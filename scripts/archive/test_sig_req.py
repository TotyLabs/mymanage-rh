import os
import sys

# Load env before importing core things
from config import DATABASE_URL

from payroll_core import SessionLocal, safe_transaction, create_signature_request

db = SessionLocal()

# We need an existing receipt + user. Let's find an enterprise receipt and its user
user_id = db.execute("SELECT user_id FROM receipts LIMIT 1").fetchone()
if not user_id:
    print("No enterprise receipts found to test!")
    sys.exit(0)

receipt = db.execute("SELECT id, company_id FROM receipts WHERE user_id = :uid LIMIT 1", {"uid": user_id[0]}).fetchone()

receipt_id = str(receipt[0])
org_id = str(receipt[1])
receiver_id = str(user_id[0])

print(f"Testing create_signature_request with bimodal fix:")
print(f"receipt_id: {receipt_id}")
print(f"org_id: {org_id}")
print(f"receiver_id / simulated employee_id: {receiver_id}")

try:
    with safe_transaction(db):
        res = create_signature_request(db, receipt_id, org_id, receiver_id)
        if res:
            print("SUCCESS! Token created:", res["token"])
        else:
            print("FAILED: create_signature_request returned None")
except Exception as e:
    import traceback
    print("FAILED with Exception:")
    traceback.print_exc()

db.close()
