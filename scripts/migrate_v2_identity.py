import sys
import os
from dotenv import load_dotenv

# Load env before any imports
load_dotenv()

sys.path.append(os.getcwd())

import sqlalchemy as sa
from sqlalchemy import text
from payroll_core import engine

def migrate():
    with engine.connect() as conn:
        print("Migrating signature_requests table...")
        # Check if column exists (PostgreSQL syntax or generic)
        try:
            conn.execute(text("ALTER TABLE signature_requests ADD COLUMN issuer_ip INET;"))
            print("Added issuer_ip")
        except Exception as e:
            print(f"issuer_ip might already exist: {e}")
            
        try:
            conn.execute(text("ALTER TABLE signature_requests ADD COLUMN issuer_ua TEXT;"))
            print("Added issuer_ua")
        except Exception as e:
            print(f"issuer_ua might already exist: {e}")
            
        try:
            conn.execute(text("ALTER TABLE signature_requests ADD COLUMN requires_verification BOOLEAN DEFAULT TRUE;"))
            print("Added requires_verification")
        except Exception as e:
            print(f"requires_verification might already exist: {e}")
        
        conn.commit()
        print("Migration complete.")

if __name__ == "__main__":
    migrate()
