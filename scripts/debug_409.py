import os
import hashlib
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

token = "4cfe3069452b2ccf3bf4cd7880a39b7e57623f9b0eb6764c34c37c07b54d9d01"
token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

print(f"Token: {token}")
print(f"Token Hash: {token_hash}")

with engine.connect() as conn:
    # Check signature_request
    sr = conn.execute(text("""
        SELECT id, receipt_id, status, token_expires_at
        FROM signature_requests
        WHERE token_hash = :hash
    """), {"hash": token_hash}).fetchone()
    
    if sr:
        print(f"Signature Request ID: {sr.id}")
        print(f"Receipt ID: {sr.receipt_id}")
        print(f"SR Status: {sr.status}")
        print(f"SR Expires: {sr.token_expires_at}")
        
        # Check payroll_receipt
        pr = conn.execute(text("""
            SELECT id, status, employee_id, organization_id
            FROM payroll_receipts
            WHERE id = :rid
        """), {"rid": sr.receipt_id}).fetchone()
        
        if pr:
            print(f"Receipt Status: {pr.status}")
            print(f"Employee ID: {pr.employee_id}")
            print(f"Org ID: {pr.organization_id}")
        else:
            print("Receipt NOT found!")
    else:
        print("Signature Request NOT found!")
