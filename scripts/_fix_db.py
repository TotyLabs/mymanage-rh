import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from payroll_core import SessionLocal

def fix_db():
    db = SessionLocal()
    try:
        # 1. Create enum if not exists
        db.execute(text("DO $$ BEGIN CREATE TYPE employee_status AS ENUM ('pre_registered', 'active', 'inactive'); EXCEPTION WHEN duplicate_object THEN null; END $$;"))
        db.commit()

        # 2. Add columns
        columns = [
            ("dni", "TEXT"),
            ("cuil", "TEXT"),
            ("email", "TEXT"),
            ("status", "employee_status NOT NULL DEFAULT 'pre_registered'"),
            ("profile_completed", "BOOLEAN NOT NULL DEFAULT false"),
            ("is_active", "BOOLEAN NOT NULL DEFAULT true"),
            ("marital_status", "TEXT"),
            ("birth_date", "DATE"),
            ("address", "TEXT"),
            ("phone", "TEXT"),
            ("position", "TEXT"),
            ("hire_date", "DATE"),
        ]

        for col, col_type in columns:
            res = db.execute(text(f"""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='employees' and column_name='{col}';
            """)).fetchone()

            if not res:
                print(f"Adding '{col}' column to employees...")
                db.execute(text(f"ALTER TABLE employees ADD COLUMN {col} {col_type};"))
                db.commit()
                print(f"Successfully added '{col}' column.")
            else:
                print(f"'{col}' column already exists.")

        db.execute(text("UPDATE employees SET dni = '11111111' WHERE dni IS NULL;"))
        db.execute(text("ALTER TABLE employees ALTER COLUMN dni SET NOT NULL;"))
        db.commit()

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_db()
