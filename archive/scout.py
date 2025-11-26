import sqlite3
import os
import re

# --- CONFIG ---
DB_FILE = "photo_library.db"
TARGET_YEAR = "1997"  # Change this to match your folder/filename pattern

def run_scout():
    print(f"🕵️  Scouting for duplicates containing '{TARGET_YEAR}'...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get all cluster IDs
    cluster_ids = [x[0] for x in cursor.execute("SELECT DISTINCT cluster_id FROM clusters").fetchall()]
    
    match_count = 0
    
    print(f"\n{'FILE A':<30} | {'FILE B':<30}")
    print("-" * 65)
    
    for cid in cluster_ids:
        # Get paths in this cluster
        query = "SELECT images.path FROM clusters JOIN images ON clusters.image_id = images.id WHERE clusters.cluster_id = ?"
        paths = [row[0] for row in cursor.execute(query, (cid,)).fetchall()]
        
        # Filter: Only look at clusters where at least one file matches the Target Year
        if any(TARGET_YEAR in p for p in paths) and len(paths) >= 2:
            # Just taking the first two for display comparison
            name_a = os.path.basename(paths[0])
            name_b = os.path.basename(paths[1])
            print(f"{name_a:<30} | {name_b:<30}")
            match_count += 1
            
    conn.close()
    print("-" * 65)
    print(f"Found {match_count} clusters involving '{TARGET_YEAR}'")

if __name__ == "__main__":
    run_scout()