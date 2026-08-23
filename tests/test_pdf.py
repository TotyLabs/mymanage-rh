import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.append(os.getcwd())

from services.employee_pdf_service import EmployeePDFService
from payroll_core import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # Get any employee
    r = db.execute(text("SELECT id, organization_id FROM employees LIMIT 1")).fetchone()
    if r:
        pdf_bytes = EmployeePDFService(db).generate_record_pdf(str(r.id), str(r.organization_id))
        with open('test_record.pdf', 'wb') as f:
            f.write(pdf_bytes)
        print(f"PDF generated for employee {r.id}. Size: {len(pdf_bytes)} bytes.")
    else:
        print("No employee found in database.")
except Exception as e:
    print(f"Error generating PDF: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
