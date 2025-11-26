import os
import re
import shutil
import sqlite3
from collections import Counter

# --- CONFIG ---
DB_FILE = "photo_library.db"
TARGET_FOLDER = "./data/input_photos"
OUTPUT_DIR = "sorted_photos"

# --- HELPERS ---

def get_pattern_prefix(filename):
    """Extracts prefix for grouping (e.g. 1997-001 -> 1997)"""
    # Regex: Capture start of string up to last separator followed by digits
    # Excludes "IMG", "Screenshot", "YYYYMMDD" logic
    if "IMG" in filename: return None
    if "Screenshot" in filename: return None
    
    # Check for date format YYYYMMDD (ignore)
    if re.match(r'^(19|20)\d{6}', filename): return None
    
    match = re.match(r'^(.*)[-_]\d+', filename)
    if match:
        return match.group(1)
    return None

def extract_sort_key(filename):
    """
    Returns a tuple (Year, Sequence) for sorting.
    Lower Year = Better. Lower Sequence = Better.
    """
    # Try to find a year
    year_match = re.search(r'(19\d{2}|20\d{2})', filename)
    year = int(year_match.group(1)) if year_match else 9999
    
    # Try to find a sequence number at the end
    seq_match = re.findall(r'\d+', filename)
    seq = int(seq_match[-1]) if seq_match else 999999
    
    return (year, seq)

# --- STAGE 1: AUDIT ---

def show_targets():
    print("\n🎯 Scanning for Targets (Prefixes with >10 images)...")
    prefix_counts = Counter()
    
    for root, _, files in os.walk(TARGET_FOLDER):
        for f in files:
            if f.lower().endswith(('.jpg', '.png')):
                p = get_pattern_prefix(f)
                if p: prefix_counts[p] += 1
                
    # Filter low counts
    targets = [t for t in prefix_counts.most_common() if t[1] >= 10]
    
    if not targets:
        print("No suitable targets found.")
        return []
        
    print(f"\n{'ID':<4} | {'PREFIX':<20} | {'COUNT':<5}")
    print("-" * 35)
    
    for idx, (prefix, count) in enumerate(targets):
        print(f"{idx+1:<4} | {prefix:<20} | {count:<5}")
        
    return [t[0] for t in targets]

# --- STAGE 2: SCOUT ---

def scout_target(target_prefix):
    print(f"\n🕵️  Scouting clusters involving '{target_prefix}'...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get all cluster IDs
    c_ids = [x[0] for x in cursor.execute("SELECT DISTINCT cluster_id FROM clusters").fetchall()]
    
    affected_clusters = []
    
    print(f"\n{'WINNER (Keep)':<35} | {'LOSER (Discard)':<35}")
    print("-" * 75)
    
    for cid in c_ids:
        # Get paths
        query = "SELECT images.path FROM clusters JOIN images ON clusters.image_id = images.id WHERE clusters.cluster_id = ?"
        paths = [row[0] for row in cursor.execute(query, (cid,)).fetchall()]
        
        # Filter: Does this cluster involve our target?
        if any(target_prefix in os.path.basename(p) for p in paths):
            
            # APPLY LOGIC: Sort by (Year Ascending, Sequence Ascending)
            # This implements "Option B: Prioritize Older Year"
            paths.sort(key=lambda p: extract_sort_key(os.path.basename(p)))
            
            winner = paths[0]
            losers = paths[1:]
            
            # Show sample output
            w_name = os.path.basename(winner)
            l_name = os.path.basename(losers[0]) if losers else "---"
            
            print(f"{w_name:<35} | {l_name:<35}")
            
            affected_clusters.append((cid, winner, losers))
            
    conn.close()
    return affected_clusters

# --- STAGE 3: SNIPER ---

def fire_sniper(cluster_data):
    if not cluster_data:
        print("No shots to fire.")
        return

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
        # Move Winner
        try:
            shutil.move(winner, os.path.join(keep_dir, os.path.basename(winner)))
        except: pass
        
        # Move Losers
        for l in losers:
            if os.path.exists(l):
                try:
                    shutil.move(l, os.path.join(disc_dir, os.path.basename(l)))
                    shots += 1
                except: pass
                
        # Remove from DB
        cursor.execute("DELETE FROM clusters WHERE cluster_id = ?", (cid,))
        
    conn.commit()
    conn.close()
    print(f"✅ Done. {shots} files moved to Discards.")

# --- MAIN LOOP ---

def main():
    while True:
        targets = show_targets()
        if not targets: break
        
        choice = input("\nEnter ID to target (or 'q' to quit): ")
        if choice.lower() == 'q': break
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(targets):
                target = targets[idx]
                
                # Scout
                data = scout_target(target)
                
                if data:
                    # Fire?
                    fire_sniper(data)
                else:
                    print("No duplicates found involving this prefix.")
                    input("Press Enter to continue...")
            else:
                print("Invalid ID.")
        except ValueError:
            print("Invalid input.")

if __name__ == "__main__":
    main()