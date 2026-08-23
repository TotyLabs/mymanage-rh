#!/usr/bin/env python3
"""
Assign signatures to ZEDIL S.A. users based on normalized name matching.

This script:
- Reads signature files from storage/signatures/FIRMAS ZEDIL S.A./source
- Matches them to users by normalized name (conservatively)
- Creates user_signatures records with the correct storage paths
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, Optional

# Make project root importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
import uuid


def normalize_name(value: Optional[str]) -> str:
    if not value:
        return ""
    s = str(value).strip().upper()
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    s = s.replace("FIRMA", "")
    for ext in [".JPG", ".JPEG", ".PNG", ".PDF", ".jpg", ".jpeg", ".png", ".pdf"]:
        s = s.replace(ext, "")
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


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


def assign_signatures(execute: bool = False) -> Dict[str, object]:
    load_env()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not configured")

    engine = create_engine(db_url)
    
    # Load signature files
    base_signature_dir = ROOT / "storage" / "signatures" / "FIRMAS ZEDIL S.A."
    signature_dir = base_signature_dir / "source"
    if not signature_dir.exists():
        signature_dir = base_signature_dir
    if not signature_dir.exists():
        raise FileNotFoundError(f"Signature directory not found: {signature_dir}")
    
    signature_files = [p for p in signature_dir.iterdir() if p.is_file()]
    signature_map = {normalize_name(p.stem): p for p in signature_files}
    
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
        
        # Find all users of ZEDIL with their employee info
        users = conn.execute(
            text("""
                select 
                    u.id as user_id,
                    u.email,
                    u.full_name,
                    e.first_name,
                    e.last_name
                from users u
                join employees e on e.id = u.employee_id
                where u.organization_id = :org_id
                order by u.email
            """),
            {"org_id": org_id},
        ).fetchall()
    
    summary = {
        "organization_id": org_id,
        "organization_name": org_name,
        "total_signature_files": len(signature_files),
        "total_users": len(users),
        "signatures_assigned": 0,
        "signatures_matched": 0,
        "errors": [],
    }
    
    rows = []
    assigned_signatures = set()
    
    for user in users:
        user_id = str(user.user_id)
        full_name = user.full_name or f"{user.first_name} {user.last_name or ''}".strip()
        normalized_name = normalize_name(full_name)
        
        signature_file = signature_map.get(normalized_name)
        
        if signature_file:
            summary["signatures_matched"] += 1
            assigned_signatures.add(normalized_name)
            
            # Build relative path for storage
            signature_path = f"signatures/FIRMAS ZEDIL S.A./source/{signature_file.name}"
            
            rows.append({
                "user_id": user_id,
                "email": user.email,
                "full_name": full_name,
                "signature_filename": signature_file.name,
                "signature_path": signature_path,
                "action": "ready",
            })
            
            # Execute assignment if requested
            if execute:
                try:
                    with engine.connect() as conn:
                        # Check if signature already exists
                        existing = conn.execute(
                            text("""
                                select id from user_signatures 
                                where user_id = :user_id
                            """),
                            {"user_id": user_id},
                        ).fetchone()
                        
                        if not existing:
                            # Create new signature record
                            sig_id = str(uuid.uuid4())
                            conn.execute(
                                text("""
                                    insert into user_signatures (id, user_id, signature_path, is_active)
                                    values (:id, :user_id, :path, true)
                                """),
                                {
                                    "id": sig_id,
                                    "user_id": user_id,
                                    "path": signature_path,
                                },
                            )
                            conn.commit()
                            summary["signatures_assigned"] += 1
                            rows[-1]["action"] = "completed"
                        else:
                            rows[-1]["action"] = "already_exists"
                        
                except Exception as exc:
                    error_msg = str(exc)[:100]
                    summary["errors"].append({"user_id": user_id, "error": error_msg})
                    rows[-1]["action"] = "error"
        else:
            rows.append({
                "user_id": user_id,
                "email": user.email,
                "full_name": full_name,
                "signature_filename": None,
                "signature_path": None,
                "action": "no_match",
            })
    
    # Count orphan signatures (firmas que no se asignaron a nadie)
    orphan_signatures = [p.name for p in signature_files if normalize_name(p.stem) not in assigned_signatures]
    summary["orphan_signatures"] = len(orphan_signatures)
    summary["orphan_signature_files"] = orphan_signatures[:10]  # Show first 10
    
    return {
        "summary": summary,
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign signature files to ZEDIL S.A. users"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Create user_signatures records",
    )
    parser.add_argument(
        "--json-out",
        default="scripts/migrations/assign_signatures_zedil.json",
    )
    args = parser.parse_args()

    result = assign_signatures(execute=args.execute)
    
    output_path = ROOT / args.json_out
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    
    print(f"Wrote result to {output_path}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
