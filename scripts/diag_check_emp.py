import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

name_pattern = '%CANDIDO%'

print(f"--- SEARCHING FOR {name_pattern} ---")
with engine.connect() as conn:
    res = conn.execute(text("""
        SELECT e.id, e.first_name, e.last_name, e.dni, e.status, e.organization_id, o.name as org_name
        FROM employees e
        JOIN organizations o ON e.organization_id = o.id
        WHERE e.first_name ILIKE :n OR e.last_name ILIKE :n OR e.dni = '********'
    """), {'n': name_pattern}).fetchall()
    
    if not res:
        print("NO EMPLOYEES FOUND")
    for r in res:
        print(f"EMP: {r.id} | {r.first_name} {r.last_name} | DNI: {r.dni} | Status: {r.status} | ORG: {r.org_name} ({r.organization_id})")
