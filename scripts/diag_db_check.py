import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

target_org = 'd65d46ef-0b7b-4ac0-a0f4-da5c30f06e5a'
target_signer = '2b656fee-e393-49e4-adab-992ab072ad58'

print("--- TARGETED DB CHECK ---")
with engine.connect() as conn:
    res = conn.execute(text("SELECT count(*) FROM organizations WHERE id = :id"), {"id": target_org}).scalar()
    print(f"ORG_EXISTS({target_org}): {res > 0}")
    
    res = conn.execute(text("SELECT count(*) FROM company_signers WHERE id = :id"), {"id": target_signer}).scalar()
    print(f"SIGNER_EXISTS({target_signer}): {res > 0}")
