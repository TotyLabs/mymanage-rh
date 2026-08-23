import os
from sqlalchemy import create_engine, text

def run_align_and_dedupe():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set.")
        return

    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        print("--- Deduplicating Identities ---")
        # Keep the record with the smaller ID (lexicographical or creation order)
        # We'll use a subquery to find duplicates and keep the first one
        dedupe_query = text("""
            DELETE FROM employees
            WHERE id IN (
                SELECT id
                FROM (
                    SELECT id,
                           row_number() OVER (PARTITION BY dni ORDER BY created_at ASC, id ASC) as row_num
                    FROM employees
                    WHERE dni IN ('94745854', '94823995')
                ) t
                WHERE t.row_num > 1
            )
        """)
        res_dedupe = conn.execute(dedupe_query)
        print(f"Deduplication: {res_dedupe.rowcount} rows deleted.")

        print("\n--- Aligning Schema (Adding Columns) ---")
        columns_to_add = [
            ("first_name", "TEXT"),
            ("last_name", "TEXT"),
            ("file_number", "TEXT"),
            ("document_type", "TEXT DEFAULT 'DNI'"),
            ("document_number", "TEXT"),
            ("phone", "TEXT"),
            ("address", "TEXT")
        ]
        
        for col, col_type in columns_to_add:
            try:
                # Check column existence first to avoid errors if already present
                check_q = text(f"SELECT COUNT(*) FROM information_schema.columns WHERE table_name='employees' AND column_name='{col}'")
                exists = conn.execute(check_q).scalar()
                if not exists:
                    conn.execute(text(f'ALTER TABLE employees ADD COLUMN "{col}" {col_type}'))
                    print(f"Added column: employees.{col}")
                else:
                    print(f"Column already exists: employees.{col}")
            except Exception as e:
                print(f"Error adding column {col}: {e}")

        conn.commit()

if __name__ == "__main__":
    run_align_and_dedupe()
