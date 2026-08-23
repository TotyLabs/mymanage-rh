import os
import json
from sqlalchemy import create_engine, text, inspect

def run_db_fix():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set.")
        return

    engine = create_engine(db_url)
    ins = inspect(engine)
    
    # 1. Backups
    print("--- Creating Backups ---")
    tables_to_backup = ["employees", "users", "organizations"]
    existing_tables = ins.get_table_names()
    with engine.connect() as conn:
        for t in tables_to_backup:
            if t not in existing_tables:
                continue
            backup_name = f"{t}_backup_20260322"
            try:
                conn.execute(text(f'DROP TABLE IF EXISTS "{backup_name}"'))
                conn.execute(text(f'CREATE TABLE "{backup_name}" AS SELECT * FROM "{t}"'))
                print(f"Backup created: {backup_name}")
            except Exception as e:
                print(f"Error backing up {t}: {e}")
        conn.commit()

    # 2. Whitelists & Fixes
    invalid_null_whitelist = {
        "organizations": ["alias", "logo_path"],
        "employees": ["address", "phone", "marital_status", "status_reason"],
        "users": ["key_management_mode"]
    }
    trim_whitelist = {
        "employees": ["dni", "cuil", "address", "phone"],
        "users": ["full_name", "email"],
        "organizations": ["name", "alias"]
    }
    
    patterns = ("0", "", "#N/A", "NULL", "00:00:00")
    
    print("\n--- Applying Fixes ---")
    with engine.connect() as conn:
        # A. Invalid Nulls (Dynamic Whitelist)
        for t, cols in invalid_null_whitelist.items():
            if t not in existing_tables: continue
            existing_cols = [c["name"] for c in ins.get_columns(t)]
            for col in cols:
                if col not in existing_cols:
                    print(f"Skipping Null Fix: {t}.{col} (column missing)")
                    continue
                q = text(f'UPDATE "{t}" SET "{col}" = NULL WHERE "{col}" IN :p')
                res = conn.execute(q, {"p": patterns})
                if res.rowcount > 0:
                    print(f"Fix Nulls: {t}.{col} -> {res.rowcount} rows affected")

        # B. Trim (Dynamic Whitelist)
        for t, cols in trim_whitelist.items():
            if t not in existing_tables: continue
            existing_cols = [c["name"] for c in ins.get_columns(t)]
            for col in cols:
                if col not in existing_cols:
                    # print(f"Skipping Trim: {t}.{col} (column missing)")
                    continue
                q = text(f'UPDATE "{t}" SET "{col}" = TRIM("{col}") WHERE "{col}" != TRIM("{col}")')
                res = conn.execute(q)
                if res.rowcount > 0:
                    print(f"Fix Trim: {t}.{col} -> {res.rowcount} rows affected")

        # C. Casing (Dynamic Check)
        if "users" in existing_tables:
            existing_cols_u = [c["name"] for c in ins.get_columns("users")]
            if "full_name" in existing_cols_u:
                q_u = text('UPDATE "users" SET "full_name" = INITCAP("full_name")')
                res_u = conn.execute(q_u)
                print(f"Fix Casing: users.full_name -> {res_u.rowcount} rows affected")
        
        if "organizations" in existing_tables:
            existing_cols_o = [c["name"] for c in ins.get_columns("organizations")]
            if "name" in existing_cols_o:
                q_o = text('UPDATE "organizations" SET "name" = INITCAP("name")')
                res_o = conn.execute(q_o)
                print(f"Fix Casing: organizations.name -> {res_o.rowcount} rows affected")

        # D. Identity Cleaning (Strict Validation)
        if "employees" in existing_tables:
            existing_cols_e = [c["name"] for c in ins.get_columns("employees")]
            if "dni" in existing_cols_e:
                q_dni = text("""
                    UPDATE "employees" 
                    SET "dni" = regexp_replace("dni", '[^0-9]', '', 'g') 
                    WHERE "dni" ~ '[^0-9]' 
                      AND length(regexp_replace("dni", '[^0-9]', '', 'g')) BETWEEN 7 AND 9
                """)
                res_dni = conn.execute(q_dni)
                print(f"Fix DNI: employees.dni (cleaned & validated) -> {res_dni.rowcount} rows affected")

            if "cuil" in existing_cols_e:
                q_cuil = text("""
                    UPDATE "employees" 
                    SET "cuil" = regexp_replace("cuil", '[^0-9]', '', 'g') 
                    WHERE "cuil" IS NOT NULL AND "cuil" != '' 
                      AND length(regexp_replace("cuil", '[^0-9]', '', 'g')) = 11
                """)
                res_cuil = conn.execute(q_cuil)
                print(f"Fix CUIL: employees.cuil (cleaned & validated) -> {res_cuil.rowcount} rows affected")

        conn.commit()

    # 3. Post-Check Validation
    print("\n--- Post-Check Validation ---")
    with engine.connect() as conn:
        if "employees" in existing_tables:
            q_bad_dni = text("SELECT COUNT(*) FROM employees WHERE dni IS NULL OR length(dni) NOT BETWEEN 7 AND 9")
            bad_dni = conn.execute(q_bad_dni).scalar()
            print(f"Validation: Invalid/Missing DNI count -> {bad_dni}")

            q_bad_cuil = text("SELECT COUNT(*) FROM employees WHERE cuil IS NOT NULL AND cuil != '' AND length(cuil) != 11")
            bad_cuil = conn.execute(q_bad_cuil).scalar()
            print(f"Validation: Invalid CUIL count -> {bad_cuil}")

        if "users" in existing_tables:
            q_bad_email = text("SELECT COUNT(*) FROM users WHERE email NOT LIKE '%@%'")
            bad_email = conn.execute(q_bad_email).scalar()
            print(f"Validation: Invalid Emails in users -> {bad_email}")

if __name__ == "__main__":
    run_db_fix()
