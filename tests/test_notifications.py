import sys
import os
import uuid
from io import BytesIO
from fastapi.testclient import TestClient

# Add parent directory to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from sqlalchemy.orm import Session
from payroll_core import SessionLocal, require_auth
from models.tables import Organization, User, Notification
from payroll_core import SessionLocal, require_auth
import config

def test_notification_flow():
    client = TestClient(app)
    db = SessionLocal()
    
    # 1. Setup mock org and users in DB
    org_id = str(uuid.uuid4())
    emp_user_id = str(uuid.uuid4())
    admin_user_id = str(uuid.uuid4())
    
    org = Organization(id=org_id, name="Test Company", slug=f"test-{org_id[:8]}", email="admin@test.com")
    db.add(org)
    db.commit()

    emp_user = User(id=emp_user_id, organization_id=org_id, role="employee", email="employee@test.com", password_hash="dummy", full_name="Emp Test")
    admin_user = User(id=admin_user_id, organization_id=org_id, role="admin", email="admin@test.com", password_hash="dummy", full_name="Admin Test")
    db.add_all([emp_user, admin_user])
    db.commit()

    try:
        # Override auth to simulate employee
        app.dependency_overrides[require_auth] = lambda: {
            "sub": emp_user_id,
            "user_id": emp_user_id,
            "organization_id": org_id,
            "role": "employee",
            "email": "employee@test.com"
        }

        print("Testing POST /api/notifications (Employee)...")
        # Multipart form data test
        files = {
            'file': ('test.txt', BytesIO(b"Hello secure world"), 'text/plain')
        }
        data = {
            'message': 'This is a test notification'
        }
        
        response = client.post("/api/notifications", data=data, files=files)
        assert response.status_code == 200, f"Expected 200 OK, got {response.status_code}: {response.text}"
        notif_id = response.json()["id"]
        print("OK: Notification created successfully")

        # Now simulate admin
        app.dependency_overrides[require_auth] = lambda: {
            "sub": admin_user_id,
            "user_id": admin_user_id,
            "organization_id": org_id,
            "role": "admin",
            "email": "admin@test.com"
        }

        print("Testing GET /api/notifications (Company/Admin)...")
        response = client.get("/api/notifications")
        assert response.status_code == 200
        notifs = response.json().get("notifications", [])
        assert len(notifs) >= 1
        assert notifs[0]["id"] == notif_id
        assert notifs[0]["has_file"] is True
        assert notifs[0]["is_read"] is False
        print("OK: Company can view the notification list")

        print("Testing GET /api/notifications/{id}/file (Company/Admin)...")
        response = client.get(f"/api/notifications/{notif_id}/file")
        assert response.status_code == 200
        assert response.content == b"Hello secure world"
        print("OK: Admin can read the attached file successfully")
        
        # Test employee cannot read file
        app.dependency_overrides[require_auth] = lambda: {
            "sub": emp_user_id,
            "user_id": emp_user_id,
            "organization_id": org_id,
            "role": "employee"
        }
        response = client.get(f"/api/notifications/{notif_id}/file")
        assert response.status_code == 403
        print("OK: Employee is blocked from accessing the file endpoint directly")

    finally:
        # Cleanup
        app.dependency_overrides.clear()
        
        # Delete dummy data
        db.query(Notification).filter(Notification.company_id == org_id).delete()
        db.query(User).filter(User.organization_id == org_id).delete()
        db.query(Organization).filter(Organization.id == org_id).delete()
        db.commit()
        db.close()

if __name__ == "__main__":
    test_notification_flow()
    print("All backend tests for Notifications PASSED. \n")
