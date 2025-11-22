import streamlit as st
import os
import shutil
import cv2
import imagehash
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# --- CONFIGURATION ---
DEFAULT_SOURCE = "input_photos"
KEEPERS_DIR = "sorted_keepers"
DISCARDS_DIR = "sorted_discards"

# Ensure output directories exist
os.makedirs(KEEPERS_DIR, exist_ok=True)
os.makedirs(DISCARDS_DIR, exist_ok=True)

st.set_page_config(layout="wide", page_title="Visual Photo Sorter")

# --- 1. IMAGE ANALYSIS & SCORING ---

def calculate_score(image_path):
    """Calculates Sharpness + Resolution Score."""
    try:
        with Image.open(image_path) as img:
            img_hash = imagehash.phash(img)
            width, height = img.size
            res_score = int((width * height) / 10000)

        cv_img = cv2.imread(image_path)
        if cv_img is None: return {'path': image_path, 'score': 0, 'hash': img_hash}

        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        sharpness = int(cv2.Laplacian(gray, cv2.CV_64F).var())
        
        # Simple composite score
        total_score = sharpness + res_score
        
        return {
            'path': image_path, 
            'hash': img_hash, 
            'score': total_score,
            'sharpness': sharpness,
            'res': f"{width}x{height}"
        }
    except:
        return {'path': image_path, 'score': 0, 'hash': None}

# --- 2. THE FILMSTRIP GENERATOR (VISUALS) ---

def create_filmstrip(cluster_items, target_height=500):
    """
    Stitches images side-by-side into a single PIL image.
    Draws scores and borders.
    """
    images = []
    
    # Try to load a nice font, else default
    try:
        font = ImageFont.truetype("arial.ttf", 40)
        small_font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Find best score to highlight
    best_score = max(item['score'] for item in cluster_items)

    for item in cluster_items:
        try:
            img = Image.open(item['path']).convert("RGB")
            
            # Resize to target height (500px) maintaining aspect ratio
            aspect_ratio = img.width / img.height
            new_width = int(target_height * aspect_ratio)
            img = img.resize((new_width, target_height))
            
            # Create a canvas with a border
            is_winner = (item['score'] == best_score)
            border_color = "#32CD32" if is_winner else "#FF4500" # Green vs Red
            
            # Add padding for border and text area at bottom
            canvas_h = target_height + 80 
            canvas_w = new_width + 20
            
            bordered = Image.new("RGB", (canvas_w, canvas_h), border_color)
            bordered.paste(img, (10, 10))
            
            # DRAW STATS
            draw = ImageDraw.Draw(bordered)
            
            # Text content
            status = "🏆 BEST" if is_winner else "Duplicate"
            stats_text = f"Score: {item['score']:.0f} | Sharpness: {item['sharpness']}"
            fname = os.path.basename(item['path'])
            
            # Draw text with simple shadow for readability
            text_x, text_y = 20, target_height + 20
            draw.text((text_x, text_y), status, font=font, fill="white")
            draw.text((text_x, text_y + 40), stats_text, font=small_font, fill="white")
            
            images.append(bordered)
        except:
            pass

    # Stitch them together
    if not images: return None
    
    total_width = sum(i.width for i in images)
    max_height = max(i.height for i in images)
    
    filmstrip = Image.new("RGB", (total_width, max_height), "#202020")
    
    current_x = 0
    for img in images:
        filmstrip.paste(img, (current_x, 0))
        current_x += img.width
        
    return filmstrip

# --- 3. SCANNING LOGIC (CACHED) ---

@st.cache_data(show_spinner=False)
def scan_structure(source_folder, threshold=16):
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.heic')
    all_files = [os.path.join(r, f) for r, _, fs in os.walk(source_folder) for f in fs]
    
    image_paths = [f for f in all_files if f.lower().endswith(valid_exts)]
    non_images = [f for f in all_files if not f.lower().endswith(valid_exts)]
    
    # Analysis
    analyzed = []
    bar = st.progress(0, text="Analyzing Image Quality...")
    for i, p in enumerate(image_paths):
        analyzed.append(calculate_score(p))
        if i % 10 == 0: bar.progress(i/len(image_paths))
    bar.empty()
    
    # Clustering
    clusters = []
    visited = set()
    analyzed.sort(key=lambda x: x['score'], reverse=True) # Best quality first
    
    c_bar = st.progress(0, text="Building Clusters...")
    for i, img_a in enumerate(analyzed):
        if img_a['path'] in visited: continue
        if img_a['hash'] is None: continue
        
        group = [img_a]
        visited.add(img_a['path'])
        
        for j in range(i+1, len(analyzed)):
            img_b = analyzed[j]
            if img_b['path'] in visited or img_b['hash'] is None: continue
            
            if (img_a['hash'] - img_b['hash']) <= threshold:
                group.append(img_b)
                visited.add(img_b['path'])
        
        if len(group) > 1:
            clusters.append(group)
        
        if i % 50 == 0: c_bar.progress(i/len(analyzed))
    c_bar.empty()
    
    # Orphans
    clustered_paths = set(item['path'] for group in clusters for item in group)
    orphans = [img for img in analyzed if img['path'] not in clustered_paths]
    
    return {"clusters": clusters, "orphans": orphans, "non_images": non_images}

# --- 4. ACTIONS ---

def move_group(winner_path, group):
    """Move winner to Keep, others to Discard."""
    fname = os.path.basename(winner_path)
    shutil.move(winner_path, os.path.join(KEEPERS_DIR, fname))
    
    for item in group:
        if item['path'] != winner_path and os.path.exists(item['path']):
            shutil.move(item['path'], os.path.join(DISCARDS_DIR, os.path.basename(item['path'])))

# --- 5. UI MAIN ---

st.title("🎞️ Visual Photo Curator")

# SIDEBAR SETUP
with st.sidebar:
    st.header("Setup")
    src = st.text_input("Source Folder", DEFAULT_SOURCE)
    thresh = st.slider("Strictness (Lower=Stricter)", 0, 30, 14)
    if st.button("🚀 START SCAN", type="primary"):
        if os.path.exists(src):
            st.session_state.data = scan_structure(src, thresh)
            st.session_state.idx = 0
            st.session_state.auto_done = False
            st.rerun()

# APP LOGIC
if 'data' in st.session_state:
    data = st.session_state.data
    clusters = data['clusters']
    
    # AUTO-MOVE PHASE
    if not st.session_state.auto_done:
        count_o = len(data['orphans'])
        count_n = len(data['non_images'])
        for o in data['orphans']: shutil.move(o['path'], os.path.join(KEEPERS_DIR, os.path.basename(o['path'])))
        for n in data['non_images']: shutil.move(n, os.path.join(KEEPERS_DIR, os.path.basename(n)))
        st.session_state.auto_done = True
        st.success(f"🧹 Auto-cleaned: {count_o} Singles & {count_n} Files moved to Safe Keeping.")
        st.rerun()

    # COUNTERS (Top of Screen)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Clusters", len(clusters))
    c2.metric("Remaining", len(clusters) - st.session_state.idx)
    c3.metric("Files in Keepers", len(os.listdir(KEEPERS_DIR)))
    
    st.divider()

    # FINISH CHECK
    if st.session_state.idx >= len(clusters):
        st.balloons()
        st.success("All sorted!")
        st.stop()

    # CURRENT CLUSTER
    group = clusters[st.session_state.idx]
    
    # 1. Generate Filmstrip
    st.subheader(f"Cluster {st.session_state.idx + 1}")
    filmstrip = create_filmstrip(group, target_height=500)
    if filmstrip:
        st.image(filmstrip, caption="Left: Best Quality | Right: Duplicates")
    
    # 2. Action Buttons (Aligned)
    st.write("#### Choose the Winner:")
    cols = st.columns(len(group))
    for i, col in enumerate(cols):
        item = group[i]
        fname = os.path.basename(item['path'])
        with col:
            if st.button(f"🏆 Keep This\n{fname}", key=item['path']):
                move_group(item['path'], group)
                st.session_state.idx += 1
                st.rerun()

    st.divider()
    if st.button("⏭️ Not sure? Skip for now"):
        st.session_state.idx += 1
        st.rerun()

else:
    st.info(f"Ready to scan '{DEFAULT_SOURCE}'. Adjust settings in Sidebar.")