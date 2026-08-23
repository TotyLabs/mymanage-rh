import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

print("--- RECOVERING ORGANIZATION INFO ---")
with engine.connect() as conn:
    # 1. Search audit_log (singular)
    # Using 'data' column
    res = conn.execute(text("""
        SELECT o.name, a.organization_id, a.data, a.created_at
        FROM audit_log a
        LEFT JOIN organizations o ON a.organization_id = o.id
        WHERE a.data::text ILIKE '%CANDIDO%'
        ORDER BY a.created_at DESC
        LIMIT 10
    """)).fetchall()
    
    if not res:
        print("NO AUDIT LOGS FOUND FOR CANDIDO IN audit_log")
        # Fallback: just list all organizations
        print("\n--- ALL ORGANIZATIONS ---")
        orgs = conn.execute(text("SELECT id, name FROM organizations")).fetchall()
        for o in orgs:
            print(f"ORG: {o.id} | Name: {o.name}")
    else:
        for r in res:
            print(f"FOUND: Org '{r.name}' ({r.organization_id}) | Data: {r.data}")
