import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

with open('diag_users_orgs.log', 'w') as f:
    with engine.connect() as conn:
        f.write("\n[USERS]\n")
        res = conn.execute(text("SELECT id, full_name, organization_id FROM users")).fetchall()
        for r in res:
            f.write(f"USER: {r.id} | {r.full_name} | ORG: {r.organization_id}\n")
            
        f.write("\n[ORGANIZATIONS]\n")
        res = conn.execute(text("SELECT id, name FROM organizations")).fetchall()
        for r in res:
            f.write(f"ORG: {r.id} | {r.name}\n")
