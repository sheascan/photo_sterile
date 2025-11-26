import streamlit as st
import os
import shutil
from PIL import Image
from send2trash import send2trash

# --- CONFIGURATION ---
CLUSTER_DIR = "clusters"      # Where your grouped duplicate folders are
OUTPUT_DIR = "final_album"    # Where the "winners" go
# ---------------------

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

st.set_page_config(layout="wide", page_title="High-Perf Photo Curator")

# --- HELPER FUNCTIONS ---

def get_clusters():
    """Scans the directory for subfolders (clusters)."""
    if not os.path.exists(CLUSTER_DIR):
        return []
    # Get all subdirectories that contain images
    clusters = [f.path for f in os.scandir(CLUSTER_DIR) if f.is_dir()]
    # Sort them so order is consistent
    return sorted(clusters)

def load_images_in_cluster(cluster_path):
    """Loads image paths from a specific cluster folder."""
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp')
    files = [
        os.path.join(cluster_path, f) 
        for f in os.listdir(cluster_path) 
        if f.lower().endswith(valid_exts)
    ]
    return sorted(files)

def finalize_cluster(keeper_path, cluster_path, all_images):
    """Moves the winner to Final Album, trashes the rest, removes empty cluster folder."""
    
    # 1. Move the Keeper
    file_name = os.path.basename(keeper_path)
    dest_path = os.path.join(OUTPUT_DIR, file_name)
    
    # Handle name collisions in destination
    if os.path.exists(dest_path):
        base, ext = os.path.splitext(file_name)
        dest_path = os.path.join(OUTPUT_DIR, f"{base}_copy{ext}")
        
    shutil.move(keeper_path, dest_path)
    
    # 2. Trash the Rejects (everything else in the list)
    for img in all_images:
        if img != keeper_path and os.path.exists(img):
            send2trash(img) # Safely send to Recycle Bin
            
    # 3. Remove the now empty cluster folder
    if os.path.exists(cluster_path):
        # Check if empty before removing to be safe
        if not os.listdir(cluster_path):
            os.rmdir(cluster_path)
        else:
            # If random non-image files remain, send folder to trash
            send2trash(cluster_path)

# --- APP LOGIC ---

st.title("📸 High-Perf Curator")

# Initialize Session State to track progress
if 'cluster_index' not in st.session_state:
    st.session_state.cluster_index = 0

# Load directory structure
all_clusters = get_clusters()

if not all_clusters:
    st.success(f"🎉 No clusters found in '{CLUSTER_DIR}'. You are done!")
    st.stop()

# Check if we are out of bounds (finished)
if st.session_state.cluster_index >= len(all_clusters):
    st.balloons()
    st.success("All clusters reviewed!")
    if st.button("Restart Review"):
        st.session_state.cluster_index = 0
        st.rerun()
    st.stop()

# Get current cluster
current_cluster_path = all_clusters[st.session_state.cluster_index]
current_images = load_images_in_cluster(current_cluster_path)

# If a folder is empty or invalid, skip it automatically
if not current_images:
    st.session_state.cluster_index += 1
    st.rerun()

# --- UI LAYOUT ---

st.write(f"**Reviewing Cluster {st.session_state.cluster_index + 1} of {len(all_clusters)}**")
st.caption(f"Location: `{current_cluster_path}`")

# Create a grid of columns equal to the number of images (max 4 per row ideally, but flexible)
cols = st.columns(len(current_images))

for idx, col in enumerate(cols):
    img_path = current_images[idx]
    img_name = os.path.basename(img_path)
    
    with col:
        # Display Image
        try:
            image = Image.open(img_path)
            # Resize for display performance (thumbnails)
            image.thumbnail((400, 400)) 
            st.image(image, use_container_width=True)
        except Exception as e:
            st.error(f"Error loading {img_name}")

        # The "Keep This One" Button
        if st.button(f"🏆 Keep\n{img_name}", key=img_path):
            finalize_cluster(img_path, current_cluster_path, current_images)
            # Move to next cluster automatically (creating a new list on rerun)
            # Note: We don't increment index because the current folder is now gone,
            # so the next folder in the list effectively slides into this index.
            st.rerun()

# Option to skip cluster (keep all for later)
st.divider()
if st.button("⏭️ Skip this Cluster (Keep All)"):
    st.session_state.cluster_index += 1
    st.rerun()