import streamlit as st
import os
import shutil
import sqlite3
import cv2
import numpy as np
import warnings
from PIL import Image

# --- SILENCE NOISE ---
warnings.filterwarnings("ignore")
os.environ["OPENCV_LOG_LEVEL"] = "OFF"

# --- CONFIG ---
DB_FILE = "photo_library.db"
SOURCE_FOLDER = "./data/input_photos"
ARCHIVE_FOLDER = "./data/archived_documents"
PAGE_SIZE = 20  # Items per page

st.set_page_config(page_title="Photo Detective v16.4", layout="wide")
st.title("🧐 Photo Detective v16.4: Paged Librarian")

# --- ENGINE ---

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def is_document_candidate(path):
    fname = os.path.basename(path).lower()
    keywords = ['screenshot', 'scan', 'screen shot', 'clip', 'capture', 'copy']
    for k in keywords:
        if k in fname: return True, f"Name contains '{k}'"
            
    if fname.endswith('.png'):
        try:
            if os.path.getsize(path) / (1024*1024) < 5: return True, "PNG Format"
        except: pass

    try:
        img = cv2.imread(path)
        if img is None: return False, ""
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        if hsv[:,:,2].mean() > 160 and hsv[:,:,1].mean() < 30:
            return True, "Visual: White Paper/Doc"
    except: return False, ""
        
    return False, ""

# --- UI STATE ---
if 'doc_candidates' not in st.session_state: st.session_state.doc_candidates = []
if 'scan_complete' not in st.session_state: st.session_state.scan_complete = False
if 'page' not in st.session_state: st.session_state.page = 0

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Scan")
    
    if st.button("🚀 Scan for Documents", type="primary"):
        st.session_state.doc_candidates = []
        st.session_state.scan_complete = False
        st.session_state.page = 0
        
        conn = get_db_connection()
        all_paths = [row[0] for row in conn.execute("SELECT path FROM images").fetchall()]
        conn.close()
        
        if not all_paths:
            st.error("Database empty.")
        else:
            prog = st.progress(0)
            status = st.empty()
            found = []
            total = len(all_paths)
            
            for i, path in enumerate(all_paths):
                if not os.path.exists(path): continue
                is_doc, reason = is_document_candidate(path)
                if is_doc: found.append({'path': path, 'reason': reason})
                if i % 100 == 0:
                    prog.progress((i+1)/total)
                    status.write(f"Scanning {i}/{total}... Found {len(found)}")
            
            st.session_state.doc_candidates = found
            st.session_state.scan_complete = True
            prog.progress(1.0)
            status.empty()
            st.rerun()

    # --- ACTION SECTION ---
    if st.session_state.scan_complete:
        st.divider()
        st.header("2. Action")
        count = len(st.session_state.doc_candidates)
        st.metric("Candidates Found", count)
        
        if count > 0:
            st.write("Review the list on the right.")
            st.write("Click 'Ignore' to keep a photo.")
            st.write("When ready, move the rest:")
            
            if st.button(f"📦 Move {count} to Archive", type="primary"):
                os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
                moved_count = 0
                conn = get_db_connection()
                cursor = conn.cursor()
                bar = st.progress(0)
                
                # Prune Check
                valid_candidates = [c for c in st.session_state.doc_candidates if os.path.exists(c['path'])]
                
                for i, item in enumerate(valid_candidates):
                    src = item['path']
                    fname = os.path.basename(src)
                    dst = os.path.join(ARCHIVE_FOLDER, fname)
                    
                    if os.path.exists(dst):
                        base, ext = os.path.splitext(fname)
                        dst = os.path.join(ARCHIVE_FOLDER, f"{base}_copy{ext}")
                    
                    try:
                        shutil.move(src, dst)
                        moved_count += 1
                        cursor.execute("DELETE FROM images WHERE path = ?", (src,))
                    except Exception as e: print(f"Error: {e}")
                        
                    if i % 10 == 0: bar.progress((i+1)/len(valid_candidates))
                
                conn.commit()
                conn.close()
                st.success(f"Moved {moved_count} files!")
                st.session_state.doc_candidates = [] 
                st.rerun()
        else:
            st.success("List is clean!")

# --- MAIN AREA ---

if not st.session_state.scan_complete:
    st.info("👈 Click 'Scan for Documents' to start.")
else:
    candidates = st.session_state.doc_candidates
    
    if not candidates:
        st.success("No documents found! Your library looks like pure photos.")
    else:
        st.subheader("Review Candidates")
        
        # --- PAGINATION LOGIC ---
        total_items = len(candidates)
        total_pages = (total_items - 1) // PAGE_SIZE + 1
        
        # Ensure page is valid (e.g. if items deleted)
        if st.session_state.page >= total_pages: st.session_state.page = total_pages - 1
        if st.session_state.page < 0: st.session_state.page = 0
        
        start_idx = st.session_state.page * PAGE_SIZE
        end_idx = start_idx + PAGE_SIZE
        visible_candidates = candidates[start_idx:end_idx]

        # Top Nav
        c1, c2, c3 = st.columns([1, 4, 1])
        with c1: 
            if st.button("⬅️ Prev"):
                if st.session_state.page > 0:
                    st.session_state.page -= 1
                    st.rerun()
        with c2: 
            st.markdown(f"**Page {st.session_state.page + 1} of {total_pages}**")
        with c3:
            if st.button("Next ➡️"):
                if st.session_state.page < total_pages - 1:
                    st.session_state.page += 1
                    st.rerun()

        # Grid
        cols = st.columns(4)
        for idx, item in enumerate(visible_candidates):
            col = cols[idx % 4]
            path = item['path']
            
            with col:
                try:
                    img = Image.open(path)
                    img.thumbnail((300,300))
                    st.image(img, caption=os.path.basename(path))
                    st.caption(f"{item['reason']}")
                    
                    if st.button("Ignore (Keep)", key=path):
                        # Find the true index in the main list
                        true_index = candidates.index(item)
                        st.session_state.doc_candidates.pop(true_index)
                        st.rerun()
                except Exception:
                    # Auto-remove missing
                    if item in st.session_state.doc_candidates:
                        st.session_state.doc_candidates.remove(item)
                        st.rerun()
        
        st.markdown("---")
        # Bottom Nav
        b1, b2, b3 = st.columns([1, 4, 1])
        with b1: 
            if st.button("⬅️ Prev", key="b_prev"):
                if st.session_state.page > 0:
                    st.session_state.page -= 1
                    st.rerun()
        with b3:
            if st.button("Next ➡️", key="b_next"):
                if st.session_state.page < total_pages - 1:
                    st.session_state.page += 1
                    st.rerun()