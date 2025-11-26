import streamlit as st
import os
import shutil
import sqlite3
import cv2
import imagehash
import concurrent.futures
import warnings  # <--- NEW: To silence the noise
from datetime import datetime
from PIL import Image

# --- SILENCE WARNINGS ---
# This shuts up the "Palette images" and "Transparency" warnings
warnings.filterwarnings("ignore")
os.environ["OPENCV_LOG_LEVEL"] = "OFF" # Tries to silence OpenCV

# --- CONFIGURATION ---
DB_FILE = "photo_library.db"
OUTPUT_FOLDER = "sorted_photos"

st.set_page_config(page_title="Photo Detective v10.2", layout="wide")
st.title("📚 Photo Detective v10.2: Silent Mode")

# --- DATABASE MANAGEMENT ---

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS images
                 (id INTEGER PRIMARY KEY,
                  path TEXT UNIQUE,
                  phash TEXT,
                  timestamp INTEGER,
                  sharpness INTEGER,
                  width INTEGER,
                  height INTEGER,
                  status TEXT DEFAULT 'NEW')''') 
    c.execute('''CREATE TABLE IF NOT EXISTS clusters
                 (cluster_id INTEGER,
                  image_id INTEGER,
                  is_winner BOOLEAN)''')
    conn.commit()
    conn.close()

def get_db_count():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT count(*) FROM images")
        count = c.fetchone()[0]
        conn.close()
        return count
    except: return 0

# --- IMAGE PROCESSING ---

def get_timestamp(img_path):
    try:
        with Image.open(img_path) as img:
            exif = img.getexif()
            if not exif: return 0
            date_str = exif.get(36867) or exif.get(306)
            if date_str:
                dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                return int(dt.timestamp())
    except: return 0
    return 0

def analyze_image(path):
    try:
        # We wrap this in a strict try/except so one bad file never crashes the app
        pil_img = Image.open(path)
        h = str(imagehash.phash(pil_img)) 
        cv_img = cv2.imread(path)
        if cv_img is None: return None
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        sharp = int(cv2.Laplacian(gray, cv2.CV_64F).var())
        height, width, _ = cv_img.shape
        ts = get_timestamp(path)
        return (path, h, ts, sharp, width, height)
    except Exception:
        # If a file is truly broken, we just return None and move on. No drama.
        return None

# --- UI COMPONENTS ---

init_db()

with st.sidebar:
    st.header("Library Stats")
    total_files = get_db_count()
    st.metric("Indexed Images", total_files)
    
    st.divider()
    st.header("1. Ingest")
    scan_path = st.text_input("Folder to Scan", "./data/input_photos")
    workers = st.slider("Threads", 1, 16, 4)
    
    if st.button("Scan & Add to Library", type="primary"):
        if not os.path.exists(scan_path):
            st.error("Folder not found!")
        else:
            valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.heic')
            files_to_process = []
            
            st.write("🔍 Checking Database...")
            existing_paths = set()
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT path FROM images")
            for row in c.fetchall():
                existing_paths.add(row[0])
            conn.close()

            st.write("📂 Crawling folder...")
            for root, _, files in os.walk(scan_path):
                for f in files:
                    if f.lower().endswith(valid_exts):
                        full_path = os.path.join(root, f)
                        if full_path not in existing_paths:
                            files_to_process.append(full_path)
            
            if not files_to_process:
                st.warning("No new images found.")
            else:
                st.info(f"Found {len(files_to_process)} new images. Starting engine...")
                
                prog = st.progress(0)
                status_text = st.empty()
                
                batch_data = []
                total_new = len(files_to_process)
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                    future_to_file = {executor.submit(analyze_image, f): f for f in files_to_process}
                    
                    for i, future in enumerate(concurrent.futures.as_completed(future_to_file)):
                        res = future.result()
                        if res: batch_data.append(res)
                        
                        if i % 25 == 0: 
                            pct = (i + 1) / total_new
                            prog.progress(pct)
                            status_text.write(f"**Analyzing: {i+1} / {total_new}**")
                            
                prog.progress(1.0)
                status_text.write("✅ Analysis Complete! Saving...")
                
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.executemany("INSERT OR IGNORE INTO images (path, phash, timestamp, sharpness, width, height) VALUES (?,?,?,?,?,?)", batch_data)
                conn.commit()
                conn.close()
                st.success(f"Added {len(batch_data)} images!")
                st.balloons()
                st.rerun()

    st.divider()
    st.header("2. Detect")
    sim_thresh = st.slider("Hash Distance", 0, 30, 16)
    time_rad = st.slider("Time Radius (Days)", 1, 30, 10)
    
    if st.button("Find Global Duplicates"):
        st.write("🧠 Loading Library Index...")
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute("SELECT * FROM images").fetchall()
        conn.close()
        
        if not rows:
            st.error("Library is empty.")
            st.stop()

        data_objs = []
        for r in rows:
            try:
                data_objs.append({
                    'id': r[0], 'path': r[1],
                    'hash': imagehash.hex_to_hash(r[2]),
                    'ts': r[3],
                    'score': r[4] + (r[5]*r[6]/10000)
                })
            except: pass
            
        data_objs.sort(key=lambda x: x['ts'])
        clusters = []
        visited = set()
        
        prog_bar = st.progress(0)
        status = st.empty()
        total = len(data_objs)
        
        for i in range(total):
            if data_objs[i]['id'] in visited: continue
            
            img_a = data_objs[i]
            current_cluster = [img_a]
            visited.add(img_a['id'])
            
            for j in range(i + 1, total):
                img_b = data_objs[j]
                if img_b['id'] in visited: continue
                
                if img_a['ts'] > 0 and img_b['ts'] > 0:
                    diff_days = abs(img_a['ts'] - img_b['ts']) / 86400
                    if diff_days > time_rad: break 
                
                if (img_a['hash'] - img_b['hash']) <= sim_thresh:
                    current_cluster.append(img_b)
                    visited.add(img_b['id'])

            if len(current_cluster) > 1:
                clusters.append(current_cluster)
            
            if i % 100 == 0:
                prog_bar.progress((i+1)/total)
                status.write(f"**Comparing: {i} / {total}**")

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM clusters")
        count = 0
        for c_idx, clust in enumerate(clusters):
            winner = max(clust, key=lambda x: x['score'])
            for item in clust:
                is_win = (item == winner)
                c.execute("INSERT INTO clusters VALUES (?,?,?)", (c_idx, item['id'], is_win))
            count += 1
        conn.commit()
        conn.close()
        st.success(f"Found {count} clusters! Go to Review Tab.")

t1, t2 = st.tabs(["Review Duplicates", "Tools"])

with t1:
    conn = sqlite3.connect(DB_FILE)
    try: c_ids = [x[0] for x in conn.execute("SELECT DISTINCT cluster_id FROM clusters").fetchall()]
    except: c_ids = []
    conn.close()
    
    if not c_ids:
        st.info("No duplicates found yet.")
    else:
        if 'page' not in st.session_state: st.session_state.page = 0
        ITEMS_PER_PAGE = 10
        total_pages = (len(c_ids) - 1) // ITEMS_PER_PAGE + 1
        
        c1, c2, c3 = st.columns([1,2,1])
        with c1: 
            if st.button("⬅️ Prev") and st.session_state.page > 0: 
                st.session_state.page -= 1
                st.rerun()
        with c2: st.markdown(f"**Page {st.session_state.page + 1} of {total_pages}**")
        with c3:
            if st.button("Next ➡️") and st.session_state.page < total_pages - 1:
                st.session_state.page += 1
                st.rerun()
                
        start = st.session_state.page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        current_ids = c_ids[start:end]
        
        conn = sqlite3.connect(DB_FILE)
        for cid in current_ids:
            st.divider()
            st.subheader(f"Cluster #{cid}")
            query = '''SELECT images.path, clusters.is_winner, images.sharpness, images.width, images.height
                       FROM clusters JOIN images ON clusters.image_id = images.id
                       WHERE clusters.cluster_id = ?'''
            items = conn.execute(query, (cid,)).fetchall()
            
            cols = st.columns(len(items))
            for idx, item in enumerate(items):
                path, is_win, sharp, w, h = item
                with cols[idx]:
                    try:
                        img = Image.open(path)
                        img.thumbnail((400,400))
                        st.image(img, caption=os.path.basename(path))
                        if is_win: st.success(f"🏆 Best\n{w}x{h} | S:{sharp}")
                        else: st.error(f"Duplicate\n{w}x{h} | S:{sharp}")
                        
                        if st.button(f"Keep This Only", key=f"keep_{path}_{cid}"):
                            keep_dir = os.path.join(OUTPUT_FOLDER, "Keepers")
                            disc_dir = os.path.join(OUTPUT_FOLDER, "Discards")
                            os.makedirs(keep_dir, exist_ok=True)
                            os.makedirs(disc_dir, exist_ok=True)
                            
                            shutil.move(path, os.path.join(keep_dir, os.path.basename(path)))
                            for sub_item in items:
                                sub_path = sub_item[0]
                                if sub_path != path:
                                    if os.path.exists(sub_path):
                                        shutil.move(sub_path, os.path.join(disc_dir, os.path.basename(sub_path)))
                            st.success("Sorted!")
                            st.rerun()
                    except: st.error("Missing File")
        conn.close()

with t2:
    if st.button("⚠️ Wipe Database"):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            st.success("Deleted.")
            st.rerun()