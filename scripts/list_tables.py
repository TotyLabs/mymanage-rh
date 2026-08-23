import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:RAABFC2026@localhost:5432/payroll_db")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    res = conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname != 'pg_catalog' AND schemaname != 'information_schema'"))
    tables = [r[0] for r in res]
    print(tables)
