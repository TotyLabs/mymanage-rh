import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

target_org = 'd65d46ef-0b7b-4ac0-a0f4-da5c30f06e5a'
target_signer = '2b656fee-e393-49e4-adab-992ab072ad58'

with open('diag_targeted_db.log', 'w') as f:
    f.write("--- TARGETED DB CHECK ---\n")
    with engine.connect() as conn:
        f.write("\n[ORGANIZATION]\n")
        res = conn.execute(text("SELECT id, name, logo_path FROM organizations WHERE id = :id"), {"id": target_org}).fetchone()
        if res:
            p = res.logo_path if res.logo_path else "NONE"
            exists = Path(p).exists() if p != "NONE" else False
            f.write(f"ID: {res.id} | Name: {res.name} | Path: {p} | Exists: {exists}\n")
        else:
            f.write(f"ORG {target_org} NOT FOUND\n")
            
        f.write("\n[COMPANY SIGNER]\n")
        res = conn.execute(text("SELECT id, name, signature_image_path FROM company_signers WHERE id = :id"), {"id": target_signer}).fetchone()
        if res:
            p = res.signature_image_path if res.signature_image_path else "NONE"
            exists = Path(p).exists() if p != "NONE" else False
            f.write(f"ID: {res.id} | Name: {res.name} | Path: {p} | Exists: {exists}\n")
        else:
            f.write(f"SIGNER {target_signer} NOT FOUND\n")
