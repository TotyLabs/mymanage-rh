import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

with open('diag_raw_paths.log', 'w') as f:
    with engine.connect() as conn:
        for t, i in [('organizations','d65d46ef-0b7b-4ac0-a0f4-da5c30f06e5a'), ('company_signers','2b656fee-e393-49e4-adab-992ab072ad58')]:
            col = 'logo_path' if t=='organizations' else 'signature_image_path'
            r = conn.execute(text(f"SELECT {col} FROM {t} WHERE id = :id"), {"id": i}).fetchone()
            f.write(f"{t} ({i}) -> {r[0] if r else 'NOT FOUND'}\n")
