import os
import shutil
import argparse
import sys
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
IS_PRODUCTION = os.getenv("PRODUCTION", "false").lower() == "true"
STORAGE_PATH = os.getenv("STORAGE_PATH", "./storage")

def purge_database(confirm=False):
    if not confirm:
        print("❌ Error: Confirmation required. Run with --confirm flag.")
        sys.exit(1)

    if IS_PRODUCTION:
        print("❌ CRITICAL ERROR: Refusing to purge database in PRODUCTION environment.")
        print("Set PRODUCTION=false in .env if this is wrong.")
        sys.exit(1)

    if not DATABASE_URL:
        print("❌ Error: DATABASE_URL not set in .env")
        sys.exit(1)

    print("--- Starting Nuclear Purge ---")
    
    engine = create_engine(DATABASE_URL)
    
    # 1. Identify tables to purge
    inspector = inspect(engine)
    all_tables = inspector.get_table_names()
    
    exclude_tables = ["alembic_version", "system_config"]
    tables_to_purge = [t for t in all_tables if t not in exclude_tables]
    
    print(f"Tables to purge: {len(tables_to_purge)}")
    
    with engine.begin() as conn:
        for table in tables_to_purge:
            try:
                # RESTART IDENTITY resets sequences
                # CASCADE handles foreign key dependencies
                conn.execute(text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE;'))
                print(f"✔️ Truncated {table}")
            except Exception as e:
                print(f"⚠️ Error truncating {table}: {e}")

    # 2. Storage cleanup
    abs_storage_path = os.path.abspath(STORAGE_PATH)
    print(f"--- Cleaning Storage: {abs_storage_path} ---")
    
    if os.path.exists(abs_storage_path):
        for item in os.listdir(abs_storage_path):
            item_path = os.path.join(abs_storage_path, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    os.makedirs(item_path, exist_ok=True) # Keep the subdirectory structure if wanted, or just wipe it
                    print(f"✔️ Cleared directory: {item}")
                else:
                    os.remove(item_path)
                    print(f"✔️ Deleted file: {item}")
            except Exception as e:
                print(f"⚠️ Error cleaning {item}: {e}")
    else:
        print("⚠️ Storage path does not exist.")

    print("--- Purge Complete ---")
    
    # 3. Verification
    print("--- Verification ---")
    with engine.connect() as conn:
        for table in ["users", "organizations", "employees", "receipts"]:
            if table in all_tables:
                count = conn.execute(text(f'SELECT count(*) FROM "{table}"')).scalar()
                status = "✔️ OK (0 rows)" if count == 0 else f"❌ FAILED ({count} rows)"
                print(f"{table}: {status}")
    
    alembic_check = "alembic_version" in all_tables
    print(f"alembic_version exists: {'✔️ Yes' if alembic_check else '❌ No'}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge database and storage for a clean slate.")
    parser.add_argument("--confirm", action="store_true", help="Explicitly confirm the destructive action.")
    
    args = parser.parse_args()
    purge_database(confirm=args.confirm)
