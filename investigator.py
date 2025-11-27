import streamlit as st
import os
import shutil
import sqlite3
import cv2
import imagehash
import warnings
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# --- SILENCE NOISE ---
warnings.filterwarnings("ignore")
os.environ["OPENCV_LOG_LEVEL"] = "OFF"

# --- CONFIG ---
DB_FILE = "photo_library.db"
OUTPUT_FOLDER = "sorted_photos"
COLLAGE_FOLDER = "review_collages"

st.set_page_config(page_title="Photo Detective v14.2", layout="wide")
st.title("🕵️ Photo Detective v14.2: Silent Inspector")

# --- DATABASE & HELPERS ---
def get_db_connection():
    return sqlite3.connect(DB_FILE)

def get_db_stats():
    try:
        conn = get_db_connection()
        img_count = conn.execute("SELECT count(*) FROM images").fetchone()[0]
        cluster_count = conn.execute("SELECT count(DISTINCT cluster_id) FROM clusters").fetchone()[0]
        clustered_img_count = conn.execute("SELECT count(*) FROM clusters").fetchone()[0]
        conn.close()
        return img_count, cluster_count, clustered_img_count
    except: return 0, 0, 0

# --- VISUALIZATION ENGINE ---
def create_filmstrip(cluster_items, cluster_id):
    images = []
    target_height = 450 
    try: font = ImageFont.truetype("arial.ttf", 24)
    except: font = ImageFont.load_default()
    try: small_font = ImageFont.truetype("arial.ttf", 16)
    except: small_font = ImageFont.load_default()

    sorted_items = sorted(cluster_items, key=lambda x: x[1], reverse=True) 

    for item in sorted_items:
        path, is_win, sharp, w, h = item
        try:
            img = Image.open(path).convert("RGB")
            aspect = img.width / img.height
            new_w = int(400 * aspect) 
            img = img.resize((new_w, 400))
            
            color = "#32CD32" if is_win else "#FF4500" 
            border_w = 10
            
            canvas = Image.new("RGB", (new_w + (border_w*2), target_height + 100), color)
            canvas.paste(img, (border_w, border_w))
            
            draw = ImageDraw.Draw(canvas)
            
            status = "🏆 Best" if is_win else "Duplicate"
            info = f"{w}x{h} | Sharp:{sharp}"
            
            folder_name = os.path.basename(os.path.dirname(path))
            filename = os.path.basename(path)
            
            draw.text((15, 415), status, font=font, fill="white")
            draw.text((15, 445), info, font=font, fill="white")
            draw.text((15, 480), f"{filename}", font=small_font, fill="white")
            draw.text((15, 500), f".../{folder_name}/", font=small_font, fill="yellow")
            
            images.append(canvas)
        except: pass

    if not images: return None
    
    total_w = sum(i.width for i in images)
    filmstrip = Image.new("RGB", (total_w, target_height + 100), "#202020")
    x_off = 0
    for img in images:
        filmstrip.paste(img, (x_off, 0))
        x_off += img.width
    return filmstrip

# --- ACTIONS ---
def dissolve_cluster(cluster_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM clusters WHERE cluster_id = ?", (cluster_id,))
    conn.commit()
    conn.close()

def keep_one(keep_path, cluster_items, cluster_id):
    k_dir = os.path.join(OUTPUT_FOLDER, "Keepers")
    os.makedirs(k_dir, exist_ok=True)
    shutil.move(keep_path, os.path.join(k_dir, os.path.basename(keep_path)))
    
    d_dir = os.path.join(OUTPUT_FOLDER, "Discards")
    os.makedirs(d_dir, exist_ok=True)
    
    for item in cluster_items:
        path = item[0]
        if path != keep_path and os.path.exists(path):
            shutil.move(path, os.path.join(d_dir, os.path.basename(path)))
    dissolve_cluster(cluster_id)

# --- UI MAIN ---

# Load Stats
total_imgs, total_clusters, total_clustered_imgs = get_db_stats()

# 1. SIDEBAR
if 'page' not in st.session_state: st.session_state.page = 0

with st.sidebar:
    st.header("🔍 Forensics")
    path_filter = st.text_input("Filter by Folder/Path", placeholder="e.g. 'scans' or 'legacy'")
    st.divider()
    
    conn = get_db_connection()
    if path_filter:
        query = f'''
            SELECT DISTINCT clusters.cluster_id 
            FROM clusters 
            JOIN images ON clusters.image_id = images.id 
            WHERE images.path LIKE ?
            ORDER BY clusters.cluster_id ASC
        '''
        filtered_c_ids = [x[0] for x in conn.execute(query, (f'%{path_filter}%',)).fetchall()]
        st.info(f"Found {len(filtered_c_ids)} clusters matching '{path_filter}'")
    else:
        filtered_c_ids = [x[0] for x in conn.execute("SELECT DISTINCT cluster_id FROM clusters ORDER BY cluster_id ASC").fetchall()]
    conn.close()

    ITEMS_PER_PAGE = 5
    if len(filtered_c_ids) > 0:
        total_pages = (len(filtered_c_ids) - 1) // ITEMS_PER_PAGE + 1
    else:
        total_pages = 1
        
    st.write(f"**Total Pages:** {total_pages}")
    
    target_page = st.number_input("Jump to Page", min_value=1, max_value=total_pages, value=st.session_state.page + 1)
    if st.button("Go"):
        st.session_state.page = target_page - 1
        st.rerun()
# --- EXIT BUTTON (POLITE VERSION) ---
    st.markdown("---")
    if st.button("❌ Exit App"):
        st.markdown("### 👋 Goodbye!")
        st.success("Server shutting down... You can close this tab.")
        
        # Wait 2 seconds to let the message render, THEN kill the server
        import time
        time.sleep(2)
        
        import os
        import signal
        os.kill(os.getpid(), signal.SIGTERM)
        
# 2. MAIN VIEW
t1, t2 = st.tabs(["🎞️ Filmstrip Review", "⚙️ Tools"])

with t1:
    if not filtered_c_ids:
        st.warning("No clusters match your filter.")
    else:
        c1, c2, c3 = st.columns([1, 4, 1])
        with c1: 
            if st.button("⬅️ Previous") and st.session_state.page > 0: 
                st.session_state.page -= 1
                st.rerun()
        with c2: 
            st.markdown(f"**Page {st.session_state.page + 1} of {total_pages}**")
            if path_filter: st.caption(f"Filtering for: '{path_filter}'")
        with c3:
            if st.button("Next ➡️") and st.session_state.page < total_pages - 1:
                st.session_state.page += 1
                st.rerun()
                
        start = st.session_state.page * ITEMS_PER_PAGE
        current_ids = filtered_c_ids[start : start + ITEMS_PER_PAGE]
        
        conn = get_db_connection()
        for cid in current_ids:
            st.markdown("---")
            st.subheader(f"Cluster #{cid}")
            
            query = '''SELECT images.path, clusters.is_winner, images.sharpness, images.width, images.height
                       FROM clusters JOIN images ON clusters.image_id = images.id
                       WHERE clusters.cluster_id = ?'''
            items = conn.execute(query, (cid,)).fetchall()
            
            # FIX: Removed deprecated argument
            filmstrip = create_filmstrip(items, cid)
            if filmstrip:
                st.image(filmstrip)
            
            cols = st.columns(len(items) + 1)
            with cols[0]:
                st.write("Match Action:")
                if st.button(f"👐 Keep All", key=f"dissolve_{cid}"):
                    dissolve_cluster(cid)
                    st.success("Dissolved.")
                    st.rerun()
            
            for idx, item in enumerate(items):
                path = item[0]
                name = os.path.basename(path)
                folder_name = os.path.basename(os.path.dirname(path))
                
                with cols[idx+1]:
                    st.markdown(f"**{name}**")
                    st.caption(f"📂 .../{folder_name}/")
                    
                    if st.button(f"🏆 Keep This Only", key=f"keep_{path}_{cid}"):
                        keep_one(path, items, cid)
                        st.success("Sorted!")
                        st.rerun()
        conn.close()
        
        st.markdown("---")
        if st.button("Next Page ➡️", key="next_btm"):
             if st.session_state.page < total_pages - 1:
                st.session_state.page += 1
                st.rerun()

with t2:
    st.header("Tools")
    if st.button("📂 Generate 'Reviews' Folder"):
        os.makedirs(COLLAGE_FOLDER, exist_ok=True)
        conn = get_db_connection()
        prog = st.progress(0)
        for i, cid in enumerate(filtered_c_ids):
            query = '''SELECT images.path, clusters.is_winner, images.sharpness, images.width, images.height
                       FROM clusters JOIN images ON clusters.image_id = images.id
                       WHERE clusters.cluster_id = ?'''
            items = conn.execute(query, (cid,)).fetchall()
            strip = create_filmstrip(items, cid)
            if strip:
                strip.save(os.path.join(COLLAGE_FOLDER, f"Cluster_{cid:05d}.jpg"))
            if i % 10 == 0: prog.progress((i+1)/len(filtered_c_ids))
        conn.close()
        prog.progress(1.0)
        st.success(f"Generated {len(filtered_c_ids)} collages")