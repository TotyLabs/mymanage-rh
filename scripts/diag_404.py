import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

print("--- DIAGNOSTICS ---")
with engine.connect() as conn:
    print("\n[ORGANIZATIONS]")
    res = conn.execute(text("SELECT id, name, logo_path FROM organizations")).fetchall()
    for row in res:
        exists = Path(row.logo_path).exists() if row.logo_path else False
        print(f"ID: {row.id} | Name: {row.name} | Path: {row.logo_path} | Exists: {exists}")

    print("\n[COMPANY SIGNERS]")
    res = conn.execute(text("SELECT id, name, signature_image_path FROM company_signers")).fetchall()
    for row in res:
        exists = Path(row.signature_image_path).exists() if row.signature_image_path else False
        print(f"ID: {row.id} | Name: {row.name} | Path: {row.signature_image_path} | Exists: {exists}")
