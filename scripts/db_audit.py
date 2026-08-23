import os
import json
import traceback
from sqlalchemy import create_engine, text, inspect

def audit_database():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set.")
        return

    engine = create_engine(db_url)
    inspector = inspect(engine)

    tables_to_audit = ["organizations", "employees", "users", "payroll_receipts", "signature_events", "audit_log", "company_signers"]
    
    report = {
        "summary": {
            "invalid_null_strings": 0,
            "whitespace_issues": 0,
            "invalid_dni": 0,
            "invalid_cuil": 0,
            "duplicate_identities": 0
        },
        "details": []
    }

    invalid_null_patterns = ["'0'", "''", "'#N/A'", "'NULL'", "'00:00:00'"]
    patterns_str = ", ".join(invalid_null_patterns)
    
    with engine.connect() as conn:
        for table in tables_to_audit:
            try:
                cols = inspector.get_columns(table)
                col_names = [c["name"] for c in cols]
                text_cols = [c["name"] for c in cols if any(t in str(c["type"]).lower() for t in ["text", "varchar", "char"])]
                
                for col in text_cols:
                    # 1. Invalid Null Strings
                    q_null = text(f"SELECT COUNT(*) FROM {table} WHERE {col} IN ({patterns_str})")
                    count_null = conn.execute(q_null).scalar() or 0
                    
                    # 2. Whitespace
                    q_ws = text(f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND {col} != TRIM({col})")
                    count_ws = conn.execute(q_ws).scalar() or 0
                    
                    if count_null > 0 or count_ws > 0:
                        report["summary"]["invalid_null_strings"] += count_null
                        report["summary"]["whitespace_issues"] += count_ws
                        report["details"].append({
                            "table": table,
                            "field": col,
                            "type": "TEXT_ISSUE",
                            "invalid_nulls": count_null,
                            "whitespace": count_ws
                        })

                if table == "employees":
                    if "dni" in col_names:
                        q_dni = text("SELECT COUNT(*) FROM employees WHERE dni ~ '[^0-9]'")
                        dni_issues = conn.execute(q_dni).scalar() or 0
                        report["summary"]["invalid_dni"] = dni_issues
                        
                        q_dupe = text("SELECT COUNT(*) FROM (SELECT dni FROM employees WHERE dni IS NOT NULL AND dni != '' GROUP BY dni HAVING COUNT(*) > 1) as sub")
                        dupes = conn.execute(q_dupe).scalar() or 0
                        report["summary"]["duplicate_identities"] += dupes # Using identities sum

                    if "cuil" in col_names:
                        q_cuil = text("SELECT COUNT(*) FROM employees WHERE cuil IS NOT NULL AND cuil != '' AND LENGTH(regexp_replace(cuil, '[^0-9]', '', 'g')) != 11")
                        cuil_issues = conn.execute(q_cuil).scalar() or 0
                        report["summary"]["invalid_cuil"] = cuil_issues

            except Exception as e:
                # print(f"Error auditing table {table}: {e}")
                pass

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    audit_database()
