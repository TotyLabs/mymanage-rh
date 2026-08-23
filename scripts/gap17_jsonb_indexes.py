import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
from sqlalchemy import create_engine, text
from config import DATABASE_URL

engine = create_engine(DATABASE_URL)
with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
    print("Creating index on DNI...")
    conn.execute(text("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_receipts_dni ON payroll_receipts ((extracted_fields->>'dni'))"))
    print("Creating index on Periodo...")
    conn.execute(text("CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_receipts_period ON payroll_receipts ((extracted_fields->>'periodo'))"))
    print("Concurrent indexes created successfully.")
