import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

with open('diag_full_output.log', 'w') as f:
    f.write("--- FULL DIAGNOSTICS ---\n")
    with engine.connect() as conn:
        f.write("\n[ORGANIZATIONS]\n")
        res = conn.execute(text("SELECT id, name, logo_path FROM organizations")).fetchall()
        for row in res:
            p = row.logo_path if row.logo_path else "NONE"
            exists = Path(p).exists() if p != "NONE" else False
            f.write(f"ID: {row.id} | Name: {row.name} | Path: {p} | Exists: {exists}\n")

        f.write("\n[COMPANY SIGNERS]\n")
        res = conn.execute(text("SELECT id, name, signature_image_path FROM company_signers")).fetchall()
        for row in res:
            p = row.signature_image_path if row.signature_image_path else "NONE"
            exists = Path(p).exists() if p != "NONE" else False
            f.write(f"ID: {row.id} | Name: {row.name} | Path: {p} | Exists: {exists}\n")
    f.write("\n--- END ---\n")
