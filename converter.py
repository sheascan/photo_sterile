import os
import time
from PIL import Image
from pillow_heif import register_heif_opener
import concurrent.futures

# --- CONFIG ---
SOURCE_FOLDER = "./data/input_photos"
WORKERS = 4 

# Enable HEIC support in Pillow
register_heif_opener()

def convert_file(file_info):
    path, filename = file_info
    
    # Target filename (same name, but .jpg)
    name_no_ext = os.path.splitext(filename)[0]
    target_path = os.path.join(path, f"{name_no_ext}.jpg")
    
    # Skip if JPG already exists
    if os.path.exists(target_path):
        return None 
    
    source_full_path = os.path.join(path, filename)
    
    try:
        # Open HEIC
        img = Image.open(source_full_path)
        
        # Save as JPG (High Quality)
        # We try to preserve EXIF if available
        try:
            exif_data = img.info.get('exif')
            if exif_data:
                img.save(target_path, "JPEG", quality=95, exif=exif_data)
            else:
                img.save(target_path, "JPEG", quality=95)
        except:
            # Fallback if EXIF fails
            img.save(target_path, "JPEG", quality=95)
            
        return source_full_path
    except Exception as e:
        print(f"Failed to convert: {filename} ({e})")
        return None

def run_conversion():
    print(f"🕵️  Scanning {SOURCE_FOLDER} for HEIC files...")
    
    heic_files = []
    for root, _, files in os.walk(SOURCE_FOLDER):
        for f in files:
            if f.lower().endswith(('.heic', '.heif')):
                heic_files.append((root, f))
                
    if not heic_files:
        print("✅ No HEIC files found.")
        return

    print(f"found {len(heic_files)} HEIC files. Starting conversion...")
    
    converted_count = 0
    
    # Run in parallel for speed
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        results = list(executor.map(convert_file, heic_files))
        
    # Count successes (non-None results)
    converted_count = sum(1 for r in results if r is not None)
    
    print(f"\n🎉 Conversion Complete.")
    print(f"   - HEIC Files Found: {len(heic_files)}")
    print(f"   - New JPGs Created: {converted_count}")
    print(f"   - Skipped (JPG existed): {len(heic_files) - converted_count}")

if __name__ == "__main__":
    run_conversion()