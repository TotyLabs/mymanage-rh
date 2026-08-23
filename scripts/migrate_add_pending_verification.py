"""
Migration script to add 'pending_verification' status to employee_status enum.
Run this after updating models/enums.py with the new status.

Usage:
    python scripts/migrate_add_pending_verification.py
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payroll_core import get_db, logger
from sqlalchemy import text

def migrate_add_pending_verification():
    """
    Adds 'pending_verification' value to the employee_status enum type.
    PostgreSQL enums are immutable, so we need to:
    1. Create a new enum type with all values
    2. Migrate data
    3. Drop old enum
    4. Rename new enum
    """
    db = next(get_db())
    
    try:
        logger.info("Starting migration: add pending_verification to employee_status enum")
        
        # Check if pending_verification already exists
        result = db.execute(text("""
            SELECT 1 FROM pg_enum 
            WHERE enumlabel = 'pending_verification' 
            AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'employee_status')
        """)).fetchone()
        
        if result:
            logger.info("pending_verification already exists in enum, skipping")
            return
        
        # Add the new value to the existing enum
        # This is a safer approach for PostgreSQL
        db.execute(text("""
            ALTER TYPE employee_status ADD VALUE 'pending_verification' BEFORE 'pre_registered'
        """))
        
        db.commit()
        logger.info("âœ… Successfully added 'pending_verification' to employee_status enum")
        
        return {"status": "success", "message": "enum_updated"}
        
    except Exception as e:
        db.rollback()
        logger.error(f"âŒ Migration failed: {e}")
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    
    result = migrate_add_pending_verification()
    print(f"\nResult: {result}")
