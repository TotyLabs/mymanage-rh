import subprocess
from dotenv import load_dotenv
import os

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("No DATABASE_URL found in .env")
    exit(1)

# Drop the wrong FK and add the right one for signature_evidence
sql = """
ALTER TABLE signature_evidence DROP CONSTRAINT fk_signature_evidence_receipt_id_payroll_receipts;
ALTER TABLE signature_evidence ADD CONSTRAINT fk_signature_evidence_receipt_id_receipts FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE;
"""

subprocess.run(["psql", db_url, "-c", sql])
