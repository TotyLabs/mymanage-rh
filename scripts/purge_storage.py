import os
import shutil

STORAGE_PATH = "./storage"

def purge_storage():
    print(f"Starting Storage Cleanup in {STORAGE_PATH}...")
    if not os.path.exists(STORAGE_PATH):
        print(f"Storage path {STORAGE_PATH} does not exist.")
        return

    subdirs = [d for d in os.listdir(STORAGE_PATH) if os.path.isdir(os.path.join(STORAGE_PATH, d))]
    
    for subdir in subdirs:
        path = os.path.join(STORAGE_PATH, subdir)
        print(f"Cleaning subdirectory: {subdir}")
        if subdir == ".tmp_secure":
             # Keep this one as a dir but empty it
             for item in os.listdir(path):
                 item_path = os.path.join(path, item)
                 if os.path.isfile(item_path): os.remove(item_path)
                 else: shutil.rmtree(item_path)
             continue

        # For others, we can just empty them
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            try:
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)
            except Exception as e:
                print(f"Error deleting {item_path}: {e}")

    # Specific cleanup for system temp
    import tempfile
    temp_dir = tempfile.gettempdir()
    print(f"Cleaning system temp directory: {temp_dir}")
    purged_count = 0
    for f in os.listdir(temp_dir):
        if f.startswith("payroll_export_") and f.endswith(".zip"):
            try:
                os.remove(os.path.join(temp_dir, f))
                purged_count += 1
            except:
                pass
    if purged_count:
        print(f"Purged {purged_count} temporary export ZIPs.")

    print("Storage Cleanup Completed.")

if __name__ == "__main__":
    purge_storage()
