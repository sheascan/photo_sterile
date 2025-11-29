import streamlit as st
import os
import shutil
import sqlite3
import warnings
from PIL import Image

# --- SILENCE NOISE ---
warnings.filterwarnings("ignore")
os.environ["OPENCV_LOG_LEVEL"] = "OFF"

# --- CONFIG ---
DB_FILE = "photo_library.db"
OUTPUT_DIR = "sorted_photos"
TRASH_DIR = os.path.join(OUTPUT_DIR, "Blurry_Trash")
PAGE_SIZE = 100

st.set_page_config(page_title="Photo Detective v17", layout="wide")
st.title("👓 Photo Detective v17: Blur Buster")

# --- ENGINE ---

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# --- UI STATE ---
if 'blur_candidates' not in st.session_state: st.session_state.blur_candidates = []
if 'scan_done' not in st.session_state: st.session_state.scan_done = False
if 'page' not in st.session_state: st.session_state.page = 0

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Threshold")
    
    # 0 is gray fog, 100 is soft, 500+ is crisp
    threshold = st.slider("Max Sharpness Score", 0, 500, 60, help="Images below this score are considered blurry.")
    
    if st.button("🚀 Find Blurry Images", type="primary"):
        st.session_state.page = 0
        conn = get_db_connection()
        
        # Query DB for low sharpness
        # We sort ASCENDING so the blurriest are first
        query = "SELECT path, sharpness FROM images WHERE sharpness < ? ORDER BY sharpness ASC"
        results = conn.execute(query, (threshold,)).fetchall()
        conn.close()
        
        # Convert to dictionary list for easier handling
        candidates = []
        for path, score in results:
            if os.path.exists(path):
                candidates.append({'path': path, 'score': score})
                
        st.session_state.blur_candidates = candidates
        st.session_state.scan_done = True
        st.rerun()

    # --- ACTION ---
    if st.session_state.scan_done:
        st.divider()
        st.header("2. Action")
        count = len(st.session_state.blur_candidates)
        st.metric("Blurry Candidates", count)
        
        if count > 0:
            st.write("Review the list.")
            st.write("Click 'Keep' for artistic blur.")
            st.write("Then trash the rest:")
            
            if st.button(f"🗑️ Move {count} to Trash", type="primary"):
                os.makedirs(TRASH_DIR, exist_ok=True)
                conn = get_db_connection()
                cursor = conn.cursor()
                bar = st.progress(0)
                
                moved_count = 0
                for i, item in enumerate(st.session_state.blur_candidates):
                    src = item['path']
                    fname = os.path.basename(src)
                    dst = os.path.join(TRASH_DIR, fname)
                    
                    # Handle collision
                    if os.path.exists(dst):
                        base, ext = os.path.splitext(fname)
                        dst = os.path.join(TRASH_DIR, f"{base}_{item['score']}{ext}")
                    
                    try:
                        shutil.move(src, dst)
                        # Remove from DB entirely
                        cursor.execute("DELETE FROM images WHERE path = ?", (src,))
                        moved_count += 1
                    except: pass
                    
                    if i % 10 == 0: bar.progress((i+1)/count)
                
                conn.commit()
                conn.close()
                st.success(f"Moved {moved_count} images to {TRASH_DIR}")
                st.session_state.blur_candidates = []
                st.rerun()

# --- MAIN DISPLAY ---

if not st.session_state.scan_done:
    st.info("👈 Set a threshold and click Find.")
    st.markdown("""
    **Guide to Sharpness Scores:**
    * **< 20:** Extremely blurry (camera shake, out of focus).
    * **20 - 60:** Soft focus or low light noise.
    * **> 100:** Generally acceptable.
    * **> 1000:** Very sharp / Text.
    """)
else:
    candidates = st.session_state.blur_candidates
    
    if not candidates:
        st.success("No blurry images found at this threshold!")
    else:
        st.subheader("Review Candidates")
        
        # Pagination
        total_pages = (len(candidates) - 1) // PAGE_SIZE + 1
        if st.session_state.page >= total_pages: st.session_state.page = max(0, total_pages - 1)
        
        start_idx = st.session_state.page * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        visible = candidates[start_idx:end_idx]
        
        # Nav
        c1, c2, c3 = st.columns([1,4,1])
        with c1: 
            if st.button("⬅️ Prev"): 
                st.session_state.page = max(0, st.session_state.page - 1)
                st.rerun()
        with c2: st.markdown(f"**Page {st.session_state.page + 1} of {total_pages}**")
        with c3: 
            if st.button("Next ➡️"): 
                st.session_state.page = min(total_pages - 1, st.session_state.page + 1)
                st.rerun()

        # Grid
        cols = st.columns(6)
        for idx, item in enumerate(visible):
            col = cols[idx % 6]
            path = item['path']
            score = item['score']
            
            with col:
                try:
                    img = Image.open(path)
                    img.thumbnail((150,150))
                    st.image(img, caption=os.path.basename(path))
                    
                    # Color code the score
                    color = "red" if score < 30 else "orange"
                    st.markdown(f"Score: :{color}[**{score}**]")
                    
                    if st.button("Keep", key=path):
                        true_index = candidates.index(item)
                        st.session_state.blur_candidates.pop(true_index)
                        st.rerun()
                except:
                    st.error("Missing")