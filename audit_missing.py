import sqlite3
import os

# --- CONFIG ---
DB_FILE = "photo_library.db"
SCAN_FOLDER = "./data/input_photos" 
# Use the exact extensions from the main app
VALID_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.heic')

def run_audit():
    print("🕵️  Starting Audit...")
    
    # 1. Get everything that successfully made it into the DB
    if not os.path.exists(DB_FILE):
        print("Error: Database not found!")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # We use a set for instant lookup speed
    print("📚 Reading Database index...")
    db_paths = set(row[0] for row in c.execute("SELECT path FROM images"))
    conn.close()
    print(f"   -> Database contains {len(db_paths)} valid images.")

    # 2. Scan the disk again to find what SHOULD be there
    print("📂 Scanning disk for candidates...")
    disk_candidates = []
    for root, _, files in os.walk(SCAN_FOLDER):
        for f in files:
            if f.lower().endswith(VALID_EXTS):
                disk_candidates.append(os.path.join(root, f))
    
    print(f"   -> Found {len(disk_candidates)} files with image extensions.")

    # 3. Compare
    missing_files = []
    for f in disk_candidates:
        if f not in db_paths:
            missing_files.append(f)

    count_missing = len(missing_files)
    print(f"\n❌ {count_missing} files were rejected by the engine.")

    if count_missing == 0:
        print("   (Everything looks perfect!)")
    else:
        print("\n--- SAMPLE OF REJECTED FILES (Top 10) ---")
        for i, path in enumerate(missing_files[:10]):
            try:
                size = os.path.getsize(path)
                print(f"   {i+1}. {os.path.basename(path)} ({size} bytes)")
            except:
                print(f"   {i+1}. {os.path.basename(path)} (File Error)")
        
        print("\n--- DIAGNOSIS ---")
        print("Check the file sizes above.")
        print("If size is 0 bytes: The file is empty.")
        print("If size is small (<1KB): It might be a thumbnail or text file.")
        print("If size is normal: The file header is likely corrupt/unreadable.")

        # Option to save full list
        with open("rejected_files_log.txt", "w") as f:
            for line in missing_files:
                f.write(f"{line}\n")
        print(f"\n📄 Full list saved to 'rejected_files_log.txt'")

if __name__ == "__main__":
    run_audit()