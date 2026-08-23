import os
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

print("--- INSPECTING DATABASE ---")
inspector = inspect(engine)
tables = inspector.get_table_names()
print(f"TABLES found: {tables}")

for t in tables:
    if 'audit' in t.lower() or 'log' in t.lower():
        print(f"\n--- COLUMNS IN {t} ---")
        columns = inspector.get_columns(t)
        for c in columns:
            print(f"  COL: {c['name']} (Type: {c['type']})")
