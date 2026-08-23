import os
import sys
import logging
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment before anything else
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def run_migration():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not set")
        return

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # 1. Employee updates
            logger.info("Adding dni_normalized to employees...")
            conn.execute(text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS dni_normalized TEXT"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_employees_dni_normalized ON employees(organization_id, dni_normalized)"))

            # 2. Receipt updates
            logger.info("Hardening receipts table...")
            # Ensure employee_id exists (service uses it, model is missing it)
            conn.execute(text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS employee_id UUID REFERENCES employees(id) ON DELETE SET NULL"))
            
            # Add new columns
            conn.execute(text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS ocr_dni_normalized TEXT"))
            conn.execute(text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS match_status TEXT DEFAULT 'orphan'"))
            conn.execute(text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS match_reason TEXT"))
            
            # Ensure page_number exists (service uses it)
            conn.execute(text("ALTER TABLE receipts ADD COLUMN IF NOT EXISTS page_number INTEGER"))

            # 3. Create indices for matching performance
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipts_ocr_dni_norm ON receipts(company_id, ocr_dni_normalized)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_receipts_match_status ON receipts(company_id, match_status)"))

            conn.commit()
            logger.info("Migration successful!")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
