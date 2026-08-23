import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from sqlalchemy import create_engine, text
from config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.begin() as conn:
    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_attempts INT DEFAULT 0"))
    conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP WITH TIME ZONE"))
print("Auth lock columns added successfully.")
