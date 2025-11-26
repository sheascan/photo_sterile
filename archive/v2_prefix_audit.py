import os
import re
from collections import Counter

# --- CONFIG ---
TARGET_FOLDER = "./data/input_photos" 

def identify_prefixes():
    print(f"🕵️  Scanning {TARGET_FOLDER} for naming patterns...")
    print("    (Ignoring groups < 10 files)")
    print("    (Ignoring YYYYMMDD date stamps)\n")
    
    if not os.path.exists(TARGET_FOLDER):
        print("❌ Error: Folder path not found.")
        return

    prefix_counts = Counter()
    files_scanned = 0
    
    # Regex: Capture everything up to the last hyphen/underscore followed by digits
    # matches "1993-B-071" -> "1993-B"
    regex = re.compile(r'^(.*)[-_]\d+')

    # Regex to identify "YYYYMMDD" (8 digits starting with 19 or 20)
    # We use this to ignore phone-camera style prefixes
    date_pattern = re.compile(r'^(19|20)\d{6}$')

    for root, _, files in os.walk(TARGET_FOLDER):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.heic')):
                files_scanned += 1
                
                match = regex.match(f)
                if match:
                    p = match.group(1)
                    
                    # FILTER 1: Is this prefix just a full date (YYYYMMDD)?
                    if date_pattern.match(p):
                        continue # Skip (likely a phone burst)
                        
                    prefix_counts[p] += 1

    print(f"   -> Scanned {files_scanned} images.\n")
    
    print(f"{'PREFIX':<25} | {'COUNT':<10}")
    print("-" * 40)
    
    found_any = False
    
    # Sort by count descending
    for prefix, count in prefix_counts.most_common():
        # FILTER 2: Only show significant groups
        if count >= 10:
            print(f"{prefix:<25} | {count:<10}")
            found_any = True
            
    if not found_any:
        print("(No prefixes found with >= 10 images)")

if __name__ == "__main__":
    identify_prefixes()