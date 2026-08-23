import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.environ['DATABASE_URL'])

with engine.connect() as conn:
    print('Receipt info:')
    res = conn.execute(text("SELECT id, status, employer_signed_at, employee_signed_at FROM payroll_receipts WHERE id = 'fb6934ba-d289-4ceb-8836-0617e49787e4'"))
    for r in res:
        print(dict(r._mapping))
        
    print('Evidence count:')
    res = conn.execute(text("SELECT COUNT(*) FROM signature_evidence WHERE receipt_id = 'fb6934ba-d289-4ceb-8836-0617e49787e4'"))
    print(res.scalar())
