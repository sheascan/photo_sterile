import os
import time
from datetime import datetime
from collections import Counter

# --- CONFIG ---
SCAN_FOLDER = "./data/input_photos"

def run_forensics():
    print(f"🕵️  Forensic Timeline of {SCAN_FOLDER}")
    print("    Scanning timestamps... (this is fast)")

    # 1. Collect Timestamps
    timestamps = []
    
    for root, _, files in os.walk(SCAN_FOLDER):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg','.png')):
                full_path = os.path.join(root, f)
                # Get Modification Time (mtime)
                mtime = os.path.getmtime(full_path)
                # Convert to readable hour bucket (YYYY-MM-DD HH:00)
                dt = datetime.fromtimestamp(mtime)
                bucket = dt.strftime("%Y-%m-%d %H:00")
                timestamps.append(bucket)

    # 2. Count Frequency
    counts = Counter(timestamps)
    
    # 3. Sort and Print
    print("\n--- TIMELINE OF JPG MODIFICATIONS ---")
    print(f"{'TIME WINDOW':<20} | {'FILES MODIFIED':<10}")
    print("-" * 35)
    
    sorted_times = sorted(counts.items())
    
    total_files = 0
    for time_bucket, count in sorted_times:
        # visual bar for scale
        bar = "█" * int(count / 100) 
        print(f"{time_bucket:<20} | {count:<5} {bar}")
        total_files += count
        
    print("-" * 35)
    print(f"Total JPGs scanned: {total_files}")

if __name__ == "__main__":
    run_forensics()