import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

target_org = 'd65d46ef-0b7b-4ac0-a0f4-da5c30f06e5a'
target_signer = '2b656fee-e393-49e4-adab-992ab072ad58'

print("--- TARGETED DIAGNOSTICS ---")
with engine.connect() as conn:
    print("\n[ORGANIZATION]")
    res = conn.execute(text("SELECT id, name, logo_path FROM organizations WHERE id = :id"), {"id": target_org}).fetchone()
    if res:
        exists = Path(res.logo_path).exists() if res.logo_path else False
        print(f"ID: {res.id} | Name: {res.name} | Path: {res.logo_path} | Exists: {exists}")
    else:
        print(f"Org {target_org} not found in DB.")

    print("\n[COMPANY SIGNER]")
    res = conn.execute(text("SELECT id, name, signature_image_path FROM company_signers WHERE id = :id"), {"id": target_signer}).fetchone()
    if res:
        exists = Path(res.signature_image_path).exists() if res.signature_image_path else False
        print(f"ID: {res.id} | Name: {res.name} | Path: {res.signature_image_path} | Exists: {exists}")
    else:
        print(f"Signer {target_signer} not found in DB.")
