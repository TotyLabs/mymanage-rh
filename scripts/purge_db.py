import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not found in .env")
    exit(1)

engine = create_engine(DATABASE_URL)

TABLES_TO_PURGE = [
    "verification_codes",
    "user_sessions",
    "password_reset_tokens",
    "user_signatures",
    "signing_logs",
    "signature_evidence",
    "signature_requests",
    "signature_events",
    "receipt_seals",
    "email_events",
    "webhook_outbox",
    "file_encryption_metadata",
    "audit_log",
    "receipts",
    "payroll_receipts",
    "payroll_batches",
    "employee_extra_data",
    "import_job_rows",
    "import_jobs",
    "notifications",
    "company_signers",
    "registration_keys",
    "users",
    "employees",
    "organizations"
]

def purge():
    print("Starting Database Purge (Connection Mode)...")
    try:
        with engine.begin() as conn:
            # Disable triggers
            print("Disabling triggers...")
            conn.execute(text("SET session_replication_role = 'replica'"))
            
            # Break cycles
            print("Breaking user-employee cycle...")
            conn.execute(text("UPDATE users SET employee_id = NULL"))
            
            for table in TABLES_TO_PURGE:
                print(f"Purging table: {table}...")
                result = conn.execute(text(f"DELETE FROM {table}"))
                print(f"  Deleted {result.rowcount} rows.")
            
            # Re-enable triggers
            print("Re-enabling triggers...")
            conn.execute(text("SET session_replication_role = 'origin'"))
            
            # Reset sequences
            print("Resetting sequences...")
            # We skip sequence reset for now to ensure deletion works first
            
        print("Database Purge Completed Successfully (Committed).")
    except Exception as e:
        print(f"Error during database purge: {e}")
        exit(1)

if __name__ == "__main__":
    purge()
