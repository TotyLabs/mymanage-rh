import os
from dotenv import load_dotenv
load_dotenv()

from payroll_core import SessionLocal
from sqlalchemy import text

def debug():
    db = SessionLocal()
    try:
        r = db.execute(text("SELECT id FROM receipts LIMIT 5")).fetchall()
        print(f"Receipt IDs in DB: {[x[0] for x in r]}")
        
        e = db.execute(text("SELECT id FROM employees LIMIT 5")).fetchall()
        print(f"Employee IDs in DB: {[x[0] for x in e]}")
        
        # Check if email_events table exists
        db.execute(text("SELECT 1 FROM email_events LIMIT 1"))
        print("email_events table exists.")
        
    except Exception as err:
        print(f"DEBUG ERROR: {err}")
    finally:
        db.close()

if __name__ == "__main__":
    debug()
