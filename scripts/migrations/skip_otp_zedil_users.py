#!/usr/bin/env python3
"""
Skip OTP verification for ZEDIL S.A. users - set user_status to 'active'.

This changes user_status from 'pending_verification' to 'active' so they can
login without needing to enter an OTP code.
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


def skip_otp_verification(execute: bool = False) -> Dict[str, object]:
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
        
        # Find all users with pending_verification status
        users = conn.execute(
            text("""
                select id, email, user_status, is_verified
                from users
                where organization_id = :org_id 
                  and user_status = 'pending_verification'
                order by email
            """),
            {"org_id": org_id},
        ).fetchall()
    
    summary = {
        "organization_id": org_id,
        "organization_name": org_name,
        "total_to_activate": len(users),
        "activated": 0,
        "errors": [],
    }
    
    rows = []
    
    for user in users:
        user_id = str(user.id)
        
        rows.append({
            "user_id": user_id,
            "email": user.email,
            "current_status": user.user_status,
            "is_verified": user.is_verified,
            "action": "ready",
        })
        
        # Execute changes if requested
        if execute:
            try:
                with engine.connect() as conn:
                    conn.execute(
                        text("""
                            update users
                            set user_status = 'active', is_verified = true
                            where id = :user_id
                        """),
                        {"user_id": user_id},
                    )
                    conn.commit()
                    
                    summary["activated"] += 1
                    rows[-1]["action"] = "completed"
                    rows[-1]["new_status"] = "active"
                    
            except Exception as exc:
                error_msg = str(exc)[:100]
                summary["errors"].append({"user_id": user_id, "error": error_msg})
                rows[-1]["action"] = "error"
    
    return {
        "summary": summary,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Skip OTP verification for ZEDIL users - set user_status to active"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Skip OTP verification and activate users",
    )
    parser.add_argument(
        "--json-out",
        default="scripts/migrations/skip_otp_zedil_users.json",
    )
    args = parser.parse_args()

    result = skip_otp_verification(execute=args.execute)
    
    output_path = ROOT / args.json_out
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    
    print(f"Wrote result to {output_path}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
