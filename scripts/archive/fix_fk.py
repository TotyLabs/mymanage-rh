import subprocess
from dotenv import load_dotenv
import os

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("No DATABASE_URL found in .env")
    exit(1)

# Drop the wrong FK and add the right one
sql = """
ALTER TABLE signature_events DROP CONSTRAINT signature_events_receipt_id_fkey;
ALTER TABLE signature_events ADD CONSTRAINT signature_events_receipt_id_fkey FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE;
"""

subprocess.run(["psql", db_url, "-c", sql])
