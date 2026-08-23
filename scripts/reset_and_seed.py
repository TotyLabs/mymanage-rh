import os
import re
from datetime import datetime
from sqlalchemy import create_engine, text
import secrets
from payroll_core import hash_password, normalize_org_name

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set.")
    exit(1)
engine = create_engine(DATABASE_URL)

import traceback

def reset_db():
    print("Resetting database...")
    # Order matters if TRUNCATE CASCADE has issues, but CASCADE should handle it.
    # Let's try children first.
    tables = [
        "user_sessions", 
        "signature_evidence", 
        "signature_events", 
        "signature_requests", 
        "payroll_receipts", 
        "payroll_batches", 
        "audit_log",
        "users", 
        "employees", 
        "organizations"
    ]
    with engine.connect() as conn:
        for table in tables:
            try:
                conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
                conn.commit()
                print(f"Truncated {table}")
            except Exception as e:
                print(f"Error truncating {table}: {e}")
                # traceback.print_exc()
    print("Database reset attempt complete.")

def seed_data():
    print("Seeding test data...")
    with engine.begin() as conn:
        # Enable UUID extension
        conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        
        # 1. Create Company
        org_name = "ACME Payroll SA"
        normalized_name = normalize_org_name(org_name)
        org_id = conn.execute(text("""
            INSERT INTO organizations (name, slug, normalized_name)
            VALUES (:name, :slug, :normalized)
            RETURNING id
        """), {"name": org_name, "slug": "acme-payroll-sa", "normalized": normalized_name}).scalar()
        
        # 2. Create Admin User for Company
        admin_pass = secrets.token_urlsafe(12)
        pass_hash = hash_password(admin_pass)
        conn.execute(text("""
            INSERT INTO users (email, password_hash, full_name, role, organization_id)
            VALUES (:email, :pass, :name, 'admin', :org_id)
        """), {"email": "hr@acme.test", "pass": pass_hash, "name": "HR Admin", "org_id": org_id})
        
        print(f"--- ADMIN CREDENTIALS ---")
        print(f"Email: hr@acme.test")
        print(f"Password: {admin_pass}")
        print(f"-------------------------")
        
        # 3. Pre-register Employee
        emp_first_name = "Juan"
        emp_last_name = "PÃ©rez"
        emp_dni = "30111222"
        emp_id = conn.execute(text("""
            INSERT INTO employees (organization_id, first_name, last_name, dni, status, profile_completed)
            VALUES (:org, :fn, :ln, :dni, 'pre_registered', false)
            RETURNING id
        """), {"org": org_id, "fn": emp_first_name, "ln": emp_last_name, "dni": emp_dni}).scalar()
        
        print(f"Company ID: {org_id}")
        print(f"Employee (pre-registered) ID: {emp_id}")

if __name__ == "__main__":
    try:
        reset_db()
        seed_data()
        print("Seed data completed successfully.")
    except Exception:
        with open("seed_error.txt", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        print("Seed data failed. Check seed_error.txt")
        traceback.print_exc()
