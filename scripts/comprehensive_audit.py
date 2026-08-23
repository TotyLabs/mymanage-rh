import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

print("--- COMPREHENSIVE EMPLOYEE AUDIT ---")
with engine.connect() as conn:
    res = conn.execute(text("""
        SELECT e.first_name, e.last_name, e.dni, e.status, o.name as org_name
        FROM employees e
        JOIN organizations o ON e.organization_id = o.id
    """)).fetchall()
    
    if not res:
        print("NO EMPLOYEES FOUND IN DATABASE AT ALL")
    for r in res:
        print(f"EMP: {r.first_name} {r.last_name} | DNI: {r.dni} | Status: {r.status} | ORG: {r.org_name}")
