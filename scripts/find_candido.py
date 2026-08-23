import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

print("--- FINDING PRE-REGISTERED EMPLOYEE ---")
with engine.connect() as conn:
    res = conn.execute(text("""
        SELECT e.first_name, e.last_name, e.dni, e.status, o.name as org_name
        FROM employees e
        JOIN organizations o ON e.organization_id = o.id
        WHERE e.status = 'pre_registered'
        OR e.first_name ILIKE '%CANDIDO%'
        OR e.last_name ILIKE '%CANDIDO%'
    """)).fetchall()
    
    if not res:
        print("NO EMPLOYEES FOUND")
    for r in res:
        print(f"EMP: {r.first_name} {r.last_name} | DNI: {r.dni} | Status: {r.status} | ORG: {r.org_name}")
