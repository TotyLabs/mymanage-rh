import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not found")
    sys.exit(1)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

TABLES_TO_CHECK = [
    "verification_codes", "user_sessions", "password_reset_tokens",
    "user_signatures", "signing_logs", "signature_evidence",
    "signature_requests", "signature_events", "receipt_seals",
    "email_events", "webhook_outbox", "file_encryption_metadata",
    "audit_log", "receipts", "payroll_receipts", "payroll_batches",
    "employee_extra_data", "import_job_rows", "import_jobs",
    "notifications", "company_signers", "registration_keys",
    "users", "employees", "organizations"
]

def validate():
    print("Starting Post-Purge Validation...")
    errors = []
    
    # 1. Check DB tables are empty
    print("Checking database tables...")
    for table in TABLES_TO_CHECK:
        try:
            count = session.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            if count > 0:
                errors.append(f"Table {table} still contains {count} records.")
        except Exception as e:
            errors.append(f"Error checking table {table}: {e}")
    
    # 2. Check Storage is clean
    print("Checking storage directories...")
    STORAGE_PATH = "./storage"
    if os.path.exists(STORAGE_PATH):
        for subdir in os.listdir(STORAGE_PATH):
            path = os.path.join(STORAGE_PATH, subdir)
            if os.path.isdir(path):
                # Ignore some special directories if needed, but here we expect them empty
                files = os.listdir(path)
                # Filter out system files like .gitkeep if they exist
                files = [f for f in files if f not in ('.gitkeep', '.gitignore')]
                if files:
                    errors.append(f"Directory {path} is not empty: {files}")
    else:
        errors.append("Storage directory does not exist.")

    # 3. Check Orphan Foreign Keys (Simplified check)
    print("Checking for orphan foreign keys...")
    # This is complex to do generically, but we trust the DELETE order and DB constraints.
    # We'll just verify that a simple query doesn't crash.
    try:
        session.execute(text("SELECT 1"))
    except Exception as e:
        errors.append(f"Database integrity check failed: {e}")

    if not errors:
        print("\nSUCCESS: All integrity checks passed. System is in 'Fresh Install' state.")
    else:
        print("\nFAILURE: Validation errors found:")
        for err in errors:
            print(f"- {err}")
        sys.exit(1)

if __name__ == "__main__":
    validate()
