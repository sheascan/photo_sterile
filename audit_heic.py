import sqlite3
import os

# --- CONFIGURATION ---
DB_FILE = "photo_library.db"
SCAN_FOLDER = "./data/input_photos" 

def run_heic_audit():
    print("🕵️  Starting HEIC vs Database Audit...")
    
    # 1. LOAD THE DATABASE INDEX
    if not os.path.exists(DB_FILE):
        print("❌ Error: Database not found!")
        return

    print("📚 Reading Database index...")
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # We load all paths into a set for instant checking
    # We normalize to lowercase to handle file extension case differences
    db_paths = set(row[0] for row in c.execute("SELECT path FROM images"))
    conn.close()
    
    print(f"   -> Database currently holds {len(db_paths)} images (JPEGs/PNGs).")

    # 2. SCAN DISK FOR HEICS
    print(f"📂 Scanning {SCAN_FOLDER} for HEIC files...")
    heic_files = []
    for root, _, files in os.walk(SCAN_FOLDER):
        for f in files:
            if f.lower().endswith(('.heic', '.heif')):
                heic_files.append(os.path.join(root, f))
    
    print(f"   -> Found {len(heic_files)} HEIC files on disk.")

    # 3. THE MATCHING LOGIC
    matched_count = 0
    orphan_count = 0
    orphans = []

    print("\n🔍 Checking for twins...")
    
    for h_path in heic_files:
        # Construct the theoretical JPG path
        # e.g., /path/to/image.HEIC -> /path/to/image.jpg
        base_name = os.path.splitext(h_path)[0]
        
        # We check for both .jpg and .JPG just in case
        candidate_1 = base_name + ".jpg"
        candidate_2 = base_name + ".JPG"
        
        if (candidate_1 in db_paths) or (candidate_2 in db_paths):
            matched_count += 1
        else:
            orphan_count += 1
            orphans.append(h_path)

    # 4. REPORT
    print("-" * 40)
    print(f"✅ MATCHED: {matched_count}")
    print(f"   (These HEIC files have a JPG twin safely inside the DB)")
    
    print(f"❌ ORPHANS: {orphan_count}")
    print(f"   (These HEIC files have NO record in the DB)")
    print("-" * 40)

    if orphan_count > 0:
        print("\n--- SAMPLE OF ORPHANS (First 10) ---")
        for o in orphans[:10]:
            print(f"   {os.path.basename(o)}")
            
        print("\n--- DIAGNOSIS ---")
        print("1. Did you run 'Scan & Add to Library' AFTER converting?")
        print("2. These files might have failed the conversion step.")
        print("3. Or their JPG twins are corrupt/unreadable by the app.")

if __name__ == "__main__":
    run_heic_audit()