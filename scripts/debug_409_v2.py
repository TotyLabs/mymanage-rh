import os, hashlib
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
load_dotenv()
engine = create_engine(os.getenv("DATABASE_URL"))
token = "4cfe3069452b2ccf3bf4cd7880a39b7e57623f9b0eb6764c34c37c07b54d9d01"
h = hashlib.sha256(token.encode()).hexdigest()
with engine.connect() as conn:
    r = conn.execute(text("SELECT sr.status as sr_s, r.status as r_s FROM signature_requests sr JOIN payroll_receipts r ON sr.receipt_id = r.id WHERE sr.token_hash = :h"), {"h": h}).fetchone()
    if r: print(f"SR:{r.sr_s}|R:{r.r_s}")
    else: print("NOTFOUND")
