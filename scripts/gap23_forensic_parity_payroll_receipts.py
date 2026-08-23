import os
import sys
from sqlalchemy import text
from payroll_core import SessionLocal, logger

def migrate():
    """
    Migration GAP-023: forensic_parity_payroll_receipts
    Adds forensic columns to payroll_receipts to match receipts (enterprise) table.
    """
    db = SessionLocal()
    try:
        cleanup_logger = logger
        cleanup_logger.info("Starting migration GAP-023: forensic_parity_payroll_receipts")
        
        # Check existing columns to avoid duplicate errors
        res = db.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'payroll_receipts'"))
        existing_cols = [r[0] for r in res.fetchall()]
        
        commands = []
        
        if 'signature_snapshot' not in existing_cols:
            commands.append("ALTER TABLE payroll_receipts ADD COLUMN signature_snapshot BYTEA")
            cleanup_logger.info("Queuing: Add signature_snapshot (BYTEA)")
            
        if 'signature_hash' not in existing_cols:
            commands.append("ALTER TABLE payroll_receipts ADD COLUMN signature_hash TEXT")
            cleanup_logger.info("Queuing: Add signature_hash (TEXT)")
            
        if 'tsa_timestamp' not in existing_cols:
            commands.append("ALTER TABLE payroll_receipts ADD COLUMN tsa_timestamp TIMESTAMPTZ")
            cleanup_logger.info("Queuing: Add tsa_timestamp (TIMESTAMPTZ)")
            
        if not commands:
            cleanup_logger.info("No migration needed. Columns already exist.")
            return

        for cmd in commands:
            db.execute(text(cmd))
            
        db.commit()
        cleanup_logger.info("Migration GAP-023 COMPLETED successfully.")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Migration GAP-023 FAILED: {e}")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
