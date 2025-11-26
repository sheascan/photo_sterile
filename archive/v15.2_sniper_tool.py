import os
import re
import shutil
import sqlite3
from collections import Counter

# --- CONFIG ---
DB_FILE = "photo_library.db"
OUTPUT_DIR = "sorted_photos"

# --- HELPERS ---

def get_pattern_prefix(filename):
    """Extracts prefix for grouping (e.g. 1997-001 -> 1997)"""
    if "IMG" in filename: return None
    if "Screenshot" in filename: return None
    if "2023-08" in filename: return None # Filter out your specific bulk folder
    
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

# --- STAGE 1: AUDIT CLUSTERS ---

def scan_database_for_targets():
    print("\n🎯 Scanning Database for ACTIVE duplicates...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get all file paths that are currently in a cluster
    query = "SELECT images.path FROM clusters JOIN images ON clusters.image_id = images.id"
    paths = [row[0] for row in cursor.execute(query).fetchall()]
    conn.close()
    
    if not paths:
        print("No clusters found in database.")
        return []

    # Count how many times each prefix appears in a duplicate
    prefix_counts = Counter()
    for p in paths:
        fname = os.path.basename(p)
        prefix = get_pattern_prefix(fname)
        if prefix:
            prefix_counts[prefix] += 1
            
    # Sort by most duplicates
    targets = prefix_counts.most_common()
    
    print(f"\n{'ID':<4} | {'PREFIX':<20} | {'DUPLICATES FOUND':<15}")
    print("-" * 45)
    
    valid_targets = []
    for idx, (prefix, count) in enumerate(targets):
        print(f"{idx+1:<4} | {prefix:<20} | {count:<15}")
        valid_targets.append(prefix)
        
    return valid_targets

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
            paths.sort(key=lambda p: extract_sort_key(os.path.basename(p)))
            
            winner = paths[0]
            losers = paths[1:]
            
            w_name = os.path.basename(winner)
            l_name = os.path.basename(losers[0]) if losers else "---"
            
            print(f"{w_name:<35} | {l_name:<35}")
            affected_clusters.append((cid, winner, losers))
            
    conn.close()
    return affected_clusters

# --- STAGE 3: SNIPER ---

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

# --- MAIN LOOP ---

def main():
    while True:
        targets = scan_database_for_targets()
        if not targets: break
        
        choice = input("\nEnter ID or PREFIX to target (or 'q' to quit): ")
        if choice.lower() == 'q': break
        
        target = None
        
        # Logic: Did they type a number or a name?
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(targets):
                target = targets[idx]
        else:
            # Try to match text input
            if choice in targets:
                target = choice
        
        if target:
            data = scout_target(target)
            if data: fire_sniper(data)
            else: input("No actions available. Press Enter...")
        else:
            print("Invalid selection.")

if __name__ == "__main__":
    main()