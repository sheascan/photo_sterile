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

st.set_page_config(page_title="Photo Detective v16.1", layout="wide")
st.title("🧐 Photo Detective v16.1: The Librarian")
st.markdown("Identify and archive Screenshots, Scans, and Spreadsheets.")

# --- ENGINE ---

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def is_document_candidate(path):
    fname = os.path.basename(path).lower()
    
    # 1. Filenames
    keywords = ['screenshot', 'scan', 'screen shot', 'clip', 'capture', 'copy']
    for k in keywords:
        if k in fname: return True, f"Name contains '{k}'"
            
    # 2. Extension
    if fname.endswith('.png'):
        try:
            if os.path.getsize(path) / (1024*1024) < 5: return True, "PNG Format"
        except: pass

    # 3. Visual Analysis
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
    st.header("Librarian Controls")
    
    if st.button("🚀 Scan for Documents", type="primary"):
        st.session_state.doc_candidates = []
        st.session_state.scan_complete = False
        
        conn = get_db_connection()
        all_paths = [row[0] for row in conn.execute("SELECT path FROM images").fetchall()]
        conn.close()
        
        if not all_paths:
            st.error("Database empty. Index files first.")
        else:
            prog = st.progress(0)
            status = st.empty()
            found = []
            total = len(all_paths)
            
            for i, path in enumerate(all_paths):
                # Verify existence first
                if not os.path.exists(path): continue
                
                is_doc, reason = is_document_candidate(path)
                if is_doc: found.append({'path': path, 'reason': reason})
                
                if i % 100 == 0:
                    prog.progress((i+1)/total)
                    status.write(f"Scanning {i}/{total}... Found {len(found)}")
            
            st.session_state.doc_candidates = found
            st.session_state.scan_complete = True
            prog.progress(1.0)
            status.success("Scan Complete!")
            st.rerun()

# --- MAIN AREA ---

if not st.session_state.scan_complete:
    st.info("👈 Click 'Scan for Documents' to start.")
else:
    # --- AUTO-PRUNE GHOSTS ---
    # Removes files that were deleted/moved by other tools since the last scan
    original_count = len(st.session_state.doc_candidates)
    st.session_state.doc_candidates = [c for c in st.session_state.doc_candidates if os.path.exists(c['path'])]
    pruned_count = len(st.session_state.doc_candidates)
    
    if original_count != pruned_count:
        st.toast(f"Removed {original_count - pruned_count} ghost files from list.")
    
    candidates = st.session_state.doc_candidates
    
    if not candidates:
        st.success("No documents found!")
    else:
        st.subheader(f"📚 Found {len(candidates)} Candidates")
        
        c1, c2 = st.columns([3, 1])
        with c2:
            if st.button(f"📦 Move ALL to Archive"):
                os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
                moved_count = 0
                conn = get_db_connection()
                cursor = conn.cursor()
                bar = st.progress(0)
                
                for i, item in enumerate(candidates):
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
                        
                    if i % 10 == 0: bar.progress((i+1)/len(candidates))
                
                conn.commit()
                conn.close()
                st.success(f"Moved {moved_count} files to '{ARCHIVE_FOLDER}'")
                st.session_state.doc_candidates = [] 
                st.rerun()

        cols = st.columns(4)
        for idx, item in enumerate(candidates):
            col = cols[idx % 4]
            path = item['path']
            
            with col:
                # FIX 1: Catch specific Exception, not BaseException (allows Rerun)
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