import os
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://postgres:RAABFC2026@localhost:5432/payroll_db"
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    org_id = conn.execute(text("SELECT id FROM organizations LIMIT 1")).scalar()
    emps = conn.execute(text("SELECT full_name, dni, cuil FROM employees")).fetchall()
    
    with open("results.txt", "w", encoding="utf-8") as f:
        f.write(f"Organization ID: {org_id}\n")
        f.write("Employees:\n")
        for e in emps:
            f.write(f"- {e[0]} | DNI: {e[1]} | CUIL: {e[2]}\n")
