import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv('DATABASE_URL')
engine = create_engine(db_url)

name_pattern = '%CANDIDO%'

print(f"--- DELETING RECORDS FOR {name_pattern} ---")
with engine.connect() as conn:
    # 1. Find the employee(s)
    res = conn.execute(text("""
        SELECT id, organization_id, dni FROM employees 
        WHERE first_name ILIKE :n OR last_name ILIKE :n
    """), {'n': name_pattern}).fetchall()
    
    if not res:
        print("NO EMPLOYEES FOUND TO DELETE")
    else:
        for r in res:
            emp_id = r.id
            print(f"Purging Employee: {emp_id} (DNI: {r.dni})")
            
            # Delete associated users first due to foreign keys (if CASCADE not used or for safety)
            conn.execute(text("DELETE FROM users WHERE employee_id = :eid"), {"eid": emp_id})
            # Delete employee signature requests/receipts mapping if necessary, 
            # but table has cascade on organization_id, check for employee_id
            conn.execute(text("DELETE FROM signature_requests WHERE employee_id = :eid"), {"eid": emp_id})
            
            # Finally delete the employee
            conn.execute(text("DELETE FROM employees WHERE id = :eid"), {"eid": emp_id})
            print(f"Successfully deleted {emp_id}")
            
    conn.commit()
print("--- CLEANUP COMPLETE ---")
