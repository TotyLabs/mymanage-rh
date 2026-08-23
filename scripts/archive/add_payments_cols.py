import subprocess
from dotenv import load_dotenv
import os

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("No DATABASE_URL found in .env")
    exit(1)

# Add missing payment columns to Receipts
sql = """
ALTER TABLE receipts ADD COLUMN payment_receipt_path TEXT;
ALTER TABLE receipts ADD COLUMN payment_upload_date TIMESTAMP WITH TIME ZONE;
ALTER TABLE receipts ADD COLUMN payment_uploaded_by UUID REFERENCES users(id) ON DELETE SET NULL;
"""

subprocess.run(["psql", db_url, "-c", sql])
