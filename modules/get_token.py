import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.append(os.getcwd())

from payroll_core import SessionLocal, create_signature_request
from sqlalchemy import text

db = SessionLocal()
try:
    r = db.execute(text("SELECT id, organization_id, employee_id FROM payroll_receipts WHERE status = 'pending_signature' LIMIT 1")).fetchone()
    if r:
        res = create_signature_request(db, str(r.id), str(r.organization_id), str(r.employee_id))
        db.commit()
        print(res['token'])
    else:
        print('None')
finally:
    db.close()
