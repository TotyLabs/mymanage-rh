
import os
import sys
from sqlalchemy import text
from payroll_core import SessionLocal, get_current_user

def test_current_user():
    db = SessionLocal()
    # Try to find a valid session token
    row = db.execute(text("SELECT session_token_hash FROM user_sessions LIMIT 1")).fetchone()
    if not row:
        print("No sessions found")
        return
    
    # We can't easily get the raw token from the hash, but we can mock get_current_user or modify it
    print("Session found, checking get_current_user return keys...")
    
    # Let's see what a row from the users table looks like
    user_row = db.execute(text("SELECT id, email FROM users LIMIT 1")).fetchone()
    if user_row:
        print(f"User row keys: {user_row._mapping.keys()}")
        print(f"User row id: {user_row.id}")
    
    db.close()

if __name__ == "__main__":
    test_current_user()
