import os
import re
import shutil
import sqlite3
from collections import Counter

# --- CONFIG ---
DB_FILE = "photo_library.db"
OUTPUT_DIR = "sorted_photos"
MIN_TOTAL_FILES = 10  # Lowered safety slightly to catch smaller batches

# --- HELPERS ---

def get_pattern_prefix(filename):
    """Extracts prefix for grouping."""
    if "IMG" in filename: return None
    if "Screenshot" in filename: return None
    if "2023-08" in filename: return None 
    
    # Ignore Date-Stamp filenames (YYYYMMDD_HHMMSS)
    if re.match(r'^(19|20)\d{6}', filename): return None
    
    # REGEX: At least 2 chars, separator, digits
    # Captures "1997" from "1997-001"
    match = re.match(r'^(.{2,})[-_]\d+', filename)
    
    if match:
        prefix = match.group(1)
        return prefix
    return None

def extract_sort_key(filename):
    year_match = re.search(r'(19\d{2}|20\d{2})', filename)
    year = int(year_match.group(1)) if year_match else 9999
    
    seq_match = re.findall(r'\d+', filename)
    seq = int(seq_match[-1]) if seq_match else 999999
    
    return (year, seq)

# --- STAGE 1: AUDIT ---

def scan_database_for_targets():
    if not os.path.exists(DB_FILE):
        print(f"❌ Critical Error: Database file '{DB_FILE}' not found.")
        return []

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # DIAGNOSTIC 1: Check Cluster Count
    try:
        cluster_count = cursor.execute("SELECT count(*) FROM clusters").fetchone()[0]
        print(f"\n📊 Database Status: Found {cluster_count} active duplicate pairs in 'clusters' table.")
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return []

    if cluster_count == 0:
        print("\n⚠️  THE SNIPER HAS NO TARGETS.")
        print("   Reason: The 'clusters' table is empty.")
        print("   Solution: Run 'streamlit run app.py' and click 'Find Global Duplicates' first.")
        return []

    # Proceed if clusters exist
    print(f"🎯 Scanning {cluster_count} duplicates for patterns...")
    
    all_paths = [row[0] for row in cursor.execute("SELECT path FROM images").fetchall()]
    total_prefix_counts = Counter()
    for p in all_paths:
        prefix = get_pattern_prefix(os.path.basename(p))
        if prefix: total_prefix_counts[prefix] += 1
            
    query = "SELECT images.path FROM clusters JOIN images ON clusters.image_id = images.id"
    cluster_paths = [row[0] for row in cursor.execute(query).fetchall()]
    
    cluster_prefix_counts = Counter()
    for p in cluster_paths:
        prefix = get_pattern_prefix(os.path.basename(p))
        if prefix: cluster_prefix_counts[prefix] += 1
            
    conn.close()
    
    valid_targets = []
    
    # Header
    print(f"\n{'ID':<4} | {'PREFIX':<20} | {'TOTAL FILES':<12} | {'DUPLICATES':<10}")
    print("-" * 55)
    
    sorted_prefixes = sorted(cluster_prefix_counts.keys(), key=lambda x: total_prefix_counts[x], reverse=True)
    
    display_idx = 1
    for prefix in sorted_prefixes:
        total = total_prefix_counts[prefix]
        
        if total >= MIN_TOTAL_FILES:
            dupes = cluster_prefix_counts[prefix]
            print(f"{display_idx:<4} | {prefix:<20} | {total:<12} | {dupes:<10}")
            valid_targets.append(prefix)
            display_idx += 1
            
    if not valid_targets:
        print(f"Clusters exist, but no prefixes matched your filter (> {MIN_TOTAL_FILES} total files).")
        return []
        
    return valid_targets

# --- STAGE 2 & 3 (Unchanged Logic) ---

def scout_target(target_prefix):
    print(f"\n🕵️  Scouting clusters involving '{target_prefix}'...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    c_ids = [x[0] for x in cursor.execute("SELECT DISTINCT cluster_id FROM clusters").fetchall()]
    
    affected_clusters = []
    print(f"\n{'WINNER (Keep)':<35} | {'LOSER (Discard)':<35}")
    print("-" * 75)
    
    for cid in c_ids:
        query = "SELECT images.path FROM clusters JOIN images ON clusters.image_id = images.id WHERE clusters.cluster_id = ?"
        paths = [row[0] for row in cursor.execute(query, (cid,)).fetchall()]
        
        if any(target_prefix in os.path.basename(p) for p in paths):
            paths.sort(key=lambda p: extract_sort_key(os.path.basename(p)))
            winner = paths[0]
            losers = paths[1:]
            w_name = os.path.basename(winner)
            l_name = os.path.basename(losers[0]) if losers else "---"
            print(f"{w_name:<35} | {l_name:<35}")
            affected_clusters.append((cid, winner, losers))
            
    conn.close()
    return affected_clusters

def fire_sniper(cluster_data):
    if not cluster_data: return
    print(f"\n🔫 Ready to resolve {len(cluster_data)} clusters.")
    confirm = input("Type 'fire' to execute moves to Discards: ")
    
    if confirm.lower() != 'fire':
        print("Aborted.")
        return
        
    print("Firing...")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    keep_dir = os.path.join(OUTPUT_DIR, "Keepers")
    disc_dir = os.path.join(OUTPUT_DIR, "Discards")
    os.makedirs(keep_dir, exist_ok=True)
    os.makedirs(disc_dir, exist_ok=True)
    
    shots = 0
    for cid, winner, losers in cluster_data:
        try: shutil.move(winner, os.path.join(keep_dir, os.path.basename(winner)))
        except: pass
        for l in losers:
            if os.path.exists(l):
                try:
                    shutil.move(l, os.path.join(disc_dir, os.path.basename(l)))
                    shots += 1
                except: pass
        cursor.execute("DELETE FROM clusters WHERE cluster_id = ?", (cid,))
        
    conn.commit()
    conn.close()
    print(f"✅ Done. {shots} files moved to Discards.")

def main():
    while True:
        targets = scan_database_for_targets()
        if not targets: break
        
        choice = input("\nEnter ID or PREFIX to target (or 'q' to quit): ")
        if choice.lower() == 'q': break
        
        target = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(targets): target = targets[idx]
        elif choice in targets: target = choice
        
        if target:
            data = scout_target(target)
            if data: fire_sniper(data)
            else: input("No actions available. Press Enter...")
        else: print("Invalid selection.")

if __name__ == "__main__":
    main()