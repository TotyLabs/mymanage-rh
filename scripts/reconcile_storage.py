import os
import sys
from pathlib import Path
from sqlalchemy import text
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payroll_core import SessionLocal, ALLOWED_STORAGE_DIR, logger

def reconcile_storage():
    """
    Industrial Hardening Phase 2: PDF Garbage Collector.
    Finds signed PDF files that are NOT referenced in the database and moves them to forensics.
    """
    print("Starting Storage Reconciliation (Garbage Collector)...")
    db = SessionLocal()
    
    try:
        # 1. Get all signed file paths from DB
        # Enterprise
        ent_paths = db.execute(text("SELECT file_path FROM receipts WHERE file_path IS NOT NULL")).scalars().all()
        # Legacy
        leg_paths = db.execute(text("SELECT receipt_pdf_path FROM payroll_receipts WHERE receipt_pdf_path IS NOT NULL")).scalars().all()
        
        referenced_paths = set()
        for p in ent_paths:
             if p: referenced_paths.add(os.path.abspath(os.path.join(ALLOWED_STORAGE_DIR, p)))
        for p in leg_paths:
             if p: referenced_paths.add(os.path.abspath(os.path.join(ALLOWED_STORAGE_DIR, p)))
        
        print(f"Referenced files in DB: {len(referenced_paths)}")
        
        # 2. Walk storage/receipts and find orphans
        receipts_root = os.path.join(ALLOWED_STORAGE_DIR, "receipts")
        if not os.path.exists(receipts_root):
            print("No receipts directory found.")
            return

        forensics_dir = os.path.join(ALLOWED_STORAGE_DIR, "forensics", "orphans")
        os.makedirs(forensics_dir, exist_ok=True)
        
        orphans_found = 0
        for root, dirs, files in os.walk(receipts_root):
            for file in files:
                if file.endswith("_signed.pdf"):
                    full_path = os.path.abspath(os.path.join(root, file))
                    if full_path not in referenced_paths:
                        # This is an orphan!
                        print(f"ORPHAN DETECTED: {full_path}")
                        target_path = os.path.join(forensics_dir, file)
                        # Avoid collisions in forensics
                        if os.path.exists(target_path):
                             target_path = os.path.join(forensics_dir, f"{os.getpid()}_{file}")
                        
                        os.rename(full_path, target_path)
                        logger.warning(f"storage.reconciliation_quarantine: {full_path} -> {target_path}")
                        orphans_found += 1
        
        print(f"Reconciliation complete. Orphans quarantined: {orphans_found}")
        
    except Exception as e:
        print(f"Reconciliation failed: {e}")
        logger.error(f"storage.reconciliation_failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reconcile_storage()
