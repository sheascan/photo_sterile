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

st.set_page_config(page_title="Photo Detective v13", layout="wide")
st.title("🧭 Photo Detective v13: The Navigator")

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
    target_height = 400
    try: font = ImageFont.truetype("arial.ttf", 30)
    except: font = ImageFont.load_default()

    sorted_items = sorted(cluster_items, key=lambda x: x[1], reverse=True) 

    for item in sorted_items:
        path, is_win, sharp, w, h = item
        try:
            img = Image.open(path).convert("RGB")
            aspect = img.width / img.height
            new_w = int(target_height * aspect)
            img = img.resize((new_w, target_height))
            
            color = "#32CD32" if is_win else "#FF4500" 
            border_w = 10
            canvas = Image.new("RGB", (new_w + (border_w*2), target_height + 60), color)
            canvas.paste(img, (border_w, border_w))
            
            draw = ImageDraw.Draw(canvas)
            status = "🏆 Best" if is_win else "Duplicate"
            info = f"{w}x{h} | Sharp:{sharp}"
            
            draw.text((15, target_height + 15), status, font=font, fill="white")
            draw.text((15, target_height + 35), info, font=font, fill="white")
            images.append(canvas)
        except: pass

    if not images: return None
    
    total_w = sum(i.width for i in images)
    filmstrip = Image.new("RGB", (total_w, target_height + 60), "#202020")
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

# 1. Load Data Structure Early (For Navigation)
total_imgs, total_clusters, total_clustered_imgs = get_db_stats()

conn = get_db_connection()
try:
    # Get ALL cluster IDs sorted (so we can find index)
    all_c_ids = [x[0] for x in conn.execute("SELECT DISTINCT cluster_id FROM clusters ORDER BY cluster_id ASC").fetchall()]
except:
    all_c_ids = []
conn.close()

ITEMS_PER_PAGE = 5
if total_clusters > 0:
    total_pages = (total_clusters - 1) // ITEMS_PER_PAGE + 1
else:
    total_pages = 1

# 2. Sidebar Navigation
if 'page' not in st.session_state: st.session_state.page = 0

with st.sidebar:
    st.header("🚀 Navigation")
    st.write(f"**Total Pages:** {total_pages}")
    
    # Mode Selection
    nav_mode = st.radio("Jump Method:", ["Go to Page Number", "Go to Cluster ID"])
    
    if nav_mode == "Go to Page Number":
        # Input for Page
        # We use +1 for display (Humans count from 1), but session_state uses 0-index
        target_page_input = st.number_input("Enter Page #", min_value=1, max_value=total_pages, value=st.session_state.page + 1)
        if st.button("Jump to Page"):
            st.session_state.page = target_page_input - 1
            st.rerun()
            
    elif nav_mode == "Go to Cluster ID":
        # Input for Cluster ID
        target_cluster = st.number_input("Enter Cluster ID #", min_value=0, value=0)
        if st.button("Find Cluster"):
            if target_cluster in all_c_ids:
                # Find the index of this cluster in the list
                idx = all_c_ids.index(target_cluster)
                # Calculate which page it falls on
                target_page_calculated = idx // ITEMS_PER_PAGE
                st.session_state.page = target_page_calculated
                st.success(f"Found! Jumping to Page {target_page_calculated + 1}")
                st.rerun()
            else:
                st.error(f"Cluster {target_cluster} not found in current results.")

    st.divider()
    st.metric("Total Library", total_imgs)
    st.metric("Clusters Remaining", total_clusters)

# 3. Main Tabs
t1, t2 = st.tabs(["🎞️ Filmstrip Review", "⚙️ Tools"])

with t1:
    if not all_c_ids:
        st.info("No clusters found. Go to 'Tools' to run detection.")
    else:
        # Standard Nav Bar
        c1, c2, c3 = st.columns([1, 4, 1])
        with c1: 
            if st.button("⬅️ Previous") and st.session_state.page > 0: 
                st.session_state.page -= 1
                st.rerun()
        with c2: 
            st.markdown(f"**Page {st.session_state.page + 1} of {total_pages}**")
            st.caption(f"Showing Clusters for Index {st.session_state.page * ITEMS_PER_PAGE} - {(st.session_state.page + 1) * ITEMS_PER_PAGE}")
        with c3:
            if st.button("Next ➡️") and st.session_state.page < total_pages - 1:
                st.session_state.page += 1
                st.rerun()
                
        # Slice Data for Current Page
        start = st.session_state.page * ITEMS_PER_PAGE
        current_ids = all_c_ids[start : start + ITEMS_PER_PAGE]
        
        # RENDER LOOP
        conn = get_db_connection()
        for cid in current_ids:
            st.markdown("---")
            st.subheader(f"Cluster #{cid}")
            
            query = '''SELECT images.path, clusters.is_winner, images.sharpness, images.width, images.height
                       FROM clusters JOIN images ON clusters.image_id = images.id
                       WHERE clusters.cluster_id = ?'''
            items = conn.execute(query, (cid,)).fetchall()
            
            # Filmstrip
            filmstrip = create_filmstrip(items, cid)
            if filmstrip:
                st.image(filmstrip, use_container_width=False)
            
            # Buttons
            cols = st.columns(len(items) + 1)
            
            with cols[0]:
                st.write("Match Action:")
                if st.button(f"👐 Keep All\n(Not Duplicates)", key=f"dissolve_{cid}"):
                    dissolve_cluster(cid)
                    st.success("Dissolved.")
                    st.rerun()
            
            for idx, item in enumerate(items):
                path = item[0]
                name = os.path.basename(path)
                with cols[idx+1]:
                    st.write(f"Candidate {idx+1}")
                    if st.button(f"🏆 Keep This Only\n{name}", key=f"keep_{path}_{cid}"):
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
    st.subheader("Export Collages")
    if st.button("📂 Generate 'Reviews' Folder"):
        os.makedirs(COLLAGE_FOLDER, exist_ok=True)
        st.info("Generating...")
        conn = get_db_connection()
        prog = st.progress(0)
        for i, cid in enumerate(all_c_ids):
            query = '''SELECT images.path, clusters.is_winner, images.sharpness, images.width, images.height
                       FROM clusters JOIN images ON clusters.image_id = images.id
                       WHERE clusters.cluster_id = ?'''
            items = conn.execute(query, (cid,)).fetchall()
            strip = create_filmstrip(items, cid)
            if strip:
                strip.save(os.path.join(COLLAGE_FOLDER, f"Cluster_{cid:05d}.jpg"))
            if i % 10 == 0: prog.progress((i+1)/len(all_c_ids))
        conn.close()
        prog.progress(1.0)
        st.success(f"Done! Saved to {COLLAGE_FOLDER}")