import os
import re
from collections import Counter

# --- CONFIG ---
# Update this to the folder you want to scan
TARGET_FOLDER = "./data/input_photos" 

def identify_prefixes():
    print(f"🕵️  Scanning {TARGET_FOLDER} for naming patterns...")
    
    if not os.path.exists(TARGET_FOLDER):
        print("❌ Error: Folder path not found.")
        return

    prefix_counts = Counter()
    files_scanned = 0
    
    # Regex Explanation:
    # ^(.*?): Capture the prefix at the start (non-greedy)
    # [-_]:   Stop at the last hyphen or underscore...
    # \d+:    ...that is followed immediately by a number
    # [^\/]*$: Ensure we are looking at the filename, not the path
    
    # This handles "1993-B-071" -> Prefix "1993-B"
    # This handles "C-022" -> Prefix "C"
    # This handles "1984-013" -> Prefix "1984"
    
    regex = re.compile(r'^(.*)[-_]\d+')

    for root, _, files in os.walk(TARGET_FOLDER):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.heic')):
                files_scanned += 1
                
                # Special handling for the "YYYYMMDD_HHMMSS" format
                # If it looks like a date-time stamp, treat the Date part as the prefix
                if re.match(r'^\d{8}_\d{6}', f):
                    prefix = f[:8] # First 8 chars (YYYYMMDD)
                    prefix_counts[prefix] += 1
                    continue

                match = regex.match(f)
                if match:
                    # We found a pattern like "Prefix-Number"
                    p = match.group(1)
                    prefix_counts[p] += 1
                else:
                    # No standard separator found (e.g. "img001.jpg")
                    # We log these as "Unpatterned"
                    prefix_counts["[No Prefix / Other]"] += 1

    print(f"   -> Scanned {files_scanned} images.\n")
    
    print(f"{'PREFIX':<25} | {'COUNT':<10}")
    print("-" * 40)
    
    # Sort by count descending
    for prefix, count in prefix_counts.most_common():
        print(f"{prefix:<25} | {count:<10}")

if __name__ == "__main__":
    identify_prefixes()