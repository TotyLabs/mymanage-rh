import os
import sys
from sqlalchemy import text
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Add root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payroll_core import SessionLocal, logger

def apply_sql_hardening():
    sql_file = os.path.join(os.path.dirname(__file__), "harden_db_triggers.sql")
    if not os.path.exists(sql_file):
        print(f"Error: {sql_file} not found")
        return

    with open(sql_file, "r") as f:
        sql = f.read()

    db = SessionLocal()
    try:
        # 1. Triggers
        print("Applying DB hardening triggers...")
        with open(sql_file, "r") as f:
            sql_triggers = f.read()
        db.execute(text(sql_triggers))
        
        # 2. RLS
        rls_file = os.path.join(os.path.dirname(__file__), "setup_rls.sql")
        if os.path.exists(rls_file):
            print("Applying Row-Level Security (RLS) policies...")
            with open(rls_file, "r") as f:
                sql_rls = f.read()
            db.execute(text(sql_rls))
            
        # 3. Immutability & Soft-Delete (Gaps 4 & 13.2)
        immutability_file = os.path.join(os.path.dirname(__file__), "setup_immutability.sql")
        if os.path.exists(immutability_file):
            print("Applying Immutability and Soft-Delete policies...")
            with open(immutability_file, "r") as f:
                sql_imm = f.read()
            db.execute(text(sql_imm))
        
        # 4. Unified Views (Gaps 8.2 & 12.3)
        views_file = os.path.join(os.path.dirname(__file__), "setup_views.sql")
        if os.path.exists(views_file):
            print("Applying Unified Views (Dual-Model Abstraction + Audit Trail)...")
            with open(views_file, "r") as f:
                sql_views = f.read()
            db.execute(text(sql_views))
        
        db.commit()
        print("Hardening measures applied successfully.")
    except Exception as e:
        db.rollback()
        print(f"Failed to apply triggers: {e}")
        logger.error(f"hardening.apply_failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    apply_sql_hardening()
