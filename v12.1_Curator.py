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

st.set_page_config(page_title="Photo Detective v12.1", layout="wide")
st.title("🎨 Photo Detective v12.1: The Curator")

# --- DATABASE & HELPERS ---
def get_db_connection():
    return sqlite3.connect(DB_FILE)

def get_db_stats():
    try:
        conn = get_db_connection()
        # 1. Total Library Size
        img_count = conn.execute("SELECT count(*) FROM images").fetchone()[0]
        # 2. Total Clusters (Groups)
        cluster_count = conn.execute("SELECT count(DISTINCT cluster_id) FROM clusters").fetchone()[0]
        # 3. Total Images Involved in Clusters (The Metric You Asked For)
        clustered_img_count = conn.execute("SELECT count(*) FROM clusters").fetchone()[0]
        conn.close()
        return img_count, cluster_count, clustered_img_count
    except: return 0, 0, 0

# --- VISUALIZATION ENGINE (The Filmstrip) ---
def create_filmstrip(cluster_items, cluster_id):
    """Stitches images side-by-side with metadata overlay."""
    images = []
    target_height = 400
    
    try: font = ImageFont.truetype("arial.ttf", 30)
    except: font = ImageFont.load_default()

    # Sort: Winner first
    sorted_items = sorted(cluster_items, key=lambda x: x[1], reverse=True) # Sort by is_winner

    for item in sorted_items:
        path, is_win, sharp, w, h = item
        try:
            img = Image.open(path).convert("RGB")
            aspect = img.width / img.height
            new_w = int(target_height * aspect)
            img = img.resize((new_w, target_height))
            
            # Border Color
            color = "#32CD32" if is_win else "#FF4500" # Green vs Red
            border_w = 10
            
            # Canvas
            canvas = Image.new("RGB", (new_w + (border_w*2), target_height + 60), color)
            canvas.paste(img, (border_w, border_w))
            
            # Text
            draw = ImageDraw.Draw(canvas)
            status = "🏆 Best" if is_win else "Duplicate"
            info = f"{w}x{h} | Sharp:{sharp}"
            
            draw.text((15, target_height + 15), status, font=font, fill="white")
            draw.text((15, target_height + 35), info, font=font, fill="white")
            
            images.append(canvas)
        except: pass

    if not images: return None
    
    # Stitch
    total_w = sum(i.width for i in images)
    filmstrip = Image.new("RGB", (total_w, target_height + 60), "#202020")
    
    x_off = 0
    for img in images:
        filmstrip.paste(img, (x_off, 0))
        x_off += img.width
        
    return filmstrip

# --- ACTIONS ---

def dissolve_cluster(cluster_id):
    """User wants to keep ALL images in this cluster (Not duplicates)."""
    conn = get_db_connection()
    conn.execute("DELETE FROM clusters WHERE cluster_id = ?", (cluster_id,))
    conn.commit()
    conn.close()

def keep_one(keep_path, cluster_items, cluster_id):
    """User selected one winner. Move others to Discards."""
    # 1. Move Winner
    k_dir = os.path.join(OUTPUT_FOLDER, "Keepers")
    os.makedirs(k_dir, exist_ok=True)
    shutil.move(keep_path, os.path.join(k_dir, os.path.basename(keep_path)))
    
    # 2. Move Losers
    d_dir = os.path.join(OUTPUT_FOLDER, "Discards")
    os.makedirs(d_dir, exist_ok=True)
    
    for item in cluster_items:
        path = item[0]
        if path != keep_path and os.path.exists(path):
            shutil.move(path, os.path.join(d_dir, os.path.basename(path)))
            
    # 3. Remove from DB display
    dissolve_cluster(cluster_id)

# --- UI MAIN ---

t1, t2 = st.tabs(["🎞️ Filmstrip Review", "⚙️ Tools & Export"])

# Load Stats
total_imgs, total_clusters, total_clustered_imgs = get_db_stats()

with t1:
    if total_clusters == 0:
        st.info("No clusters found. Go to 'Tools' to run detection if needed.")
    else:
        # Pagination
        if 'page' not in st.session_state: st.session_state.page = 0
        ITEMS_PER_PAGE = 5
        total_pages = (total_clusters - 1) // ITEMS_PER_PAGE + 1
        
        # Nav Bar
        c1, c2, c3 = st.columns([1, 4, 1])
        with c1: 
            if st.button("⬅️ Previous") and st.session_state.page > 0: 
                st.session_state.page -= 1
                st.rerun()
        with c2: 
            # --- UPDATED STATS DISPLAY ---
            st.markdown(f"**Viewing Page {st.session_state.page + 1} of {total_pages}**")
            st.caption(f"Clusters: {total_clusters} | Images Involved: {total_clustered_imgs}")
        with c3:
            if st.button("Next ➡️") and st.session_state.page < total_pages - 1:
                st.session_state.page += 1
                st.rerun()
                
        # Data Fetch
        conn = get_db_connection()
        c_ids = [x[0] for x in conn.execute("SELECT DISTINCT cluster_id FROM clusters").fetchall()]
        conn.close()
        
        start = st.session_state.page * ITEMS_PER_PAGE
        current_ids = c_ids[start : start + ITEMS_PER_PAGE]
        
        # RENDER LOOP
        conn = get_db_connection()
        for cid in current_ids:
            st.markdown("---")
            # Get Items: path, is_winner, sharpness, w, h
            query = '''SELECT images.path, clusters.is_winner, images.sharpness, images.width, images.height
                       FROM clusters JOIN images ON clusters.image_id = images.id
                       WHERE clusters.cluster_id = ?'''
            items = conn.execute(query, (cid,)).fetchall()
            
            # 1. Generate Visual
            filmstrip = create_filmstrip(items, cid)
            if filmstrip:
                st.image(filmstrip, use_container_width=False)
            
            # 2. Action Buttons
            cols = st.columns(len(items) + 1)
            
            # "Keep All" Button (First Column)
            with cols[0]:
                st.write("Match Action:")
                if st.button(f"👐 Keep All\n(Not Duplicates)", key=f"dissolve_{cid}"):
                    dissolve_cluster(cid)
                    st.success("Cluster dissolved! Images kept.")
                    st.rerun()
            
            # Individual "Keep This" Buttons
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
        # Bottom Nav
        if st.button("Next Page ➡️", key="next_btm"):
             if st.session_state.page < total_pages - 1:
                st.session_state.page += 1
                st.rerun()

with t2:
    st.header("Tools")
    st.metric("Total Library Size", total_imgs)
    c1, c2 = st.columns(2)
    c1.metric("Active Clusters", total_clusters)
    c2.metric("Images in Clusters", total_clustered_imgs)
    
    st.divider()
    st.subheader("1. Export Review Collages")
    st.write("Generate physical JPG strips of all current clusters to a folder.")
    if st.button("📂 Generate 'Reviews' Folder"):
        os.makedirs(COLLAGE_FOLDER, exist_ok=True)
        st.info("Generating collages... This might take a minute.")
        
        conn = get_db_connection()
        all_cids = [x[0] for x in conn.execute("SELECT DISTINCT cluster_id FROM clusters").fetchall()]
        
        prog = st.progress(0)
        for i, cid in enumerate(all_cids):
            query = '''SELECT images.path, clusters.is_winner, images.sharpness, images.width, images.height
                       FROM clusters JOIN images ON clusters.image_id = images.id
                       WHERE clusters.cluster_id = ?'''
            items = conn.execute(query, (cid,)).fetchall()
            
            strip = create_filmstrip(items, cid)
            if strip:
                save_path = os.path.join(COLLAGE_FOLDER, f"Cluster_{cid:05d}.jpg")
                strip.save(save_path)
            
            if i % 10 == 0: prog.progress((i+1)/len(all_cids))
            
        conn.close()
        prog.progress(1.0)
        st.success(f"Done! Check the folder '{COLLAGE_FOLDER}'")

    st.divider()
    st.subheader("2. Re-Run Detection")
    st.write("Change settings and find duplicates again (clears current results).")