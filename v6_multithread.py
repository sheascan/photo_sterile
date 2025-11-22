import streamlit as st
import os
import shutil
import cv2
import imagehash
import concurrent.futures
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ExifTags

# --- SETUP THE APP LAYOUT ---
st.set_page_config(page_title="Photo Detective v6 (Fixed)", layout="wide")
st.title("📸 Photo Detective v6: Multithreaded (Fixed)")
st.markdown("Same logic as v5, but running parallel workers with REAL-TIME progress.")

# --- SIDEBAR PARAMETERS ---
with st.sidebar:
    st.header("Configuration")
    source_folder = st.text_input("Source Folder Path", value="./input_photos")
    output_folder = st.text_input("Output Folder Path", value="./sorted_photos")
    st.divider()
    sim_threshold = st.slider("Similarity Threshold", 0, 30, 16)
    search_radius = st.slider("Time Search Radius (Days)", 1, 30, 10)
    st.divider()
    max_workers = st.slider("Speed (CPU Threads)", 1, 16, 4)
    run_button = st.button("🚀 Start Scanning", type="primary")

# --- CORE LOGIC (UNCHANGED FROM v5) ---

def get_date_taken(path):
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif: return None
            date_str = exif.get(36867) or exif.get(306)
            if date_str: return date_str 
    except: return None
    return None

def parse_date_string(date_str):
    if not date_str: return None
    try: return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
    except: return None

def calculate_stats(image_path):
    try:
        pil_img = Image.open(image_path)
        img_hash_obj = imagehash.phash(pil_img)
        
        cv_img = cv2.imread(image_path)
        if cv_img is None: return None
        
        gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        sharpness = int(cv2.Laplacian(gray, cv2.CV_64F).var())
        
        hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
        saturation = int(hsv[:, :, 1].mean())
        
        h, w, _ = cv_img.shape
        res_score = int((h * w) / 10000)
        
        return {
            'path': image_path,
            'hash_obj': img_hash_obj, 
            'sharpness': sharpness,
            'saturation': saturation,
            'res': res_score,
            'date_str': get_date_taken(image_path),
            'total_score': sharpness + res_score + (saturation * 0.5)
        }
    except: return None

def are_time_compatible_strict(data_a, data_b, radius):
    dt_a = parse_date_string(data_a['date_str'])
    dt_b = parse_date_string(data_b['date_str'])
    if dt_a is None or dt_b is None: return False
    diff = abs((dt_a - dt_b).days)
    return diff <= radius

def create_collage(cluster_data, cluster_id, output_folder):
    images = []
    try:
        try: font = ImageFont.truetype("arial.ttf", 30)
        except: font = ImageFont.load_default()
    except IOError: font = ImageFont.load_default()

    target_height = 450 
    sorted_cluster = sorted(cluster_data, key=lambda x: x['is_winner'], reverse=True)

    for item in sorted_cluster:
        try:
            img = Image.open(item['path']).convert("RGB")
            aspect_ratio = img.width / img.height
            new_width = int(target_height * aspect_ratio)
            img = img.resize((new_width, target_height))
            
            color = "#32CD32" if item['is_winner'] else "#FF4500" 
            bordered = Image.new("RGB", (new_width + 20, target_height + 60), color)
            bordered.paste(img, (10, 10))
            
            draw = ImageDraw.Draw(bordered)
            status = "WINNER" if item['is_winner'] else "TRASH"
            text = f"{status}\nScore:{int(item['total_score'])}\nSharp:{item['sharpness']}"
            
            x, y = 20, 20
            draw.text((x-1, y-1), text, font=font, fill="black")
            draw.text((x+1, y+1), text, font=font, fill="black")
            draw.text((x, y), text, font=font, fill="white")
            
            images.append(bordered)
        except: pass

    if images:
        total_width = sum(i.width for i in images)
        composite = Image.new("RGB", (total_width, target_height + 60), "#202020")
        current_x = 0
        for img in images:
            composite.paste(img, (current_x, 0))
            current_x += img.width
        save_path = os.path.join(output_folder, "Review_Collages", f"cluster_{cluster_id:03d}.jpg")
        composite.save(save_path)
        return composite
    return None

# --- MAIN PROCESS ---
if run_button:
    if not os.path.exists(source_folder):
        st.error(f"Source folder not found: {source_folder}")
    else:
        if os.path.exists(output_folder):
            shutil.rmtree(output_folder)
        for p in ['Keep', 'Discard', 'Review_Collages']:
            os.makedirs(os.path.join(output_folder, p))

        valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
        all_image_files = []
        non_image_files = []
        
        for root, _, filenames in os.walk(source_folder):
            for f in filenames:
                full_path = os.path.join(root, f)
                if f.lower().endswith(valid_exts):
                    all_image_files.append(full_path)
                else:
                    non_image_files.append(full_path)
        
        st.info(f"Found {len(all_image_files)} images. Launching {max_workers} threads...")
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        analyzed_list = []
        
        # --- THE FIXED MULTITHREADING BLOCK ---
        # We use 'as_completed' so we can update the bar as each image finishes
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_file = {executor.submit(calculate_stats, f): f for f in all_image_files}
            
            for i, future in enumerate(concurrent.futures.as_completed(future_to_file)):
                stats = future.result()
                if stats:
                    analyzed_list.append(stats)
                
                # Update Progress Bar Live
                pct = (i + 1) / len(all_image_files)
                progress_bar.progress(pct)
                if i % 10 == 0:
                    status_text.text(f"Analyzed {i+1} / {len(all_image_files)} images...")
        
        status_text.empty()
        # -------------------------------------
            
        st.success("Analysis Complete. Clustering...")
        
        # --- CLUSTERING (EXACTLY v5 LOGIC) ---
        clusters = []
        visited = set()
        clustered_paths = set() 
        
        for i, img_a in enumerate(analyzed_list):
            if img_a['path'] in visited: continue
            current_cluster = [img_a]
            visited.add(img_a['path'])
            
            for j, img_b in enumerate(analyzed_list):
                if img_b['path'] in visited: continue
                
                sim = img_a['hash_obj'] - img_b['hash_obj']
                match = False
                
                if sim <= 10: match = True
                elif sim <= sim_threshold:
                    if are_time_compatible_strict(img_a, img_b, search_radius):
                        match = True
                
                if match:
                    current_cluster.append(img_b)
                    visited.add(img_b['path'])
            
            if len(current_cluster) > 1:
                clusters.append(current_cluster)
                for c_img in current_cluster:
                    clustered_paths.add(c_img['path'])

        # Sort, Save, Collage
        trash_count = 0
        cluster_winners_count = 0
        
        st.divider()
        st.subheader(f"🔎 Reviewing {len(clusters)} Clusters")
        
        for idx, cluster in enumerate(clusters):
            winner = max(cluster, key=lambda x: x['total_score'])
            cluster_winners_count += 1
            
            for img in cluster:
                img['is_winner'] = (img == winner) 
                dest = "Keep" if img['is_winner'] else "Discard"
                shutil.copy2(img['path'], os.path.join(output_folder, dest, os.path.basename(img['path'])))
                if not img['is_winner']: trash_count += 1

            collage = create_collage(cluster, idx+1, output_folder)
            if collage:
                st.image(collage, caption=f"Cluster #{idx+1}", width=700)

        singles_count = 0
        for img in analyzed_list:
            if img['path'] not in clustered_paths:
                shutil.copy2(img['path'], os.path.join(output_folder, "Keep", os.path.basename(img['path'])))
                singles_count += 1
                
        non_image_count = 0
        for f_path in non_image_files:
            shutil.copy2(f_path, os.path.join(output_folder, "Keep", os.path.basename(f_path)))
            non_image_count += 1
        
        total_kept = cluster_winners_count + singles_count + non_image_count
        
        st.balloons()
        st.success(f"Processing Complete! (Used {max_workers} Threads)")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Moved to Trash", trash_count)
        with col2: st.metric("Cluster Winners", cluster_winners_count)
        with col3: st.metric("Orphans (Saved)", singles_count)
        with col4: st.metric("Videos/Other", non_image_count)