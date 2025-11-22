import streamlit as st
import os
import shutil
import cv2
import imagehash
import numpy as np
from PIL import Image

# --- CONFIGURATION ---
DEFAULT_SOURCE = "input_photos"
KEEPERS_DIR = "sorted_keepers"
DISCARDS_DIR = "sorted_discards"

# Ensure output directories exist
os.makedirs(KEEPERS_DIR, exist_ok=True)
os.makedirs(DISCARDS_DIR, exist_ok=True)

st.set_page_config(layout="wide", page_title="Sterile Photo Sorter")

# --- HELPER: IMAGE SCORING (From v5_app) ---
def calculate_score(image_path):
    """
    Calculates a quality score based on Sharpness, Resolution, and Saturation.
    Returns a dict with stats.
    """
    try:
        # 1. Resolution & Hash
        with Image.open(image_path) as img:
            img_hash = imagehash.phash(img)
            width, height = img.size
            res_score = int((width * height) / 10000)

        # 2. CV2 Stats (Sharpness/Saturation)
        cv_img = cv2.imread(image_path)
        if cv_img is None:
            return {'path': image_path, 'score': 0, 'hash': img_hash}

        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        sharpness = int(cv2.Laplacian(gray, cv2.CV_64F).var())

        hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
        saturation = int(hsv[:, :, 1].mean())

        # Composite Score
        total_score = sharpness + res_score + (saturation * 0.5)
        
        return {
            'path': image_path,
            'hash': img_hash,
            'sharpness': sharpness,
            'res': res_score,
            'score': total_score
        }
    except Exception as e:
        # If file is corrupt, return low score
        return {'path': image_path, 'score': 0, 'hash': None}

# --- CORE LOGIC: SCANNING & CLUSTERING ---

@st.cache_data(show_spinner=False)
def scan_structure(source_folder, threshold=16):
    """
    1. Scans folder.
    2. Separates Non-Images.
    3. Calculates Stats for Images.
    4. Clusters Duplicates.
    5. Identifies Orphans.
    """
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.heic')
    
    all_files = []
    for root, _, files in os.walk(source_folder):
        for f in files:
            all_files.append(os.path.join(root, f))
            
    # 1. Separate Images vs Others
    image_paths = []
    non_image_paths = []
    
    for f in all_files:
        if f.lower().endswith(valid_exts):
            image_paths.append(f)
        else:
            non_image_paths.append(f)
            
    # 2. Calculate Stats & Hashes
    analyzed_images = []
    prog_bar = st.progress(0, text="Analyzing images...")
    
    for idx, img_path in enumerate(image_paths):
        stats = calculate_score(img_path)
        if stats['hash'] is not None:
            analyzed_images.append(stats)
        if idx % 10 == 0:
            prog_bar.progress(idx / len(image_paths))
    
    prog_bar.empty()
    
    # 3. Clustering (The "Smart" Part)
    clusters = []
    visited = set()
    clustered_paths = set()
    
    # Sort by score descending (so high quality is checked first)
    analyzed_images.sort(key=lambda x: x['score'], reverse=True)
    
    cluster_bar = st.progress(0, text="Grouping duplicates...")
    
    for i, img_a in enumerate(analyzed_images):
        if img_a['path'] in visited:
            continue
            
        current_cluster = [img_a]
        visited.add(img_a['path'])
        
        for j in range(i + 1, len(analyzed_images)):
            img_b = analyzed_images[j]
            if img_b['path'] in visited:
                continue
            
            # Compare Hashes
            sim = img_a['hash'] - img_b['hash']
            if sim <= threshold:
                current_cluster.append(img_b)
                visited.add(img_b['path'])
        
        if len(current_cluster) > 1:
            clusters.append(current_cluster)
            for c in current_cluster:
                clustered_paths.add(c['path'])
                
        if i % 20 == 0:
            cluster_bar.progress(i / len(analyzed_images))
            
    cluster_bar.empty()
    
    # 4. Identify Orphans (Singles)
    orphans = [img for img in analyzed_images if img['path'] not in clustered_paths]
    
    return {
        "clusters": clusters,
        "orphans": orphans,
        "non_images": non_image_paths
    }

# --- ACTION HANDLERS ---

def move_file(src, dest_folder):
    """Moves a file safely, handling name collisions."""
    if not os.path.exists(src): return
    
    fname = os.path.basename(src)
    dest = os.path.join(dest_folder, fname)
    
    # Rename if exists
    if os.path.exists(dest):
        base, ext = os.path.splitext(fname)
        dest = os.path.join(dest_folder, f"{base}_{int(datetime.now().timestamp())}{ext}")
        
    shutil.move(src, dest)

def process_winner(winner_path, cluster_list):
    """Moves winner to Keepers, losers to Discards."""
    # Move Winner
    move_file(winner_path, KEEPERS_DIR)
    
    # Move Losers
    for img in cluster_list:
        if img['path'] != winner_path:
            move_file(img['path'], DISCARDS_DIR)

# --- UI LAYOUT ---

st.title("🧪 Sterile Lab: Photo Processor")

with st.sidebar:
    st.header("1. Setup")
    src = st.text_input("Source Path", DEFAULT_SOURCE)
    threshold = st.slider("Similarity Threshold", 0, 30, 16)
    
    st.divider()
    
    if st.button("🚀 Start / Rescan", type="primary"):
        if os.path.exists(src):
            st.session_state.scan_data = scan_structure(src, threshold)
            st.session_state.cluster_index = 0
            st.session_state.auto_processed = False
            st.rerun()
        else:
            st.error("Source folder not found.")

# --- MAIN APP LOGIC ---

if 'scan_data' in st.session_state:
    data = st.session_state.scan_data
    clusters = data['clusters']
    orphans = data['orphans']
    non_images = data['non_images']
    
    # --- PHASE 1: AUTO-MOVE ORPHANS & VIDEOS ---
    if not st.session_state.get('auto_processed', False):
        st.info("⚡ Auto-processing Singles and Non-Images...")
        
        count_orphans = 0
        count_non = 0
        
        # Move Orphans
        for o in orphans:
            move_file(o['path'], KEEPERS_DIR)
            count_orphans += 1
            
        # Move Non-Images
        for n in non_images:
            move_file(n, KEEPERS_DIR)
            count_non += 1
            
        st.session_state.auto_processed = True
        st.success(f"Moved {count_orphans} Singles and {count_non} Videos/Files to '{KEEPERS_DIR}'")
        st.divider()

    # --- PHASE 2: CLUSTER REVIEW ---
    
    # Check if done
    if st.session_state.cluster_index >= len(clusters):
        st.balloons()
        st.success("🎉 All photos sorted! The 'input' folder should now be empty.")
        st.stop()
        
    # Get Current Cluster
    current_group = clusters[st.session_state.cluster_index]
    
    st.subheader(f"⚔️ Duplicate Battle {st.session_state.cluster_index + 1} of {len(clusters)}")
    
    # Grid Layout
    cols = st.columns(len(current_group))
    
    # Find the highest score in this group to highlight it
    best_score = max(item['score'] for item in current_group)
    
    for idx, col in enumerate(cols):
        item = current_group[idx]
        path = item['path']
        score = item['score']
        fname = os.path.basename(path)
        
        with col:
            is_best = (score == best_score)
            border_color = "green" if is_best else "red"
            
            # Display Image
            try:
                img = Image.open(path)
                st.image(img, use_container_width=True)
            except:
                st.error("Error loading")
            
            # Stats
            if is_best:
                st.markdown(f":star: **Best Quality** ({score:.0f})")
            else:
                st.caption(f"Score: {score:.0f}")
                
            st.caption(f"Sharpness: {item['sharpness']}")
            
            # ACTION BUTTON
            if st.button(f"🏆 Keep {fname}", key=path):
                process_winner(path, current_group)
                st.session_state.cluster_index += 1
                st.rerun()

    st.divider()
    col_a, col_b = st.columns([1, 4])
    with col_a:
        if st.button("⏭️ Skip Group"):
            st.session_state.cluster_index += 1
            st.rerun()
    
else:
    st.info("👈 Ready. Enter path and click Start.")