import os
import re
from collections import Counter

# --- CONFIG ---
TARGET_FOLDER = "./data/input_photos" 

def identify_prefixes():
    print(f"🕵️  Scanning {TARGET_FOLDER} for naming patterns...")
    print("    (Filters active: No IMG, No Dates, No 2023-08, Count >= 10)\n")
    
    if not os.path.exists(TARGET_FOLDER):
        print("❌ Error: Folder path not found.")
        return

    prefix_counts = Counter()
    files_scanned = 0
    
    # Regex: Capture everything up to the last hyphen/underscore followed by digits
    regex = re.compile(r'^(.*)[-_]\d+')

    # Regex for YYYYMMDD (Phone bursts)
    date_pattern = re.compile(r'^(19|20)\d{6}$')

    for root, _, files in os.walk(TARGET_FOLDER):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.heic')):
                files_scanned += 1
                
                match = regex.match(f)
                if match:
                    p = match.group(1)
                    
                    # --- FILTERS ---
                    
                    # 1. Ignore Full Dates (20230512)
                    if date_pattern.match(p): continue 
                    
                    # 2. Ignore "IMG" (Generic Camera)
                    if "IMG" in p: continue
                    
                    # 3. Ignore Specific Noise
                    if "2023-08" in p: continue
                    
                    prefix_counts[p] += 1

    print(f"   -> Scanned {files_scanned} images.")
    print(f"   -> Found {len(prefix_counts)} unique prefixes after filtering.\n")
    
    print(f"{'PREFIX':<25} | {'COUNT':<10}")
    print("-" * 40)
    
    found_any = False
    
    # Sort by count descending
    for prefix, count in prefix_counts.most_common():
        # FILTER 4: Significance Threshold
        if count >= 10:
            print(f"{prefix:<25} | {count:<10}")
            found_any = True
            
    if not found_any:
        print("(No prefixes found matching criteria)")

if __name__ == "__main__":
    identify_prefixes()