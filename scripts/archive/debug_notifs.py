from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # Try reading from config.py if .env is missing
    try:
        import config
        DATABASE_URL = config.DATABASE_URL
    except:
        pass

engine = create_engine(DATABASE_URL)

def check_notifications():
    with engine.connect() as conn:
        print("--- Notifications Table ---")
        res = conn.execute(text("SELECT id, sender_user_id, company_id, message, created_at FROM notifications ORDER BY created_at DESC LIMIT 5"))
        for row in res:
            print(row)
            
        print("\n--- Current Users ---")
        res = conn.execute(text("SELECT id, email, role, organization_id FROM users LIMIT 10"))
        for row in res:
            print(row)

if __name__ == "__main__":
    check_notifications()
