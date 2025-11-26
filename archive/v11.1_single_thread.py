import streamlit as st
import os
import shutil
import sqlite3
import cv2
import imagehash
import warnings
import gc # Garbage Collection
from datetime import datetime
from PIL import Image

# --- SILENCE NOISE ---
warnings.filterwarnings("ignore")
os.environ["OPENCV_LOG_LEVEL"] = "OFF"

# --- CONFIG ---
DB_FILE = "photo_library.db"
OUTPUT_FOLDER = "sorted_photos"

st.set_page_config(page_title="Photo Detective v11.1 (Single Thread)", layout="wide")
st.title("🚜 Photo Detective v11.1: The Tractor")
st.markdown("Single-threaded. Low memory. Shows exactly what file is processing.")

# --- DB & HELPERS ---
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
        val = c.fetchone()[0]
        conn.close()
        return val
    except: return 0

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
        # Load Pillow
        pil_img = Image.open(path)
        h = str(imagehash.phash(pil_img))
        pil_img.close() # Explicit close to free RAM
        
        # Load OpenCV
        cv_img = cv2.imread(path)
        if cv_img is None: return None
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        sharp = int(cv2.Laplacian(gray, cv2.CV_64F).var())
        height, width, _ = cv_img.shape
        
        # Cleanup OpenCV
        del cv_img
        del gray
        
        ts = get_timestamp(path)
        
        return (path, h, ts, sharp, width, height)
    except:
        return None

# --- UI ---
init_db()

with st.sidebar:
    st.header("Library Stats")
    stats_ph = st.empty()
    stats_ph.metric("Indexed Images", get_db_count())
    
    st.divider()
    st.header("1. Ingest (Sequential)")
    scan_path = st.text_input("Folder to Scan", "./data/input_photos")
    
    # NO THREAD SLIDER NEEDED - WE ARE RUNNING ON 1 CORE
    
    if st.button("Start Safe Scan", type="primary"):
        if not os.path.exists(scan_path):
            st.error("Folder not found!")
        else:
            valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.heic')
            files_to_process = []
            
            st.write("Checking DB for known files...")
            existing_paths = set()
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT path FROM images")
            for row in c.fetchall(): existing_paths.add(row[0])
            conn.close()

            st.write("Crawling folder...")
            for root, _, files in os.walk(scan_path):
                for f in files:
                    if f.lower().endswith(valid_exts):
                        full_path = os.path.join(root, f)
                        if full_path not in existing_paths:
                            files_to_process.append(full_path)
            
            if not files_to_process:
                st.warning("No new images found.")
            else:
                st.info(f"Processing {len(files_to_process)} new images one by one...")
                
                prog = st.progress(0)
                current_file_text = st.empty() # Shows exactly what file is busy
                
                chunk_buffer = []
                total_processed = 0
                
                # SEQUENTIAL LOOP (No ThreadPool)
                for i, f_path in enumerate(files_to_process):
                    
                    # Update UI BEFORE processing
                    fname = os.path.basename(f_path)
                    current_file_text.text(f"Processing: {fname}")
                    
                    # Run Analysis
                    res = analyze_image(f_path)
                    
                    if res:
                        chunk_buffer.append(res)
                        total_processed += 1
                        
                    # Save every 20 images (Frequent saves)
                    if len(chunk_buffer) >= 20:
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.executemany("INSERT OR IGNORE INTO images (path, phash, timestamp, sharpness, width, height) VALUES (?,?,?,?,?,?)", chunk_buffer)
                        conn.commit()
                        conn.close()
                        chunk_buffer = []
                        
                        # Aggressive Memory Cleanup
                        gc.collect() 
                        
                        stats_ph.metric("Indexed Images", get_db_count())

                    # Update Progress
                    if i % 5 == 0:
                        prog.progress((i+1)/len(files_to_process))
                
                # Save Remainder
                if chunk_buffer:
                    conn = sqlite3.connect(DB_FILE)
                    c = conn.cursor()
                    c.executemany("INSERT OR IGNORE INTO images (path, phash, timestamp, sharpness, width, height) VALUES (?,?,?,?,?,?)", chunk_buffer)
                    conn.commit()
                    conn.close()

                prog.progress(1.0)
                current_file_text.text("Done!")
                st.success("Finished!")
                st.balloons()
                st.rerun()

    st.divider()
    st.header("2. Detect")
    st.info("Use the Curator script (v12/v13) for detection once indexing is done!")