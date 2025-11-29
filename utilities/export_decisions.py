import os
import json
import imagehash
from PIL import Image
import concurrent.futures

# --- CONFIG ---
DIRS = {
    "ARCHIVE": "./data/archived_documents",
    "DISCARDS": "./sorted_photos/Discards",
    "KEEPERS": "./sorted_photos/Keepers" 
    # We track Keepers too, so we don't accidentally delete them in a new merge
}

OUTPUT_FILE = "decision_passport.json"

def get_hash(path):
    try:
        img = Image.open(path)
        # We use strict hash size for exact matching across systems
        return str(imagehash.phash(img))
    except:
        return None

def scan_folder(folder_path, label):
    print(f"   Scanning {label}...")
    hashes = set()
    files_to_scan = []
    
    for root, _, files in os.walk(folder_path):
        for f in files:
            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.heic')):
                files_to_scan.append(os.path.join(root, f))
                
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(get_hash, files_to_scan))
        
    for h in results:
        if h: hashes.add(h)
        
    print(f"   -> Found {len(hashes)} unique {label}.")
    return list(hashes)

def create_passport():
    print("🛂 Generating Decision Passport...")
    
    data = {
        "documents": scan_folder(DIRS["ARCHIVE"], "Documents"),
        "discards": scan_folder(DIRS["DISCARDS"], "Discards"),
        "keepers": scan_folder(DIRS["KEEPERS"], "Keepers")
    }
    
    # Save to JSON
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f)
        
    print(f"\n✅ Passport Created: {OUTPUT_FILE}")
    print("   Save this file! It contains all your hard work.")

if __name__ == "__main__":
    create_passport()