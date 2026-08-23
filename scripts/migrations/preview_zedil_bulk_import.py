#!/usr/bin/env python3
"""
Create user accounts for pre-registered ZEDIL S.A. employees.

The script:
- resolves the organization from the database by name,
- finds pre-registered employees without associated users,
- creates user accounts for them using data from the Excel file,
- uses the project's enums and bcrypt hashing for passwords,
- can run in preview mode or create real user accounts when --execute is passed.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
import uuid
import secrets
from pathlib import Path
from typing import Dict, Optional, Tuple

# Make project root importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from services.legajo.form_parser import FormParser
from models.tables import User
from models.enums import EmployeeStatus, UserStatus
from payroll_core import hash_password


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


def normalize_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_dni(value: Optional[str]) -> str:
    text = normalize_text(value)
    return re.sub(r"\D", "", text)


def normalize_legajo(value: Optional[str]) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalize_email(value: Optional[str]) -> str:
    return normalize_text(value).lower()


def normalize_status(value: Optional[str]) -> str:
    if hasattr(value, "value"):
        return value.value
    return str(value or "")


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


def resolve_organization(conn, org_name: str = "ZEDIL S.A.") -> Tuple[str, str]:
    rows = conn.execute(
        text("select id, name from organizations where lower(name)=lower(:name)"),
        {"name": org_name},
    ).fetchall()
    if not rows:
        raise RuntimeError(f"Organization not found: {org_name}")
    if len(rows) > 1:
        raise RuntimeError(f"Organization name is ambiguous: {org_name}")
    org = rows[0]
    return str(org.id), org.name


def build_existing_indexes(employees):
    by_dni = {}
    by_legajo = {}
    by_email = {}
    for emp in employees:
        dni = normalize_dni(getattr(emp, "dni", None))
        if dni:
            by_dni[dni] = emp
        legajo = normalize_legajo(getattr(emp, "file_number", None))
        if legajo:
            by_legajo[legajo] = emp
        email = normalize_email(getattr(emp, "email", None))
        if email:
            by_email[email] = emp
    return by_dni, by_legajo, by_email


def find_existing_employee(rec, by_dni, by_legajo, by_email):
    dni = normalize_dni(rec.get("dni"))
    legajo = normalize_legajo(rec.get("legajo") or rec.get("file_number"))
    email = normalize_email(rec.get("email"))

    if dni and dni in by_dni:
        return by_dni[dni], "dni"
    if legajo and legajo in by_legajo:
        return by_legajo[legajo], "legajo"
    if email and email in by_email:
        return by_email[email], "email"
    return None, "none"


def split_full_name(full_name: str) -> Tuple[str, str]:
    value = normalize_text(full_name)
    if not value:
        return "", ""
    if "," in value:
        last_name, first_name = value.split(",", 1)
        return normalize_text(first_name), normalize_text(last_name)
    return value, ""


def match_signature(signature_files, full_name: str):
    if not full_name:
        return "", "FIRMA_FALTANTE", "skip"

    normalized_name = normalize_name(full_name)
    if not normalized_name:
        return "", "FIRMA_FALTANTE", "skip"

    normalized_candidates = [p for p in signature_files if normalize_name(p.stem) == normalized_name]
    if len(normalized_candidates) == 1:
        return normalized_candidates[0].name, "FIRMA_MATCH_NORMALIZADO", "assign_signature"
    if len(normalized_candidates) > 1:
        return "", "FIRMA_AMBIGUA", "skip"
    return "", "FIRMA_FALTANTE", "skip"


def build_plan(execute: bool = False, auto_verify: bool = False) -> Dict[str, object]:
    load_env()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not configured")

    excel_path = ROOT / "fichaempleadozed123.xls"
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel not found: {excel_path}")

    rows = FormParser(mapping_version="3").parse(file_path=str(excel_path))

    engine = create_engine(db_url)
    SessionFactory = sessionmaker(bind=engine)

    with engine.connect() as conn:
        org_id, org_name = resolve_organization(conn, "ZEDIL S.A.")
        employees = conn.execute(
            text("""
                select id, first_name, last_name, dni, file_number, email, status, profile_completed, is_active, is_deleted
                from employees
                where organization_id = :org_id and is_deleted = false
                order by dni
            """),
            {"org_id": org_id},
        ).fetchall()
        users = conn.execute(
            text("""
                select id, email, employee_id, organization_id, user_status, is_verified, is_active
                from users
                where organization_id = :org_id
            """),
            {"org_id": org_id},
        ).fetchall()

    by_dni, by_legajo, by_email = build_existing_indexes(employees)
    users_by_employee = {str(r.employee_id): r for r in users if r.employee_id}

    signature_dir = ROOT / "storage" / "signatures" / "FIRMAS ZEDIL S.A." / "source"
    signature_files = []
    if signature_dir.exists():
        signature_files = [p for p in signature_dir.iterdir() if p.is_file()]

    preview_rows = []
    users_created = 0
    users_skipped = 0
    users_auto_verified = 0
    errors = []

    for excel_row, rec in enumerate(rows, start=1):
        dni = normalize_dni(rec.get("dni"))
        email = normalize_email(rec.get("email"))
        full_name = normalize_text(rec.get("full_name"))
        legajo = normalize_legajo(rec.get("legajo") or rec.get("file_number"))
        phone = normalize_text(rec.get("phone"))
        first_name, last_name = split_full_name(full_name)
        if not first_name and rec.get("first_name"):
            first_name = normalize_text(rec.get("first_name"))
        if not last_name and rec.get("last_name"):
            last_name = normalize_text(rec.get("last_name"))

        employee, match_key = find_existing_employee(rec, by_dni, by_legajo, by_email)
        user = users_by_employee.get(str(employee.id)) if employee else None

        warnings = []
        blocking = []

        if not dni:
            blocking.append("DNI faltante")
        if not full_name:
            blocking.append("Nombre faltante")
        if not email:
            warnings.append("Email faltante")
        elif "@" not in email:
            warnings.append("Email inválido")

        if not employee:
            blocking.append("Empleado no encontrado (no preregistrado)")
        elif normalize_status(getattr(employee, "status", None)) != EmployeeStatus.pre_registered.value:
            warnings.append(f"estado_empleado={normalize_status(getattr(employee, 'status', None))}")

        signature_filename, signature_match_status, planned_signature_action = match_signature(signature_files, full_name)
        if signature_match_status == "FIRMA_FALTANTE":
            warnings.append("firma_faltante")
        if signature_match_status == "FIRMA_AMBIGUA":
            warnings.append("firma_ambigua")

        # Decidir acciones según el estado actual
        if employee and user:
            planned_user_action = "existing_noop"
            action_description = "Usuario ya existe"
            user_status_after = "existing"
        elif employee and not user:
            planned_user_action = "create_user"
            action_description = "Crear usuario de acceso"
            user_status_after = "pending_verification"
        else:
            planned_user_action = "cannot_create"
            action_description = "No se puede crear usuario sin empleado preregistrado"
            user_status_after = "blocked"

        # Ejecutar creación de usuario si es necesario
        if execute and employee and not user and not blocking:
            try:
                temp_password = secrets.token_urlsafe(16)
                password_hash = hash_password(temp_password)
                
                with SessionFactory() as session:
                    user_obj = User(
                        id=str(uuid.uuid4()),
                        email=email or f"{dni}@sin-correo.local",
                        password_hash=password_hash,
                        full_name=full_name,
                        role="employee",
                        organization_id=org_id,
                        employee_id=str(employee.id),
                        user_status=UserStatus.active.value if auto_verify else UserStatus.pending_verification.value,
                        is_verified=auto_verify,
                        is_active=True,
                    )
                    session.add(user_obj)
                    session.commit()
                    users_created += 1
                    if auto_verify:
                        users_auto_verified += 1
                    users_by_employee[str(employee.id)] = user_obj
                    user = user_obj
                    action_description = f"Usuario creado (contraseña: {temp_password[:8]}...)"
            except IntegrityError as exc:
                errors.append({"excel_row": excel_row, "error": f"IntegrityError: {str(exc)[:100]}", "dni": dni, "email": email})
                planned_user_action = "error"
                action_description = f"Error de integridad: email duplicado o usuario existente"
                continue
            except Exception as exc:
                errors.append({"excel_row": excel_row, "error": str(exc)[:100], "dni": dni})
                planned_user_action = "error"
                action_description = f"Error: {str(exc)[:50]}"
                continue
        elif employee and not user:
            users_skipped += 1

        preview_rows.append(
            {
                "excel_row": excel_row,
                "dni": dni,
                "legajo": legajo,
                "nombre_completo": full_name,
                "email": email,
                "phone": phone,
                "organization_id": org_id,
                "organization_name": org_name,
                "employee_exists": bool(employee),
                "user_exists": bool(user),
                "match_strategy": match_key,
                "preregistration_status": normalize_status(getattr(employee, "status", None)) if employee else "no_existe",
                "planned_user_action": planned_user_action,
                "action_description": action_description,
                "signature_filename": signature_filename,
                "signature_match_status": signature_match_status,
                "planned_signature_action": planned_signature_action,
                "warnings": "; ".join(warnings),
                "blocking_errors": "; ".join(blocking),
            }
        )

    matched_signature_names = {normalize_name(r["nombre_completo"]) for r in preview_rows if r["signature_match_status"] in {"FIRMA_MATCH_NORMALIZADO", "FIRMA_MATCH_EXACTO"}}
    orphan_signature_count = sum(1 for p in signature_files if normalize_name(p.stem) not in matched_signature_names)

    summary = {
        "total_excel": len(preview_rows),
        "aptos_para_crear_usuario": len([r for r in preview_rows if not r["blocking_errors"]]),
        "bloqueados": len([r for r in preview_rows if r["blocking_errors"]]),
        "usuarios_a_crear": len([r for r in preview_rows if r["planned_user_action"] == "create_user"]),
        "usuarios_creados": users_created,
        "usuarios_auto_verificados": users_auto_verified,
        "usuarios_existentes": len([r for r in preview_rows if r["planned_user_action"] == "existing_noop"]),
        "usuarios_omitidos_preview": users_skipped,
        "firmas_a_asignar": len([r for r in preview_rows if r["planned_signature_action"] == "assign_signature"]),
        "firmas_faltantes": len([r for r in preview_rows if r["signature_match_status"] == "FIRMA_FALTANTE"]),
        "firmas_ambiguas": len([r for r in preview_rows if r["signature_match_status"] == "FIRMA_AMBIGUA"]),
        "firmas_huerfanas": orphan_signature_count,
        "cambios_ejecutados": users_created,
        "errores": len(errors),
    }
    
    if errors:
        summary["error_details"] = errors

    return {"summary": summary, "rows": preview_rows, "organization_id": org_id, "organization_name": org_name}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create user accounts for pre-registered ZEDIL S.A. employees")
    parser.add_argument("--execute", action="store_true", help="Create user accounts for employees without users")
    parser.add_argument("--auto-verify", action="store_true", help="Create users as auto-verified active accounts")
    parser.add_argument("--json-out", default="scripts/migrations/preview_zedil_bulk_import.json")
    args = parser.parse_args()

    preview = build_plan(execute=args.execute, auto_verify=args.auto_verify)
    output_path = ROOT / args.json_out
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(preview, ensure_ascii=False, indent=2))
    print(f"Wrote preview JSON to {output_path}")
    print(json.dumps(preview["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
