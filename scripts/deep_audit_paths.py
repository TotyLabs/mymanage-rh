import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

base_dir = os.getcwd()
print(f"--- FOLDER AUDIT ---")
print(f"Current Working Directory (CWD): {base_dir}")

def check_path(p):
    if not p: return "NO PATH"
    exists_abs = os.path.exists(p)
    
    # Try reconstructing relative to CWD if it looks like it was from another machine
    # e.g. C:\Users\Someone\...\storage\orgs\... -> storage\orgs\...
    rel_candidate = None
    if 'storage' in p.lower():
        parts = p.lower().split('storage', 1)
        rel_candidate = os.path.join(base_dir, 'storage' + parts[1].replace('/', os.sep).replace('\\', os.sep))
    
    exists_rel = os.path.exists(rel_candidate) if rel_candidate else False
    
    res = []
    if exists_abs: res.append("EXISTS_ABS")
    if exists_rel: res.append(f"EXISTS_RECONSTRUCTED_REL ({rel_candidate})")
    
    if not res: return f"NOT FOUND (Tried absolute: {p})"
    return " | ".join(res)

print("\n--- ORGANIZATIONS LOGO PATHS ---")
with engine.connect() as conn:
    res = conn.execute(text("SELECT name, logo_path FROM organizations")).fetchall()
    for r in res:
        status = check_path(r.logo_path)
        print(f"ORG: {r.name} | DB_PATH: {r.logo_path} | STATUS: {status}")

print("\n--- SIGNERS SIGNATURE PATHS ---")
with engine.connect() as conn:
    res = conn.execute(text("SELECT name, signature_image_path FROM company_signers")).fetchall()
    for r in res:
        status = check_path(r.signature_image_path)
        print(f"SIGNER: {r.name} | DB_PATH: {r.signature_image_path} | STATUS: {status}")
