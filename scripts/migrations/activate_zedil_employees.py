#!/usr/bin/env python3
"""
Activate ZEDIL S.A. employees and set passwords to their CUIL.

This script:
- Finds all pre-registered employees of ZEDIL S.A.
- Sets their status to 'active'
- Sets each user's password to their CUIL (bcrypt hashed)
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict

# Make project root importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from payroll_core import hash_password


def load_env() -> None:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def activate_employees(execute: bool = False) -> Dict[str, object]:
    load_env()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not configured")

    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Get organization ID
        org = conn.execute(
            text("select id, name from organizations where lower(name)=lower(:name)"),
            {"name": "ZEDIL S.A."},
        ).fetchone()
        
        if not org:
            raise RuntimeError("Organization ZEDIL S.A. not found")
        
        org_id = str(org.id)
        org_name = org.name
        
        # Find all pre-registered employees with their associated users
        employees = conn.execute(
            text("""
                select 
                    e.id, e.first_name, e.last_name, e.dni, e.cuil, e.status,
                    u.id as user_id, u.email
                from employees e
                left join users u on u.employee_id = e.id
                where e.organization_id = :org_id 
                  and e.is_deleted = false
                  and e.status = 'pre_registered'
                order by e.dni
            """),
            {"org_id": org_id},
        ).fetchall()
        
    summary = {
        "organization_id": org_id,
        "organization_name": org_name,
        "total_to_activate": len(employees),
        "activated": 0,
        "password_updated": 0,
        "errors": [],
    }
    
    rows = []
    
    for emp in employees:
        emp_id = str(emp.id)
        user_id = str(emp.user_id) if emp.user_id else None
        cuil = emp.cuil
        
        error = None
        action_status = "skipped"
        
        # Validate CUIL exists
        if not cuil:
            error = "CUIL faltante"
            action_status = "error"
        elif not emp.user_id:
            error = "Usuario no existe"
            action_status = "error"
        else:
            action_status = "ready"
        
        rows.append({
            "employee_id": emp_id,
            "user_id": user_id,
            "name": f"{emp.first_name} {emp.last_name or ''}".strip(),
            "dni": emp.dni,
            "cuil": cuil,
            "email": emp.email,
            "current_status": emp.status,
            "action": action_status,
            "error": error,
        })
        
        # Execute changes if requested
        if execute and not error:
            try:
                with engine.connect() as conn:
                    # 1. Update employee status to 'active'
                    conn.execute(
                        text("""
                            update employees 
                            set status = 'active', profile_completed = true
                            where id = :emp_id
                        """),
                        {"emp_id": emp_id},
                    )
                    
                    # 2. Update user password to CUIL (hashed)
                    password_hash = hash_password(cuil)
                    conn.execute(
                        text("""
                            update users
                            set password_hash = :pwd_hash, is_verified = true, user_status = 'active'
                            where id = :user_id
                        """),
                        {"pwd_hash": password_hash, "user_id": user_id},
                    )
                    
                    conn.commit()
                    
                    summary["activated"] += 1
                    summary["password_updated"] += 1
                    rows[-1]["action"] = "completed"
                    
            except Exception as exc:
                error_msg = str(exc)[:100]
                summary["errors"].append({"employee_id": emp_id, "error": error_msg})
                rows[-1]["action"] = "error"
                rows[-1]["error"] = error_msg
    
    return {
        "summary": summary,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Activate ZEDIL employees and set passwords to CUIL"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Activate employees and set passwords",
    )
    parser.add_argument(
        "--json-out",
        default="scripts/migrations/activate_zedil_employees.json",
    )
    args = parser.parse_args()

    result = activate_employees(execute=args.execute)
    
    output_path = ROOT / args.json_out
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    
    print(f"Wrote result to {output_path}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
