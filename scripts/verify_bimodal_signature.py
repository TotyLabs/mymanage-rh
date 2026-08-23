from dotenv import load_dotenv; load_dotenv()
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from payroll_core import SessionLocal, safe_transaction
from services.document_repository import DocumentRepository
from modules.digital_signature import DigitalSignatureEngine
from sqlalchemy import text
import uuid

def verify():
    db = SessionLocal()
    try:
        # 1. Find an enterprise receipt
        res = db.execute(text("SELECT id, company_id, user_id FROM receipts LIMIT 1")).fetchone()
        if not res:
            print("No enterprise receipts found to test.")
            return
        
        rid = str(res.id)
        org_id = str(res.company_id)
        user_id = str(res.user_id)
        
        print(f"Testing with enterprise receipt: {rid}")
        
        # 2. Mock a signature request (Phase 1)
        # We need an employee_id for the engine. Let's find the employee linked to this user.
        emp = db.execute(text("SELECT e.id FROM employees e JOIN users u ON u.email = e.email AND u.organization_id = e.organization_id WHERE u.id = :uid"), {"uid": user_id}).fetchone()
        if not emp:
            print(f"User {user_id} has no linked employee profile. Skipping.")
            return
        
        emp_id = str(emp.id)
        
        with safe_transaction(db):
            # Test validate_and_lock
            print("Validating and locking...")
            ctx = DigitalSignatureEngine.validate_and_lock(db, rid, org_id, "employee", "test-sr-id")
            print(f"Context source: {ctx.get('source')}")
            assert ctx.get("source") == "enterprise"
            
            # Test update_document (Phase 3)
            print("Updating document status...")
            DocumentRepository.update_document(db, rid, "enterprise", status="pending_verification")
            
            # Verify update
            status = db.execute(text("SELECT status FROM receipts WHERE id = :id"), {"id": rid}).scalar()
            print(f"New status: {status}")
            assert status == "pending_verification"
            
            # Rollback to avoid polluting DB if needed, or just leave it for manual check
            # db.rollback()
            print("Verification logic passed (Dry Run portion).")
            
    except Exception as e:
        print(f"Verification FAILED: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    verify()
