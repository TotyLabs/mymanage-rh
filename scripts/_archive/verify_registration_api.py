import os
import sys
from fastapi.testclient import TestClient
from sqlalchemy import text

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from payroll_core import get_db

client = TestClient(app)

def verify_registration():
    print("Starting registration API verification...")
    
    # Payload matching the new frontend fields
    payload = {
        "email": "verification.test@example.com",
        "password": "Password123!",
        "full_name": "TEST VERIFICATION USER",
        "dni": "12345678",
        "cuil": "20123456789",
        "organization_name": "ACME Payroll SA",
        "marital_status": "single",
        "birth_date": "1995-10-10",
        "address": "Test Street 456",
        "phone": "555-0199",
        "position": "Tester",
        "hire_date": "2023-01-15"
    }

    # Ensure organization exists
    db = next(get_db())
    db.execute(text("INSERT INTO organizations (name, slug, normalized_name) VALUES ('ACME Payroll SA', 'acme-payroll-sa', 'ACME PAYROLL SA') ON CONFLICT DO NOTHING"))
    org = db.execute(text("SELECT id FROM organizations WHERE slug='acme-payroll-sa'")).fetchone()
    
    # Pre-register employee (required by backend logic)
    db.execute(text("DELETE FROM users WHERE email=:email"), {"email": payload["email"]})
    db.execute(text("DELETE FROM employees WHERE dni=:dni"), {"dni": payload["dni"]})
    db.execute(text("""
        INSERT INTO employees (organization_id, first_name, last_name, dni, cuil, status)
        VALUES (:org_id, :fname, :lname, :dni, :cuil, 'pre_registered')
    """), {"org_id": org.id, "fname": "TEST VERIFICATION", "lname": "USER", "dni": payload["dni"], "cuil": payload["cuil"]})
    db.commit()

    print("Step 1: Sending registration request...")
    response = client.post("/api/auth/register-employee", json=payload)
    
    if response.status_code != 200:
        print(f"âŒ Registration failed: {response.status_code}")
        print(f"Response: {response.text}")
        return False
    
    print("âœ… Registration response: 200 OK")
    
    print("Step 2: Verifying database synchronization...")
    # Check Employee
    emp = db.execute(text("SELECT * FROM employees WHERE dni=:dni"), {"dni": payload["dni"]}).fetchone()
    if not (emp.status == "active" and emp.profile_completed and emp.marital_status == "single" and str(emp.birth_date).startswith("1995-10-10")):
        print(f"âŒ Employee record discrepancy: marital={emp.marital_status}, birth={emp.birth_date}, status={emp.status}")
        return False
    print("âœ… Employee record correctly updated.")

    # Check User
    user = db.execute(text("SELECT * FROM users WHERE email=:email"), {"email": payload["email"]}).fetchone()
    if not user:
        print(f"âŒ User record correctly created with profile fields.")
        return False
    print("âœ… User record correctly created.")

    print("\nðŸŽ‰ SUCCESS: Frontend-Backend integration for multi-field onboarding verified!")
    return True

if __name__ == "__main__":
    if verify_registration():
        sys.exit(0)
    else:
        sys.exit(1)
