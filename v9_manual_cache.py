import streamlit as st
import os
import shutil
import cv2
import imagehash
import concurrent.futures
import pickle  # <--- NEW: For manual saving
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# --- SETUP ---
st.set_page_config(page_title="Photo Detective v9", layout="wide")
st.title("📸 Photo Detective v9: Visible Progress + Safety")
st.markdown("Real-time progress bar on first run. Instant load on restarts.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Configuration")
    source_folder = st.text_input("Source Folder Path", value="./data/input_photos")
    output_folder = st.text_input("Output Folder Path", value="./data/sorted_photos")
    st.divider()
    sim_threshold = st.slider("Similarity Threshold", 0, 30, 16)
    search_radius = st.slider("Time Search Radius (Days)", 1, 30, 10)
    st.divider()
    max_workers = st.slider("Speed (CPU Threads)", 1, 16, 4)
    st.divider()
    st.header("Report Viewer")
    items_per_page = st.number_input("Collages per Page", min_value=10, max_value=100, value=20)
    
    # CACHE CONTROL
    st.divider()
    st.markdown("**Cache Control**")
    if st.button("🗑️ Force Re-Scan (Delete Cache)"):
        if os.path.exists("scan_cache.pkl"):
            os.remove("scan_cache.pkl")
            st.success("Cache deleted. Click Start to re-scan.")
            st.rerun()
    
    valid_source = os.path.exists(source_folder)
    if valid_source:
        run_button = st.button("🚀 Start Processing", type="primary")

# --- HELPER FUNCTIONS ---

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
    return abs((dt_a - dt_b).days) <= radius

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
            aspect = img.width / img.height
            new_w = int(target_height * aspect)
            img = img.resize((new_w, target_height))
            color = "#32CD32" if item['is_winner'] else "#FF4500" 
            bordered = Image.new("RGB", (new_w + 20, target_height + 60), color)
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
        total_w = sum(i.width for i in images)
        composite = Image.new("RGB", (total_w, target_height + 60), "#202020")
        cx = 0
        for img in images:
            composite.paste(img, (cx, 0))
            cx += img.width
        save_path = os.path.join(output_folder, "Review_Collages", f"cluster_{cluster_id:03d}.jpg")
        composite.save(save_path)
        return save_path
    return None

# --- MANUAL CACHE MANAGER ---

def get_data_with_progress(folder, workers):
    """
    Logic:
    1. Check for 'scan_cache.pkl'.
    2. If found, load and return (FAST).
    3. If not found, SCAN with PROGRESS BAR, save, and return (SLOW).
    """
    cache_file = "scan_cache.pkl"
    
    # OPTION A: LOAD FROM CACHE
    if os.path.exists(cache_file):
        st.info(f"⚡ Found cached data ({cache_file}). Loading instantly...")
        with open(cache_file, "rb") as f:
            data = pickle.load(f)
        return data['analyzed'], data['non_images']

    # OPTION B: FRESH SCAN
    st.write("📂 Scanning file structure...")
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
    all_image_files = []
    non_image_files = []
    
    for root, _, filenames in os.walk(folder):
        for f in filenames:
            path = os.path.join(root, f)
            if f.lower().endswith(valid_exts):
                all_image_files.append(path)
            else:
                non_image_files.append(path)
                
    st.info(f"Found {len(all_image_files)} images. Analyzing...")
    
    analyzed_list = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Multithreaded Analysis
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_file = {executor.submit(calculate_stats, f): f for f in all_image_files}
        
        for i, future in enumerate(concurrent.futures.as_completed(future_to_file)):
            stats = future.result()
            if stats: analyzed_list.append(stats)
            
            # UPDATE PROGRESS
            pct = (i + 1) / len(all_image_files)
            progress_bar.progress(pct)
            if i % 50 == 0:
                status_text.text(f"Analyzed {i+1} / {len(all_image_files)}...")
    
    status_text.text("✅ Analysis Complete. Saving Cache to Disk...")
    
    # SAVE TO CACHE
    with open(cache_file, "wb") as f:
        pickle.dump({'analyzed': analyzed_list, 'non_images': non_image_files}, f)
        
    return analyzed_list, non_image_files

# --- MAIN APP LOGIC ---

if 'page_number' not in st.session_state: st.session_state.page_number = 1
if 'report_data' not in st.session_state: st.session_state.report_data = []
if 'last_thresh' not in st.session_state: st.session_state.last_thresh = -1

if run_button or st.session_state.get('has_run', False):
    st.session_state.has_run = True
    
    # 1. GET DATA (Manually Cached with Progress)
    try:
        analyzed_list, non_image_files = get_data_with_progress(source_folder, max_workers)
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

    # 2. CLUSTERING (Real-time)
    if sim_threshold != st.session_state.last_thresh or not st.session_state.report_data:
        st.session_state.last_thresh = sim_threshold
        
        with st.spinner("Grouping Duplicates..."):
            if os.path.exists(output_folder): shutil.rmtree(output_folder)
            for p in ['Keep', 'Discard', 'Review_Collages']: os.makedirs(os.path.join(output_folder, p))

            analyzed_list.sort(key=lambda x: x['total_score'], reverse=True)
            
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
                        if are_time_compatible_strict(img_a, img_b, search_radius): match = True
                    if match:
                        current_cluster.append(img_b)
                        visited.add(img_b['path'])
                if len(current_cluster) > 1:
                    clusters.append(current_cluster)
                    for c_img in current_cluster: clustered_paths.add(c_img['path'])

            trash_count = 0
            winners_count = 0
            new_report = []
            
            for idx, cluster in enumerate(clusters):
                winner = max(cluster, key=lambda x: x['total_score'])
                winners_count += 1
                for img in cluster:
                    img['is_winner'] = (img == winner) 
                    dest = "Keep" if img['is_winner'] else "Discard"
                    shutil.copy2(img['path'], os.path.join(output_folder, dest, os.path.basename(img['path'])))
                    if not img['is_winner']: trash_count += 1
                
                c_path = create_collage(cluster, idx+1, output_folder)
                if c_path: new_report.append({"id": idx+1, "path": c_path, "count": len(cluster)})
            
            singles = 0
            for img in analyzed_list:
                if img['path'] not in clustered_paths:
                    shutil.copy2(img['path'], os.path.join(output_folder, "Keep", os.path.basename(img['path'])))
                    singles += 1
            videos = 0
            for f in non_image_files:
                shutil.copy2(f, os.path.join(output_folder, "Keep", os.path.basename(f)))
                videos += 1

            st.session_state.report_data = new_report
            st.session_state.report_stats = {
                "trash": trash_count, "winners": winners_count,
                "orphans": singles, "videos": videos
            }
            st.session_state.page_number = 1 

# --- VIEWER ---
if st.session_state.report_data:
    stats = st.session_state.report_stats
    st.divider()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Moved to Trash", stats.get('trash', 0))
    c2.metric("Cluster Winners", stats.get('winners', 0))
    c3.metric("Orphans", stats.get('orphans', 0))
    c4.metric("Videos", stats.get('videos', 0))
    st.divider()

    total_items = len(st.session_state.report_data)
    if total_items > 0:
        total_pages = (total_items - 1) // items_per_page + 1
        
        col_prev_t, col_page_t, col_next_t = st.columns([1, 2, 1])
        with col_prev_t:
            if st.button("⬅️ Previous", key="prev_top") and st.session_state.page_number > 1:
                st.session_state.page_number -= 1
                st.rerun()
        with col_page_t:
            st.markdown(f"**Page {st.session_state.page_number} of {total_pages}**")
        with col_next_t:
            if st.button("Next ➡️", key="next_top") and st.session_state.page_number < total_pages:
                st.session_state.page_number += 1
                st.rerun()

        start_idx = (st.session_state.page_number - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_slice = st.session_state.report_data[start_idx:end_idx]
        
        st.subheader(f"Clusters {start_idx + 1} - {min(end_idx, total_items)}")
        for item in current_slice:
            try:
                st.image(item['path'], caption=f"Cluster #{item['id']} ({item['count']} images)", use_container_width=True)
            except: st.warning("Image load error")

        st.divider()
        col_prev_b, col_page_b, col_next_b = st.columns([1, 2, 1])
        with col_prev_b:
            if st.button("⬅️ Previous", key="prev_btm") and st.session_state.page_number > 1:
                st.session_state.page_number -= 1
                st.rerun()
        with col_page_b:
             st.markdown(f"**Page {st.session_state.page_number} of {total_pages}**")
        with col_next_b:
            if st.button("Next ➡️", key="next_btm") and st.session_state.page_number < total_pages:
                st.session_state.page_number += 1
                st.rerun()
    else:
        st.info("No duplicates found.")