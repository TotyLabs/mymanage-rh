
import os
import sys
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

load_dotenv()

from sqlalchemy import text
from payroll_core import SessionLocal

def migrate():
    db = SessionLocal()
    try:
        print("Starting migration: adding signature_image_data to company_signers...")
        
        # Check if column exists
        res = db.execute(text("""
            SELECT count(*) 
            FROM information_schema.columns 
            WHERE table_name = 'company_signers' AND column_name = 'signature_image_data'
        """)).fetchone()
        
        if res[0] == 0:
            db.execute(text("ALTER TABLE company_signers ADD COLUMN signature_image_data BYTEA"))
            db.commit()
            print("Successfully added signature_image_data column.")
        else:
            print("Column signature_image_data already exists.")
            
        print("Migration complete.")
    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
