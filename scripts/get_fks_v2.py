import os
from sqlalchemy import create_engine, text

def get_fks():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set.")
        return

    engine = create_engine(db_url)
    with engine.connect() as conn:
        # Query pg_constraint for all tables referring to employees
        q = text("""
            SELECT
                conname AS constraint_name,
                conrelid::regclass AS table_name,
                a.attname AS column_name
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
            WHERE c.confrelid = 'employees'::regclass;
        """)
        res = conn.execute(q).fetchall()
        for r in res:
            print(f"Table: {r[1]}, Column: {r[2]} -> employees.id (Constraint: {r[0]})")

if __name__ == "__main__":
    get_fks()
