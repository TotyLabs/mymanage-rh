import os
import re
import fitz
from sqlalchemy import create_engine, text
import sys
import secrets
from dotenv import load_dotenv

load_dotenv()

# Ensure core is found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from payroll_core import hash_password, normalize_org_name

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set.")
    exit(1)
engine = create_engine(DATABASE_URL)

def reset_db():
    print("Resetting database...")
    tables = [
        "user_sessions", "signature_evidence", "signature_events", 
        "signature_requests", "payroll_receipts", "payroll_batches", 
        "audit_log", "users", "employees", "organizations"
    ]
    with engine.connect() as conn:
        for table in tables:
            try:
                conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                conn.commit()
            except Exception as e:
                pass
    print("Database reset complete.")

def extract_employees_from_pdf(pdf_path):
    print(f"Extracting expected employees from {pdf_path}...")
    doc = fitz.open(pdf_path)
    employees = {}
    
    for page in doc:
        lines = page.get_text().split("\n")
        
        for i, line in enumerate(lines):
            line = line.strip()
            # Look for CUIL format
            m = re.match(r"^(\d{2})-(\d{7,8})-(\d{1})$", line)
            if m:
                cuil = line
                dni = m.group(2)
                # the line above might be the name
                name = lines[i-1].strip()
                
                if name and "CUIT" not in name.upper() and "C.U.I.T" not in name.upper() and not re.match(r'^\d', name) and name != "Laferrere":
                    if cuil not in employees:
                        if name != "FLEITAS ROMERO JULIO CESAR":
                            # split name into first and last
                            parts = name.split(" ", 1)
                            first = parts[0]
                            last = parts[1] if len(parts) > 1 else ""
                            employees[cuil] = {"first_name": first, "last_name": last, "dni": dni, "cuil": cuil}
    
    return list(employees.values())

def seed_data():
    emps_data = extract_employees_from_pdf("test.pdf")
    print(f"Found {len(emps_data)} employees in PDF.")
    
    with engine.begin() as conn:
        # Enable uuid-ossp if not already created
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        
        # Create company
        org_name = "Antigravity Test Company"
        normalized_name = normalize_org_name(org_name)
        org_id = conn.execute(text("""
            INSERT INTO organizations (name, slug, normalized_name)
            VALUES (:name, :slug, :normalized) RETURNING id
        """), {"name": org_name, "slug": "antigravity-test-company", "normalized": normalized_name}).scalar()
        
        # Create admin user
        admin_pass = secrets.token_urlsafe(12)
        pass_hash = hash_password(admin_pass)
        conn.execute(text("""
            INSERT INTO users (email, password_hash, full_name, role, organization_id)
            VALUES (:email, :pass, :name, 'admin', :org_id)
        """), {"email": "admin@antigravity.test", "pass": pass_hash, "name": "Admin Antigravity", "org_id": org_id})
        
        print(f"--- ADMIN CREDENTIALS ---")
        print(f"Email: admin@antigravity.test")
        print(f"Pass: {admin_pass}")
        print(f"Organization ID: {org_id}")
        
        print("\n--- EMPLOYEES CREATED ---")
        for e in emps_data:
            conn.execute(text("""
                INSERT INTO employees (organization_id, first_name, last_name, dni, cuil, status, profile_completed)
                VALUES (:org, :fn, :ln, :dni, :cuil, 'pre_registered', false)
            """), {"org": org_id, "fn": e["first_name"], "ln": e["last_name"], "dni": e["dni"], "cuil": e["cuil"]})
            print(f"- Name: {e['first_name']} {e['last_name']} | DNI: {e['dni']} | CUIL: {e['cuil']}")

if __name__ == "__main__":
    reset_db()
    seed_data()
    print("Done")
