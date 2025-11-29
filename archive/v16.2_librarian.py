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

st.set_page_config(page_title="Photo Detective v16.2", layout="wide")
st.title("🧐 Photo Detective v16.2: Librarian")

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

# --- SIDEBAR ---
with st.sidebar:
    st.header("1. Scan")
    
    if st.button("🚀 Scan for Documents", type="primary"):
        st.session_state.doc_candidates = []
        st.session_state.scan_complete = False
        
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

    # --- ACTION SECTION (Always visible now) ---
    if st.session_state.scan_complete:
        st.divider()
        st.header("2. Action")
        count = len(st.session_state.doc_candidates)
        st.metric("Candidates Found", count)
        
        if count > 0:
            st.write("Review the list on the right.")
            st.write("Click 'Ignore' to keep a photo.")
            st.write("When ready, move the rest:")
            
            # THE MOVED BUTTON
            if st.button(f"📦 Move {count} to Archive", type="primary"):
                os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
                moved_count = 0
                conn = get_db_connection()
                cursor = conn.cursor()
                bar = st.progress(0)
                
                for i, item in enumerate(st.session_state.doc_candidates):
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
                        
                    if i % 10 == 0: bar.progress((i+1)/count)
                
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
    # --- AUTO-PRUNE GHOSTS ---
    original_count = len(st.session_state.doc_candidates)
    st.session_state.doc_candidates = [c for c in st.session_state.doc_candidates if os.path.exists(c['path'])]
    
    if original_count != len(st.session_state.doc_candidates):
        st.rerun() # Refresh if we pruned ghosts
    
    candidates = st.session_state.doc_candidates
    
    if not candidates:
        st.success("No documents found! Your library looks like pure photos.")
    else:
        st.subheader("Review Candidates")
        st.caption("These files will be moved to Archive unless you click 'Ignore'.")

        cols = st.columns(4)
        for idx, item in enumerate(candidates):
            col = cols[idx % 4]
            path = item['path']
            
            with col:
                try:
                    img = Image.open(path)
                    img.thumbnail((300,300))
                    st.image(img, caption=os.path.basename(path))
                    st.caption(f"{item['reason']}")
                    
                    if st.button("Ignore (Keep)", key=path):
                        candidates.pop(idx)
                        st.rerun()
                except Exception:
                    st.error("File missing")