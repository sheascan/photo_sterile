import streamlit as st
import os
import shutil
import sqlite3
import cv2
import imagehash
import concurrent.futures
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
DB_FILE = "./data/photo_library.db"
OUTPUT_FOLDER = "./data/sorted_photos"

st.set_page_config(page_title="Photo Detective v10 (DB)", layout="wide")
st.title("📚 Photo Detective v10: The Library Edition")

# --- DATABASE MANAGEMENT ---

def init_db():
    """Creates the database tables if they don't exist."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Table to store file info
    c.execute('''CREATE TABLE IF NOT EXISTS images
                 (id INTEGER PRIMARY KEY,
                  path TEXT UNIQUE,
                  phash TEXT,
                  timestamp INTEGER,
                  sharpness INTEGER,
                  width INTEGER,
                  height INTEGER,
                  status TEXT DEFAULT 'NEW')''') 
    # Table to store identified clusters
    c.execute('''CREATE TABLE IF NOT EXISTS clusters
                 (cluster_id INTEGER,
                  image_id INTEGER,
                  is_winner BOOLEAN)''')
    conn.commit()
    conn.close()

def get_db_count():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT count(*) FROM images")
    count = c.fetchone()[0]
    conn.close()
    return count

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
    """The worker function."""
    try:
        pil_img = Image.open(path)
        h = str(imagehash.phash(pil_img)) # Store hash as string for DB
        
        cv_img = cv2.imread(path)
        if cv_img is None: return None
        
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        sharp = int(cv2.Laplacian(gray, cv2.CV_64F).var())
        height, width, _ = cv_img.shape
        
        ts = get_timestamp(path)
        
        return (path, h, ts, sharp, width, height)
    except:
        return None

# --- UI COMPONENTS ---

# Initialize DB on load
init_db()

# SIDEBAR
with st.sidebar:
    st.header("Library Stats")
    total_files = get_db_count()
    st.metric("Indexed Images", total_files)
    
    st.divider()
    st.header("1. Ingest")
    scan_path = st.text_input("Folder to Scan", "./input_photos")
    workers = st.slider("Threads", 1, 16, 4)
    if st.button("Scan & Add to Library", type="primary"):
        # SCAN LOGIC
        valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
        files_to_process = []
        
        st.write("🔍 Crawling folder...")
        existing_paths = set()
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT path FROM images")
        for row in c.fetchall():
            existing_paths.add(row[0])
        conn.close()

        for root, _, files in os.walk(scan_path):
            for f in files:
                if f.lower().endswith(valid_exts):
                    full_path = os.path.join(root, f)
                    if full_path not in existing_paths:
                        files_to_process.append(full_path)
        
        if not files_to_process:
            st.warning("No new images found in this folder.")
        else:
            st.info(f"Found {len(files_to_process)} new images. analyzing...")
            prog = st.progress(0)
            
            # BATCH INSERT
            batch_data = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                results = list(executor.map(analyze_image, files_to_process))
                
                for i, res in enumerate(results):
                    if res: batch_data.append(res)
                    prog.progress((i+1)/len(results))
            
            # Write to DB
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.executemany("INSERT OR IGNORE INTO images (path, phash, timestamp, sharpness, width, height) VALUES (?,?,?,?,?,?)", batch_data)
            conn.commit()
            conn.close()
            st.success(f"Added {len(batch_data)} images to the Library!")
            st.rerun()

    st.divider()
    st.header("2. Detect")
    sim_thresh = st.slider("Hash Distance", 0, 30, 16)
    time_rad = st.slider("Time Radius (Days)", 1, 30, 10)
    
    if st.button("Find Global Duplicates"):
        st.write("🧠 Loading Library Data...")
        conn = sqlite3.connect(DB_FILE)
        # Load data into memory for fast comparison (100k dicts is handled by RAM easily, images are not)
        # Row: 0-id, 1-path, 2-hash, 3-ts, 4-sharp, 5-w, 6-h
        rows = conn.execute("SELECT * FROM images WHERE status='NEW'").fetchall()
        conn.close()
        
        if not rows:
            st.warning("Library is empty or all processed.")
            st.stop()

        # PREPARE DATA STRUCTURES
        # Convert hex hash string back to ImageHash object for math
        data_objs = []
        for r in rows:
            try:
                data_objs.append({
                    'id': r[0],
                    'path': r[1],
                    'hash': imagehash.hex_to_hash(r[2]),
                    'ts': r[3],
                    'score': r[4] + (r[5]*r[6]/10000) # Sharpness + Res Score
                })
            except: pass
            
        # CLUSTERING LOGIC (Optimized)
        # Sort by Time to reduce comparison window
        data_objs.sort(key=lambda x: x['ts'])
        
        clusters = []
        visited = set()
        
        prog_bar = st.progress(0)
        status = st.empty()
        
        # Limit comparison window to avoid N^2 on 100k
        # We compare an image only with others within the Time Radius in the sorted list
        
        window_size = 2000 # Safety buffer, usually enough for time radius
        
        for i in range(len(data_objs)):
            if data_objs[i]['id'] in visited: continue
            
            img_a = data_objs[i]
            current_cluster = [img_a]
            visited.add(img_a['id'])
            
            # Only look ahead in the sorted list
            # We stop looking if time difference > radius
            start_scan = i + 1
            
            for j in range(start_scan, len(data_objs)):
                img_b = data_objs[j]
                if img_b['id'] in visited: continue
                
                # Time Check (Fastest)
                diff_days = abs(img_a['ts'] - img_b['ts']) / 86400
                if diff_days > time_rad:
                    # Since list is sorted by time, if we exceed radius, we can stop checking this loop
                    # UNLESS timestamps are 0 (missing), then we must check.
                    if img_a['ts'] != 0 and img_b['ts'] != 0:
                        break 
                
                # Hash Check
                if (img_a['hash'] - img_b['hash']) <= sim_thresh:
                    current_cluster.append(img_b)
                    visited.add(img_b['id'])

            if len(current_cluster) > 1:
                clusters.append(current_cluster)
            
            if i % 100 == 0:
                prog_bar.progress((i+1)/len(data_objs))
                status.text(f"Scanned {i}/{len(data_objs)}...")

        # SAVE CLUSTERS TO DB
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM clusters") # Clear old results
        
        count = 0
        for c_idx, clust in enumerate(clusters):
            # Determine winner
            winner = max(clust, key=lambda x: x['score'])
            for item in clust:
                is_win = (item == winner)
                c.execute("INSERT INTO clusters VALUES (?,?,?)", (c_idx, item['id'], is_win))
            count += 1
            
        conn.commit()
        conn.close()
        st.success(f"Found {count} clusters! Go to Review Tab.")

# --- MAIN TABS ---

t1, t2 = st.tabs(["Review Duplicates", "Tools"])

with t1:
    # Load Clusters from DB
    conn = sqlite3.connect(DB_FILE)
    # Get list of cluster IDs
    c_ids = [x[0] for x in conn.execute("SELECT DISTINCT cluster_id FROM clusters").fetchall()]
    conn.close()
    
    if not c_ids:
        st.info("No duplicates found yet. Index folders and click 'Find Global Duplicates'.")
    else:
        # Pagination
        if 'page' not in st.session_state: st.session_state.page = 0
        ITEMS_PER_PAGE = 10
        
        start = st.session_state.page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        current_ids = c_ids[start:end]
        
        # Nav
        c1, c2, c3 = st.columns([1,2,1])
        with c1: 
            if st.button("Prev") and st.session_state.page > 0: 
                st.session_state.page -= 1
                st.rerun()
        with c3:
            if st.button("Next") and end < len(c_ids):
                st.session_state.page += 1
                st.rerun()
                
        st.write(f"Page {st.session_state.page + 1} of {(len(c_ids)//ITEMS_PER_PAGE)+1}")
        
        # Render
        conn = sqlite3.connect(DB_FILE)
        for cid in current_ids:
            st.divider()
            st.subheader(f"Cluster #{cid}")
            
            # Get items for this cluster
            # Join with images table to get paths
            query = '''SELECT images.path, clusters.is_winner, images.sharpness, images.width, images.height
                       FROM clusters 
                       JOIN images ON clusters.image_id = images.id
                       WHERE clusters.cluster_id = ?'''
            items = conn.execute(query, (cid,)).fetchall()
            
            cols = st.columns(len(items))
            for idx, item in enumerate(items):
                path, is_win, sharp, w, h = item
                with cols[idx]:
                    try:
                        img = Image.open(path)
                        img.thumbnail((300,300))
                        
                        border = "green" if is_win else "red"
                        st.image(img, caption=os.path.basename(path))
                        if is_win: st.markdown("**:star: Best Quality**")
                        st.caption(f"Sharp: {sharp} | {w}x{h}")
                        
                        if st.button(f"Keep This", key=f"keep_{path}_{cid}"):
                            # ACTION LOGIC
                            # 1. Move winner to keep
                            keep_dir = os.path.join(OUTPUT_FOLDER, "Keepers")
                            os.makedirs(keep_dir, exist_ok=True)
                            shutil.copy2(path, os.path.join(keep_dir, os.path.basename(path)))
                            
                            # 2. Move others to discard
                            disc_dir = os.path.join(OUTPUT_FOLDER, "Discards")
                            os.makedirs(disc_dir, exist_ok=True)
                            
                            for sub_item in items:
                                sub_path = sub_item[0]
                                if sub_path != path:
                                    shutil.copy2(sub_path, os.path.join(disc_dir, os.path.basename(sub_path)))
                                    
                            st.success("Processed!")
                    except:
                        st.error("Missing File")
        conn.close()

with t2:
    st.write("Database Maintenance")
    if st.button("⚠️ Wipe Database (Reset All)"):
        if os.path.exists(DB_FILE):
            os.remove(DB_FILE)
            st.success("Reset complete.")
            st.rerun()