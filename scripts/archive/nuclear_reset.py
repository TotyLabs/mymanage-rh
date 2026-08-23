import os
import shutil
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# --- PROTECTION CHECK ---
if os.getenv("PRODUCTION") == "true" or os.getenv("ENV") == "production":
    raise Exception("🚨 Refusing to run in PRODUCTION environment")

print("⚠️  WARNING: This will PERMANENTLY DELETE all data from the database and storage.")
confirm = input("Type 'DELETE ALL DATA' to continue: ")
if confirm != "DELETE ALL DATA":
    print("❌ Aborted.")
    exit(1)

if not DATABASE_URL:
    print("❌ Error: DATABASE_URL not set.")
    exit(1)

engine = create_engine(DATABASE_URL)

# Comprehensive list to ensure a true NUCLEAR reset
TRUNCATE_SQL = """
TRUNCATE TABLE 
    users, 
    organizations, 
    employees,
    employee_extra_data,
    company_signers,
    receipts, 
    payroll_receipts, 
    payroll_batches,
    signature_requests, 
    signature_evidence,
    signature_events, 
    notifications, 
    user_sessions, 
    verification_codes, 
    user_signatures, 
    import_jobs, 
    import_job_rows,
    audit_log,
    email_events,
    signing_logs,
    webhook_outbox
RESTART IDENTITY CASCADE;
"""

print("--- Purging Database ---")
try:
    with engine.begin() as conn:
        conn.execute(text(TRUNCATE_SQL))
    print("✔️ Database wiped successfully.")
except Exception as e:
    print(f"❌ Database purge failed: {e}")
    exit(1)

# --- STORAGE WIPE ---
storage_path = Path("./storage").resolve()

# Safety check for path
if "storage" not in str(storage_path):
    raise Exception("🚨 Unsafe storage path detected")

print(f"--- Cleaning Storage: {storage_path} ---")
if storage_path.exists():
    try:
        shutil.rmtree(storage_path)
        storage_path.mkdir(parents=True, exist_ok=True)
        print("✔️ Storage wiped successfully.")
    except Exception as e:
        print(f"❌ Storage wipe failed: {e}")
else:
    storage_path.mkdir(parents=True, exist_ok=True)
    print("⚠️ Storage path did not exist, created empty folder.")

print("\n🚀 NUCLEAR RESET COMPLETE. The environment is now empty.")
