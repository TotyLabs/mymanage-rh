"""
DB migration script - Add employee legajo columns (V1)
Run with: venv\Scripts\python scripts\_migrate_v1.py
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from payroll_core import SessionLocal


def migrate():
    db = SessionLocal()
    try:
        # New employee columns
        employee_columns = [
            ("last_name", "TEXT"),
            ("contract_type", "TEXT"),
            ("bank_name", "TEXT"),
            ("account_type", "TEXT"),
            ("cbu", "TEXT"),
            ("bank_alias", "TEXT"),
            ("account_holder", "TEXT"),
            ("signature_image_path", "TEXT"),
        ]

        for col, col_type in employee_columns:
            res = db.execute(text(f"""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='employees' AND column_name='{col}';
            """)).fetchone()
            if not res:
                print(f"  + employees.{col} ({col_type})")
                db.execute(text(f"ALTER TABLE employees ADD COLUMN {col} {col_type};"))
                db.commit()
            else:
                print(f"  âœ“ employees.{col} already exists")

        # Organization logo_path (Phase 3 prep)
        res = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='organizations' AND column_name='logo_path';
        """)).fetchone()
        if not res:
            print(f"  + organizations.logo_path")
            db.execute(text("ALTER TABLE organizations ADD COLUMN logo_path TEXT;"))
            db.commit()
        else:
            print(f"  âœ“ organizations.logo_path already exists")

        # PayrollReceipt document_locked (Phase 4 prep)
        res = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='payroll_receipts' AND column_name='document_locked';
        """)).fetchone()
        if not res:
            print(f"  + payroll_receipts.document_locked")
            db.execute(text("ALTER TABLE payroll_receipts ADD COLUMN document_locked BOOLEAN NOT NULL DEFAULT false;"))
            db.commit()
        else:
            print(f"  âœ“ payroll_receipts.document_locked already exists")

        print("\nâœ… Migration complete.")

    except Exception as e:
        print(f"âŒ Error: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("Running V1 database migration...")
    migrate()
