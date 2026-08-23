import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

print("--- FINAL ORG LOOKUP ---")
with engine.connect() as conn:
    res = conn.execute(text("""
        SELECT o.name 
        FROM employees e 
        JOIN organizations o ON e.organization_id = o.id 
        WHERE e.first_name ILIKE '%CANDIDO%' OR e.last_name ILIKE '%CANDIDO%' 
        LIMIT 1
    """)).fetchone()
    
    if res:
        print(f"FOUND_ORG_NAME: {res.name}")
    else:
        print("RESULT: NOT_FOUND (Employee might not be pre-registered yet)")
