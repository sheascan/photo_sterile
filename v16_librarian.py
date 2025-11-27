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
ARCHIVE_FOLDER = "./data/archived_documents"  # Where they will go

st.set_page_config(page_title="Photo Detective v16", layout="wide")
st.title("🧐 Photo Detective v16: The Librarian")
st.markdown("Identify and archive Screenshots, Scans, and Spreadsheets.")

# --- ENGINE ---

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def is_document_candidate(path):
    """
    Returns True/False and a 'Reason'.
    Checks Filename, Extension, and Visual Properties.
    """
    fname = os.path.basename(path).lower()
    
    # 1. LOW HANGING FRUIT (Filenames)
    keywords = ['screenshot', 'scan', 'screen shot', 'clip', 'capture', 'copy']
    for k in keywords:
        if k in fname:
            return True, f"Name contains '{k}'"
            
    # 2. FILE EXTENSION (PNGs are often screenshots)
    # (Optional: You can comment this out if you shoot PNG photos)
    if fname.endswith('.png'):
        # Let's verify it's not a huge photo first
        try:
            size_mb = os.path.getsize(path) / (1024*1024)
            if size_mb < 5: # Small PNGs are usually screenshots
                return True, "PNG Format"
        except: pass

    # 3. VISUAL ANALYSIS (The 'Paper' Test)
    # This is slower, so we do it last
    try:
        # Read image
        img = cv2.imread(path)
        if img is None: return False, ""
        
        # Convert to HSV (Hue, Saturation, Value)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Calculate averages
        saturation = hsv[:,:,1].mean()
        brightness = hsv[:,:,2].mean()
        
        # Rule: Documents are usually Bright (>180) and Desaturated (<30)
        if brightness > 160 and saturation < 30:
            return True, "Visual: White Paper/Doc"
            
    except:
        return False, ""
        
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
        # Get all file paths
        all_paths = [row[0] for row in conn.execute("SELECT path FROM images").fetchall()]
        conn.close()
        
        if not all_paths:
            st.error("Database empty. Index files first.")
        else:
            prog = st.progress(0)
            status = st.empty()
            
            found = []
            
            # Scan loop
            total = len(all_paths)
            # We step 10 at a time for speed in UI updates
            for i, path in enumerate(all_paths):
                is_doc, reason = is_document_candidate(path)
                if is_doc:
                    found.append({'path': path, 'reason': reason})
                
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
    st.markdown("""
    **What this detects:**
    * Files named "Screenshot", "Scan", etc.
    * PNG files (often software captures).
    * Images that are mostly white/gray (Paper, Spreadsheets).
    """)

else:
    candidates = st.session_state.doc_candidates
    
    if not candidates:
        st.success("No documents found! Your library looks like pure photos.")
    else:
        st.subheader(f"📚 Found {len(candidates)} Candidates")
        
        # ACTION BAR
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
                    
                    # Handle name collision
                    if os.path.exists(dst):
                        base, ext = os.path.splitext(fname)
                        dst = os.path.join(ARCHIVE_FOLDER, f"{base}_copy{ext}")
                    
                    try:
                        shutil.move(src, dst)
                        moved_count += 1
                        
                        # REMOVE FROM DB (Since it's no longer in the main library)
                        cursor.execute("DELETE FROM images WHERE path = ?", (src,))
                        # Also remove any clusters it was involved in
                        # (We need the ID first, but for bulk speed we skip complex query and just clean orphaned clusters later)
                        
                    except Exception as e:
                        print(f"Error moving {src}: {e}")
                        
                    if i % 10 == 0: bar.progress((i+1)/len(candidates))
                
                conn.commit()
                conn.close()
                st.success(f"Moved {moved_count} files to '{ARCHIVE_FOLDER}'")
                st.session_state.doc_candidates = [] # Clear list
                st.rerun()

        # GRID DISPLAY
        # Show 4 per row
        cols = st.columns(4)
        
        for idx, item in enumerate(candidates):
            col = cols[idx % 4]
            path = item['path']
            reason = item['reason']
            
            with col:
                try:
                    img = Image.open(path)
                    img.thumbnail((300,300))
                    st.image(img, caption=os.path.basename(path))
                    st.caption(f"Reason: {reason}")
                    
                    # Individual Action
                    if st.button("Ignore (Keep)", key=path):
                        candidates.pop(idx)
                        st.rerun()
                except:
                    st.error("File missing")