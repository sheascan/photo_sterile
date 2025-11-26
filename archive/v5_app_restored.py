import streamlit as st
import os
import shutil
import cv2
import imagehash
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ExifTags

# --- CONFIGURATION ---
DEFAULT_SOURCE = "input_photos"
OUTPUT_BASE = "sorted_photos"

# Folders for our workflow
KEEPERS_DIR = os.path.join(OUTPUT_BASE, "Keepers")
DISCARDS_DIR = os.path.join(OUTPUT_BASE, "Discards")
COLLAGE_DIR = os.path.join(OUTPUT_BASE, "Review_Collages")

for d in [KEEPERS_DIR, DISCARDS_DIR, COLLAGE_DIR]:
    os.makedirs(d, exist_ok=True)

st.set_page_config(layout="wide", page_title="v5 Logic Restored")

# --- 1. v5 LOGIC: DATE & EXIF ---
def get_date_taken(path):
    """Extracts EXIF Date to prevent clustering photos from different years."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif: return None
            # Tags 36867 or 306 usually hold the date string
            date_str = exif.get(36867) or exif.get(306)
            if date_str: return date_str 
    except: return None
    return None

def parse_date_string(date_str):
    if not date_str: return None
    try: return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except: return None

def are_time_compatible(data_a, data_b, radius_days=10):
    """Returns True if images are within 'radius_days' of each other."""
    dt_a = parse_date_string(data_a['date_str'])
    dt_b = parse_date_string(data_b['date_str'])
    
    # If one lacks a date, we assume they might be compatible (loose matching)
    if dt_a is None or dt_b is None: return True
    
    diff = abs((dt_a - dt_b).days)
    return diff <= radius_days

# --- 2. v5 LOGIC: SCORING & HASHING ---
def calculate_stats(image_path):
    """
    The original v5 logic:
    - pHash (Perceptual Hash)
    - CV2 Laplacian (Sharpness)
    - HSV (Saturation)
    """
    try:
        # 1. PIL for Hashing & EXIF
        pil_img = Image.open(image_path)
        img_hash = imagehash.phash(pil_img) # v5 used phash (better than average_hash)
        date_str = get_date_taken(image_path)
        
        # 2. CV2 for Quality Stats
        cv_img = cv2.imread(image_path)
        if cv_img is None: return None
        
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        sharpness = int(cv2.Laplacian(gray, cv2.CV_64F).var())
        
        hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
        saturation = int(hsv[:, :, 1].mean())
        
        h, w, _ = cv_img.shape
        res_score = int((h * w) / 10000)
        
        # v5 Composite Score
        total_score = sharpness + res_score + (saturation * 0.5)
        
        return {
            'path': image_path,
            'hash': img_hash,
            'sharpness': sharpness,
            'date_str': date_str,
            'total_score': total_score,
            'res': f"{w}x{h}"
        }
    except Exception:
        return None

# --- 3. v5 LOGIC: COLLAGE GENERATOR (SAVING TO DISK) ---
def create_and_save_collage(cluster_data, cluster_id):
    """
    Generates the side-by-side strip and SAVES it to disk.
    This allows you to check 'Review_Collages' folder for debugging.
    """
    target_height = 500
    images = []
    
    try:
        font = ImageFont.truetype("arial.ttf", 40)
        small_font = ImageFont.truetype("arial.ttf", 24)
    except:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()

    # Sort by score (Best on left)
    sorted_cluster = sorted(cluster_data, key=lambda x: x['total_score'], reverse=True)
    best_score = sorted_cluster[0]['total_score']

    for item in sorted_cluster:
        try:
            img = Image.open(item['path']).convert("RGB")
            aspect = img.width / img.height
            new_w = int(target_height * aspect)
            img = img.resize((new_w, target_height))
            
            # Border Color (Green for Winner, Red for Loser)
            is_winner = (item['total_score'] == best_score)
            color = "#32CD32" if is_winner else "#FF4500"
            
            canvas = Image.new("RGB", (new_w + 20, target_height + 80), color)
            canvas.paste(img, (10, 10))
            
            draw = ImageDraw.Draw(canvas)
            label = "WINNER" if is_winner else "Trash"
            info = f"Score:{int(item['total_score'])} | Sharp:{item['sharpness']}"
            if item['date_str']:
                info += f"\nDate: {item['date_str']}"
            
            draw.text((20, target_height + 20), label, font=font, fill="white")
            draw.text((20, target_height + 55), info, font=small_font, fill="white")
            
            images.append(canvas)
        except: pass

    if not images: return None

    # Stitch
    total_w = sum(i.width for i in images)
    collage = Image.new("RGB", (total_w, target_height + 80), "#202020")
    x_off = 0
    for i in images:
        collage.paste(i, (x_off, 0))
        x_off += i.width
        
    # Save to Disk (The Feature You Wanted)
    filename = f"Cluster_{cluster_id:04d}.jpg"
    save_path = os.path.join(COLLAGE_DIR, filename)
    collage.save(save_path)
    
    return save_path # Return path so app can display it

# --- 4. THE SCAN ENGINE ---

@st.cache_data(show_spinner=False)
def run_v5_engine(source_dir, threshold=16, time_radius=10):
    """
    Replicates the nested loop logic of v5.
    """
    # A. Scan Files
    st.write("📂 Scanning file list...")
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
    image_files = []
    non_image_files = []
    
    for r, _, fs in os.walk(source_dir):
        for f in fs:
            path = os.path.join(r, f)
            if f.lower().endswith(valid_exts):
                image_files.append(path)
            else:
                non_image_files.append(path)
                
    # B. Analyze (Stats)
    analyzed = []
    prog_bar = st.progress(0)
    status = st.empty()
    
    for i, p in enumerate(image_files):
        if i % 5 == 0:
            prog_bar.progress((i+1)/len(image_files))
            status.text(f"Analyzing {i+1}/{len(image_files)}...")
        stats = calculate_stats(p)
        if stats: analyzed.append(stats)
        
    prog_bar.empty()
    status.text("✅ Analysis done. Clustering...")
    
    # C. Cluster (The v5 Nested Loop)
    clusters = []
    visited = set()
    
    # Sort by quality first
    analyzed.sort(key=lambda x: x['total_score'], reverse=True)
    
    c_bar = st.progress(0)
    
    for i, img_a in enumerate(analyzed):
        if img_a['path'] in visited: continue
        
        group = [img_a]
        visited.add(img_a['path'])
        
        for j in range(i+1, len(analyzed)):
            img_b = analyzed[j]
            if img_b['path'] in visited: continue
            
            # The v5 Logic: Hash Check + Time Check
            sim = img_a['hash'] - img_b['hash']
            is_match = False
            
            if sim <= threshold:
                if are_time_compatible(img_a, img_b, time_radius):
                    is_match = True
                    
            if is_match:
                group.append(img_b)
                visited.add(img_b['path'])
        
        if len(group) > 1:
            clusters.append(group)
            
        if i % 10 == 0: c_bar.progress((i+1)/len(analyzed))
        
    c_bar.empty()
    status.empty()
    
    # D. Identify Orphans
    clustered_paths = set(item['path'] for group in clusters for item in group)
    orphans = [img for img in analyzed if img['path'] not in clustered_paths]
    
    return {
        "clusters": clusters,
        "orphans": orphans,
        "non_images": non_image_files
    }

# --- 5. UI & ACTIONS ---

def apply_decision(winner_path, group):
    fname = os.path.basename(winner_path)
    shutil.move(winner_path, os.path.join(KEEPERS_DIR, fname))
    for item in group:
        if item['path'] != winner_path and os.path.exists(item['path']):
            shutil.move(item['path'], os.path.join(DISCARDS_DIR, os.path.basename(item['path'])))

st.title("📸 v5 Logic: The Robust Restorer")

with st.sidebar:
    st.header("v5 Parameters")
    src_folder = st.text_input("Source", DEFAULT_SOURCE)
    sim_thresh = st.slider("Similarity (Default 16)", 0, 30, 16)
    time_rad = st.slider("Time Radius (Days)", 1, 365, 10)
    
    st.divider()
    if st.button("🚀 START ANALYSIS", type="primary"):
        if os.path.exists(src_folder):
            st.session_state.v5_data = run_v5_engine(src_folder, sim_thresh, time_rad)
            st.session_state.v5_idx = 0
            st.session_state.v5_auto_done = False
            st.rerun()
        else:
            st.error("Folder not found.")

if 'v5_data' in st.session_state:
    data = st.session_state.v5_data
    clusters = data['clusters']
    
    # --- PHASE 1: AUTOMATION (Singles/Videos) ---
    if not st.session_state.v5_auto_done:
        # Move Orphans & Non-Images immediately (Clean the room)
        for o in data['orphans']:
            shutil.move(o['path'], os.path.join(KEEPERS_DIR, os.path.basename(o['path'])))
        for n in data['non_images']:
            shutil.move(n, os.path.join(KEEPERS_DIR, os.path.basename(n)))
            
        st.session_state.v5_auto_done = True
        st.success(f"Auto-Cleaned: {len(data['orphans'])} Singles and {len(data['non_images'])} Videos moved to Safe Keeping.")
        st.rerun()

    # --- PHASE 2: REVIEW ---
    if st.session_state.v5_idx >= len(clusters):
        st.balloons()
        st.success("Processing Complete!")
        st.stop()

    group = clusters[st.session_state.v5_idx]
    
    # COUNTERS
    c1, c2, c3 = st.columns(3)
    c1.metric("Clusters Found", len(clusters))
    c2.metric("Reviewing", f"{st.session_state.v5_idx + 1} / {len(clusters)}")
    c3.metric("Files in Output", len(os.listdir(KEEPERS_DIR)))
    
    st.divider()
    
    # DISPLAY (Generate the Collage ONCE and save it)
    collage_path = create_and_save_collage(group, st.session_state.v5_idx)
    if collage_path:
        st.image(collage_path, caption=f"Saved to: {collage_path}")
    
    st.write("### Action")
    
    # Find the 'Calculated' Winner (Best Score)
    best_item = max(group, key=lambda x: x['total_score'])
    
    col_left, col_right = st.columns([1, 4])
    
    with col_left:
        if st.button(f"✅ Confirm Auto-Winner", type="primary"):
            apply_decision(best_item['path'], group)
            st.session_state.v5_idx += 1
            st.rerun()
            
    with col_right:
        # Allow swapping if the auto-logic failed
        with st.expander("Swap Winner (If Auto is wrong)"):
            for item in group:
                if st.button(f"🏆 Keep {os.path.basename(item['path'])} instead"):
                    apply_decision(item['path'], group)
                    st.session_state.v5_idx += 1
                    st.rerun()
else:
    st.info("Waiting to run. Check settings on left.")