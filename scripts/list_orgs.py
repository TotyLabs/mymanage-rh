import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

print("--- ALL ORGANIZATIONS ---")
with engine.connect() as conn:
    orgs = conn.execute(text("SELECT id, name FROM organizations")).fetchall()
    if not orgs:
        print("NO ORGANIZATIONS FOUND")
    for o in orgs:
        print(f"ID: {o.id} | Name: {o.name}")
