import sys, os, pprint
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import create_engine, text

engine=create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    res = conn.execute(text("SELECT id, status, employee_id, employer_signed_at, employee_signed_at FROM payroll_receipts WHERE batch_id = 'b54a45fb-245f-4e83-916f-e4e092235afd'"))
    pprint.pprint([dict(r._mapping) for r in res])
