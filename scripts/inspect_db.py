import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))
with engine.connect() as conn:
    print("----- TABLES -----")
    for row in conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")):
        print(row[0])
