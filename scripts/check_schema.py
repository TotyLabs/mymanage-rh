
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

with engine.connect() as conn:
    print("----- Checking Schema for Organizations -----")
    res = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'organizations'"))
    for r in res:
        print(r)
        
    print("\n----- Checking Schema for Employees -----")
    res = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'employees'"))
    for r in res:
        print(r)
