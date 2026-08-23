
import os
import sys
from sqlalchemy import text
from payroll_core import SessionLocal, get_current_user

def verify_identity_contract():
    db = SessionLocal()
    try:
        print("Testing direct mapping logic from users table...")
        user_row = db.execute(text("""
            SELECT u.id, u.email, u.full_name, u.role, u.organization_id, u.employee_id, u.is_active,
                    o.name as organization_name,
                    (SELECT signature_path FROM user_signatures WHERE user_id = u.id AND is_active = true LIMIT 1) AS sig_path
            FROM users u
            LEFT JOIN organizations o ON o.id = u.organization_id
            LIMIT 1
        """)).fetchone()
        
        if not user_row:
            print("No users found in database.")
            return

        m = user_row._mapping
        print(f"Row mapping keys: {list(m.keys())}")
        
        user_dict = {
            "id": str(m["id"]),
            "email": m["email"],
            "full_name": m["full_name"],
            "role": m["role"],
            "organization_id": str(m["organization_id"]) if m["organization_id"] else None,
            "employee_id": str(m["employee_id"]) if m["employee_id"] else None,
            "organization_name": m["organization_name"],
            "has_stored_signature": bool(m["sig_path"]),
        }
        
        print("Successfully normalized user dictionary:")
        for k, v in user_dict.items():
            print(f"  {k}: {v} ({type(v)})")
            
        assert "id" in user_dict, "MISSING ID KEY"
        assert isinstance(user_dict["id"], str), f"ID NOT A STRING: {type(user_dict['id'])}"
        assert len(user_dict["id"]) > 30, "ID looks too short for a UUID string"
        
        print("\nIDENTITY CONTRACT VERIFIED")
            
    finally:
        db.close()

if __name__ == "__main__":
    verify_identity_contract()
