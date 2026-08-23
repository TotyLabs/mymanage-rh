import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

print("--- ORG LOGO AUDIT ---")
with engine.connect() as conn:
    res = conn.execute(text("SELECT id, name, logo_path FROM organizations")).fetchall()
    for r in res:
        exists = " - FILE EXISTS" if r.logo_path and os.path.exists(r.logo_path) else " - FILE MISSING" if r.logo_path else " - NO PATH DEFINED"
        print(f"ORG: {r.name} ({r.id}) | LOGO: {r.logo_path}{exists}")

print("\n--- COMPANY SIGNERS IMAGE AUDIT ---")
with engine.connect() as conn:
    res = conn.execute(text("SELECT id, name, organization_id, signature_image_path FROM company_signers")).fetchall()
    for r in res:
        exists = " - FILE EXISTS" if r.signature_image_path and os.path.exists(r.signature_image_path) else " - FILE MISSING" if r.signature_image_path else " - NO PATH DEFINED"
        print(f"SIGNER: {r.name} ({r.id}) | ORG_ID: {r.organization_id} | IMAGE: {r.signature_image_path}{exists}")

print("\n--- CHECKING STORAGE DIRECTORY ---")
storage_path = os.getenv('STORAGE_PATH', 'storage')
print(f"STORAGE_PATH: {storage_path} (exists: {os.path.exists(storage_path)})")
if os.path.exists(storage_path):
    print("Listing storage subdirs:")
    for item in os.listdir(storage_path):
        p = os.path.join(storage_path, item)
        if os.path.isdir(p):
            print(f" - {item}/")
