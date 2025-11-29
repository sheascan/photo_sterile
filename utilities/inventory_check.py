import os
import sqlite3
from collections import Counter

# --- CONFIG ---
DB_FILE = "photo_library.db"
DIRS = {
    "INPUT": "./data/input_photos",
    "KEEPERS": "./sorted_photos/Keepers",
    "DISCARDS": "./sorted_photos/Discards",
    "ARCHIVE": "./data/archived_documents"
}

def count_files(directory):
    """Recursively counts images in a directory."""
    if not os.path.exists(directory):
        return 0
    count = 0
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.bmp')
    for root, _, files in os.walk(directory):
        for f in files:
            if f.lower().endswith(valid_exts):
                count += 1
    return count

def scan_subfolders(directory):
    """Returns a dict of subfolder names and their file counts."""
    if not os.path.exists(directory):
        return {}
    
    subfolder_counts = Counter()
    valid_exts = ('.jpg', '.jpeg', '.png', '.webp', '.heic', '.bmp')
    
    # We only look at immediate subfolders for the breakdown
    try:
        subdirs = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]
        
        # Add root files (files not in a subfolder)
        root_files = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f)) and f.lower().endswith(valid_exts)]
        if root_files:
            subfolder_counts["(Root Folder)"] = len(root_files)

        for sub in subdirs:
            full_path = os.path.join(directory, sub)
            count = count_files(full_path)
            if count > 0:
                subfolder_counts[sub] = count
    except: pass
            
    return subfolder_counts

def get_db_metrics():
    if not os.path.exists(DB_FILE):
        return 0, 0, 0
    
    conn = sqlite3.connect(DB_FILE)
    try:
        # Total files the DB knows about (should match Input Folder roughly)
        indexed = conn.execute("SELECT count(*) FROM images").fetchone()[0]
        
        # Total CLUSTERS (The number of unique "Moments" involved in conflicts)
        clusters = conn.execute("SELECT count(DISTINCT cluster_id) FROM clusters").fetchone()[0]
        
        # Total IMAGES in those clusters (The number of files at risk)
        files_in_conflict = conn.execute("SELECT count(*) FROM clusters").fetchone()[0]
    except:
        return 0, 0, 0
    finally:
        conn.close()
        
    return indexed, clusters, files_in_conflict

def print_report():
    print("\n📊 PHOTO DETECTIVE: BALANCE SHEET")
    print("=" * 50)
    
    # --- 1. PHYSICAL INVENTORY ---
    print(f"\n1. PHYSICAL LOCATION STATUS")
    print("-" * 50)
    
    current_input = count_files(DIRS["INPUT"])
    current_keepers = count_files(DIRS["KEEPERS"])
    current_discards = count_files(DIRS["DISCARDS"])
    current_archive = count_files(DIRS["ARCHIVE"])
    
    print(f"{'LOCATION':<30} | {'COUNT':<10}")
    print("-" * 45)
    print(f"{'Input Folder (Pending)':<30} | {current_input:<10}")
    print(f"{'Sorted Keepers (Safe)':<30} | {current_keepers:<10}")
    print(f"{'Sorted Discards (Trash)':<30} | {current_discards:<10}")
    print(f"{'Archived Docs (Safe)':<30} | {current_archive:<10}")
    
    total_assets = current_input + current_keepers + current_archive
    print("-" * 45)
    print(f"{'TOTAL LIBRARY ASSETS':<30} | {total_assets:<10}")

    # --- 2. SUBFOLDER BREAKDOWN ---
    print(f"\n\n2. INPUT FOLDER BREAKDOWN")
    print("-" * 50)
    sub_stats = scan_subfolders(DIRS["INPUT"])
    if not sub_stats:
        print("(No subfolders found)")
    else:
        # Sort by count descending
        for folder, count in sub_stats.most_common():
            print(f"{folder:<30} | {count:<10}")

    # --- 3. THE PREDICTION ---
    indexed, num_clusters, files_in_conflict = get_db_metrics()
    
    # THE MATH:
    # If we resolve a cluster, we keep 1 photo and discard the rest.
    # Discards = Total Files in Conflict - Total Number of Clusters
    projected_discards = files_in_conflict - num_clusters
    
    # Remaining in Input = Current Input - Projected Discards
    # (Assuming the conflicted files are currently in Input)
    final_input_count = current_input - projected_discards
    
    # Final Library Size = Keepers (already moved) + Archive (already moved) + Remaining Input
    final_library_size = current_keepers + current_archive + final_input_count

    print(f"\n\n3. THE FORECAST (If you prune all clusters)")
    print("=" * 50)
    print(f"Current Active Clusters:       {num_clusters}")
    print(f"Files involved in Clusters:    {files_in_conflict}")
    print("-" * 50)
    print(f"📉 Projected NEW Discards:     -{projected_discards}")
    print(f"📈 Projected Final Library:    {final_library_size}")
    print("=" * 50)
    print("Note: 'Projected Final Library' = Keepers + Archive + (Input - Duplicates)")

if __name__ == "__main__":
    print_report()