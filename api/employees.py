"""
Employees API - Refactored v5.1
Identidad centralizada por DNI y vinculaciÃƒÂ³n automÃƒÂ¡tica de recibos.

GAP-009: DNI change in PATCH triggers re-match of orphan receipts + blocks if signed exist.
GAP-010: delete_employee / bulk_delete_employees guard against signed receipts.
GAP-019: upsert_employee does NOT downgrade 'active' employees to 'pre_registered'.
"""

import json
import re
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Form, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import secrets
import os
import shutil
from pathlib import Path
from fastapi import File, UploadFile
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
import config

from payroll_core import (
    get_db,
    require_auth,
    require_admin,
    audit,
    safe_transaction,
    file_transaction,
    write_upload_to_disk,
    logger,
    normalize_dni,
    normalize_cuil,
    limiter,
    user_ip_key,
    utc_now,
    validate_email_format,
    sanitize_text_input,
    create_signature_request,
    resolve_storage_path,
)
from services.family_members import normalize_family_members_payload
from services.legajo.ingestion import IngestionService, IngestionMode
from services.legajo.banks import list_banks, get_bank_by_code
from services.encryption_service import (
    EncryptionService,
    KmsError,
    get_encryption_service,
    record_kms_error_event,
)

router = APIRouter(prefix="/api", tags=["employees"])


def persist_family_members(db: Session, employee_id: str, raw_value, org_id: Optional[str] = None) -> list[dict]:
    members = normalize_family_members_payload(raw_value)
    payload = json.dumps({"family_members": members})
    db.execute(
        text("""
            UPDATE employees
            SET extra_fields = COALESCE(extra_fields, '{}'::jsonb) || CAST(:payload AS jsonb)
            WHERE id = :id
              AND (:org_id IS NULL OR organization_id = CAST(:org_id AS UUID))
        """),
        {"payload": payload, "id": employee_id, "org_id": org_id},
    )
    return members


def persist_clothing_delivery(db: Session, employee_id: str, payload, org_id: Optional[str] = None) -> None:
    fields = {
        "desde": "ropa_desde",
        "hasta": "ropa_hasta",
        "vencimiento": "ropa_vencimiento",
        "proximo_vencimiento": "ropa_proximo_vencimiento",
    }
    if not any(key in payload for key in fields.values()):
        return

    values = {
        name: sanitize_text_input(str(payload.get(key, "") or ""))
        for name, key in fields.items()
    }
    db.execute(
        text("""
            UPDATE employees
            SET extra_fields = COALESCE(extra_fields, '{}'::jsonb) || CAST(:payload AS jsonb)
            WHERE id = :id
              AND (:org_id IS NULL OR organization_id = CAST(:org_id AS UUID))
        """),
        {"payload": json.dumps({"ropa_trabajo": values}), "id": employee_id, "org_id": org_id},
    )


def persist_template_fields(db: Session, employee_id: str, raw_value, org_id: Optional[str] = None) -> None:
    if not raw_value:
        return
    try:
        values = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except (TypeError, ValueError):
        raise HTTPException(400, "datos_nuevo_legajo_invalidos")
    if not isinstance(values, dict):
        raise HTTPException(400, "datos_nuevo_legajo_invalidos")

    allowed = {
        "document_expediente", "health_insurance_code", "retirement_plan", "afjp",
        "section_address", "section_locality", "ieric_delivery_status", "booklet_number",
        "booklet_rubric_date", "union_voluntary", "family_residence", "studies_completed",
        "work_history", "family_data", "shirt_size", "pants_size", "shoe_size",
    }
    clean_values = {
        key: sanitize_text_input(str(value or ""))
        for key, value in values.items()
        if key in allowed
    }
    db.execute(
        text("""
            UPDATE employees
            SET extra_fields = COALESCE(extra_fields, '{}'::jsonb) || CAST(:payload AS jsonb)
            WHERE id = :id
              AND (:org_id IS NULL OR organization_id = CAST(:org_id AS UUID))
        """),
        {"payload": json.dumps({"nuevo_legajo": clean_values}), "id": employee_id, "org_id": org_id},
    )


def _encryption_metadata_exists(db: Session, file_path: str | Path, organization_id: str) -> bool:
    try:
        storage_key = EncryptionService.storage_key(file_path)
        row = db.execute(
            text("""
                SELECT 1
                FROM file_encryption_metadata
                WHERE organization_id = CAST(:org AS UUID)
                  AND storage_path = :storage_path
                LIMIT 1
            """),
            {"org": organization_id, "storage_path": storage_key},
        ).fetchone()
        return bool(row)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return False


def _encrypt_dni_file_or_fail(
    db: Session,
    file_path: str | Path,
    *,
    organization_id: str,
    actor_id: str,
    employee_id: str,
    side: str,
) -> Optional[dict]:
    if not config.APP_ENCRYPTION_ENABLED:
        return None

    import uuid

    file_id = str(uuid.uuid4())
    purpose = f"identity_snapshot:dni_{side}"
    try:
        return get_encryption_service().encrypt_file_in_place(
            file_path,
            organization_id=str(organization_id),
            purpose=purpose,
            file_id=file_id,
        )
    except KmsError as exc:
        try:
            record_kms_error_event(
                db,
                organization_id=str(organization_id),
                actor_id=str(actor_id),
                actor_type="admin",
                file_id=file_id,
                purpose=purpose,
                error_code=str(exc),
            )
        except Exception:
            logger.exception("dni.encryption_kms_error_audit_failed")
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            logger.exception("dni.plaintext_cleanup_failed_after_kms_error")
        raise HTTPException(503, "kms_unavailable_encryption_failed") from exc

# Validaciones estrictas
DNI_REGEX = re.compile(r"^\d{7,9}$")
CUIL_REGEX = re.compile(r"^\d{11}$")
CBU_REGEX = re.compile(r"^\d{22}$")

# =====================================================
# BANKS MASTER
# =====================================================

@router.get("/banks")
async def get_banks():
    """Returns the master bank list for the UI dropdown."""
    return {"banks": list_banks()}

# =====================================================
# HELPERS
# =====================================================




def calculate_seniority(hire_date) -> str:
    """Calcula la antigÃƒÂ¼edad en aÃƒÂ±os y meses."""
    if not hire_date:
        return "n/a"
    from datetime import date
    today = date.today()
    years = today.year - hire_date.year
    months = today.month - hire_date.month
    if months < 0:
        years -= 1
        months += 12
    parts = []
    if years > 0:
        parts.append(f"{years} {'aÃƒÂ±o' if years == 1 else 'aÃƒÂ±os'}")
    if months > 0:
        parts.append(f"{months} {'mes' if months == 1 else 'meses'}")
    if not parts:
        return "ReciÃƒÂ©n ingresado"
    return ", ".join(parts)


def _has_signed_receipts(db: Session, employee_id: str) -> int:
    """Returns count of signed receipts with legal evidence for this employee."""
    row = db.execute(text("""
        SELECT COUNT(*) AS cnt
        FROM payroll_receipts pr
        JOIN signature_evidence se ON se.receipt_id = pr.id
        WHERE pr.employee_id = :eid
    """), {"eid": employee_id}).fetchone()
    return row.cnt if row else 0


# =====================================================
# ENDPOINTS
# =====================================================

@router.get("/employees")
async def get_employees(
    limit: Optional[int] = None,
    all: bool = False,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Lista todos los empleados de la organizaciÃƒÂ³n con contadores de recibos y cuenta."""
    org_id = user["organization_id"]

    # GAP-014 Fix: Defensive LIMIT to prevent OOM
    MAX_LIMIT = 2000
    safe_limit = min(limit or MAX_LIMIT, MAX_LIMIT)
    
    # If all=true, we don't filter by is_deleted
    deleted_filter = "" if all else "AND e.is_deleted = false"

    rows = db.execute(
        text(f"""
            SELECT
                e.id, e.first_name, e.last_name, e.file_number, e.dni, e.cuil, e.email, e.status,
                e.profile_completed, e.created_at, e.dni_image_path, e.is_deleted,
                (SELECT id FROM users u WHERE u.employee_id = e.id LIMIT 1) AS user_id,
                (SELECT COUNT(*) FROM payroll_receipts pr WHERE pr.employee_id = e.id AND pr.is_deleted = false) AS receipts_count
            FROM employees e
            WHERE e.organization_id = :org {deleted_filter}
            ORDER BY e.created_at DESC
            LIMIT :limit
        """),
        {"org": org_id, "limit": safe_limit},
    ).fetchall()

    return {
        "employees": [
            {
                "id": str(r.id),
                "first_name": r.first_name,
                "last_name": r.last_name,
                "full_name": f"{r.first_name} {r.last_name or ''}".strip(),
                "file_number": r.file_number,
                "dni": r.dni,
                "cuil": r.cuil,
                "email": r.email,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "profile_completed": r.profile_completed,
                "has_account": bool(r.user_id),
                "user_id": str(r.user_id) if r.user_id else None,
                "receipts_count": r.receipts_count,
                "dni_image_uploaded": bool(r.dni_image_path),
                "is_deleted": r.is_deleted,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
    }

@router.get("/employees/pending-verification/list")
async def get_pending_verification_employees(
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Lista empleados pendientes de verificaciÃƒÂ³n.
    Estos son empleados creados automÃƒÂ¡ticamente desde DNIs de recibos,
    esperando validaciÃƒÂ³n del usuario.
    """
    org_id = user["organization_id"]

    rows = db.execute(
        text("""
            SELECT
                e.id, e.first_name, e.last_name, e.dni, e.status_reason, e.created_at,
                COUNT(pr.id) as receipts_count
            FROM employees e
            LEFT JOIN payroll_receipts pr ON pr.employee_id = e.id AND pr.is_deleted = false
            WHERE e.organization_id = :org AND e.status = 'pending_verification' AND e.is_deleted = false
            GROUP BY e.id, e.first_name, e.last_name, e.dni, e.status_reason, e.created_at
            ORDER BY e.created_at DESC
        """),
        {"org": org_id},
    ).fetchall()

    return {
        "total": len(rows),
        "pending_employees": [
            {
                "id": str(r.id),
                "first_name": r.first_name,
                "last_name": r.last_name,
                "dni": r.dni,
                "reason": r.status_reason,
                "receipts_count": r.receipts_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "actions": [
                    "complete_profile",
                    "confirm_and_activate",
                    "delete"
                ]
            }
            for r in rows
        ]
    }

@router.post("/employees/{employee_id}/verify-and-activate")
async def verify_and_activate_employee(
    employee_id: str,
    first_name: str = Form(...),
    last_name: str = Form(None),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Valida y activa un empleado que estaba en pending_verification.
    Mueve el estado a 'active'.
    """
    org_id = user["organization_id"]

    # Verify ownership
    emp = db.execute(
        text("SELECT id, status FROM employees WHERE id = :id AND organization_id = :org AND is_deleted = false"),
        {"id": employee_id, "org": org_id}
    ).fetchone()

    if not emp:
        raise HTTPException(404, "employee_not_found")

    if emp.status != "pending_verification":
        raise HTTPException(400, f"employee_not_pending_verification_status_is_{emp.status}")

    clean_first = sanitize_text_input(first_name) if first_name else None
    clean_last = sanitize_text_input(last_name) if last_name else None

    if not clean_first:
        raise HTTPException(400, "first_name_required")

    try:
        with safe_transaction(db):
            db.execute(
                text("""
                    UPDATE employees
                    SET first_name = :fn, last_name = :ln, status = 'active', status_reason = NULL
                    WHERE id = :id
                """),
                {"fn": clean_first, "ln": clean_last or None, "id": employee_id}
            )
            audit(db, org_id, "admin", user["id"], "EMPLOYEE_VERIFIED", employee_id,
                  {"previous_status": "pending_verification", "new_status": "active"})

        return {"status": "ok", "message": "employee_activated"}
    except Exception as e:
        logger.exception("employees.verify_and_activate_error")
        raise HTTPException(500, f"error_al_activar: {str(e)[:100]}")

@router.get("/employees/deleted")
async def get_deleted_employees(
    limit: Optional[int] = None,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Lista todos los empleados eliminados de la organizacion."""
    org_id = user["organization_id"]
    MAX_LIMIT = 2000
    safe_limit = min(limit or MAX_LIMIT, MAX_LIMIT)

    rows = db.execute(
        text("""
            SELECT
                e.id, e.first_name, e.last_name, e.file_number, e.dni, e.cuil, e.email, e.status,
                e.deleted_at
            FROM employees e
            WHERE e.organization_id = :org AND e.is_deleted = true
            ORDER BY e.deleted_at DESC
            LIMIT :limit
        """),
        {"org": org_id, "limit": safe_limit},
    ).fetchall()

    return {
        "employees": [
            {
                "id": str(r.id),
                "first_name": r.first_name,
                "last_name": r.last_name,
                "full_name": f"{r.first_name} {r.last_name or ''}".strip(),
                "file_number": r.file_number,
                "dni": r.dni,
                "cuil": r.cuil,
                "email": r.email,
                "status": r.status.value if hasattr(r.status, "value") else r.status,
                "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
            }
            for r in rows
        ]
    }


@router.get("/employees/{employee_id}")
async def get_employee_profile(
    employee_id: str,
    user=Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Obtiene el detalle completo de un legajo."""
    org_id = user["organization_id"]
    is_admin = user["role"] == "admin"
    
    # Seguridad: si no es admin, solo puede ver su propio perfil
    if not is_admin and str(user.get("employee_id")) != str(employee_id):
        if not is_admin:
            raise HTTPException(403, "not_authorized_to_view_other_employees_profile")

    row = db.execute(
        text("""
                 SELECT e.*, ed.ieric_number, ed.floor, ed.apartment, ed.tower,
                     ed.union_member_number, ed.unemployment_fund_account,
                     ed.legajo_number, ed.card_number, ed.paraje
            FROM employees e
            LEFT JOIN employee_extra_data ed ON ed.employee_id = e.id
            WHERE e.id = :id AND e.organization_id = :org
        """),
        {"id": employee_id, "org": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(404, "employee_not_found")

    emp_data = dict(row._mapping)
    # Formatear fechas, antigüedad y enums
    for key in ['birth_date', 'hire_date', 'termination_date', 'created_at']:
        if emp_data.get(key):
            if hasattr(emp_data[key], 'isoformat'):
                emp_data[key] = emp_data[key].isoformat()
            else:
                emp_data[key] = str(emp_data[key])
    
    if "status" in emp_data:
        st = emp_data["status"]
        emp_data["status"] = st.value if hasattr(st, "value") else st
    
    # Agregar datos calculados
    emp_data["seniority_text"] = calculate_seniority(row.hire_date)
    emp_data["full_name"] = f"{row.first_name} {row.last_name or ''}".strip()

    return {"employee": emp_data}

@router.post("/employees")
async def upsert_employee(
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Crea o completa un empleado usando el Unified Ingestion Nucleus.
    """
    org_id = user["organization_id"]
    author_id = user["id"]
    
    # 1. Capture all form data
    form_data = await request.form()
    raw_payload = {k: v for k, v in form_data.items()}
    
    # 2. Process via Ingestion Nucleus in a transaction
    try:
        with safe_transaction(db):
            service = IngestionService(db, org_id, author_id)
            result = service.process_row(raw_payload, mode=IngestionMode.MANUAL)
    except Exception as e:
        logger.exception("employees.upsert_error")
        raise HTTPException(status_code=500, detail=str(e))
    
    if result.status == "failed":
        # Standardized Ingestion Error Response
        logger.warning(f"employees.upsert_failed: org={org_id} issues={[iss.code for iss in result.issues]}")
        return {
            "status": "failed",
            "errors": [iss.to_dict() for iss in result.issues if iss.level == "error"],
            "warnings": [iss.to_dict() for iss in result.issues if iss.level == "warning"]
        }

    if result.employee_id and "family_members" in raw_payload:
        persist_family_members(db, result.employee_id, raw_payload.get("family_members"), org_id)
    if result.employee_id:
        persist_clothing_delivery(db, result.employee_id, raw_payload, org_id)
        persist_template_fields(db, result.employee_id, raw_payload.get("nuevo_legajo"), org_id)

    return {
        "status": "ok",
        "employee_id": result.employee_id,
        "match": result.match_info
    }


@router.post("/employees/{employee_id}/restore")
async def restore_employee(
    employee_id: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Restaura un empleado eliminado (soft delete)."""
    org_id = user["organization_id"]

    try:
        with safe_transaction(db):
            existing = db.execute(
                text("SELECT id, dni FROM employees WHERE id = :id AND organization_id = :org AND is_deleted = true FOR UPDATE"),
                {"id": employee_id, "org": org_id}
            ).fetchone()

            if not existing:
                raise HTTPException(404, "empleado_eliminado_no_encontrado")

            # Restore the employee
            db.execute(
                text("UPDATE employees SET is_active = true, is_deleted = false, deleted_at = NULL, status = 'active', status_reason = 'Restaurado' WHERE id = :id"),
                {"id": employee_id}
            )

            # DI-01 & DM-01 Re-matching: try to recover orphaned receipts matching DNI
            # IMPORTANT: Only re-match genuinely pending receipts.
            # Signed/completed receipts must NEVER re-enter active workflows.
            import payroll_core
            linked = db.execute(text("""
                UPDATE payroll_receipts
                SET employee_id = :emp, 
                    status = (CASE 
                        WHEN :sig_mode = 'dual' AND employer_signed_at IS NULL THEN 'pending_employer_signature'
                        ELSE 'pending_employer_signature'
                    END)::receipt_status
                WHERE organization_id = :org
                  AND employee_id IS NULL
                  AND status = 'pending_match'
                  AND signed_at IS NULL
                  AND employee_signed_at IS NULL
                  AND is_deleted = false
                  AND (extracted_fields->>'dni' = :dni OR extracted_fields->>'document' = :dni)
                RETURNING id
            """), {
                "emp": employee_id, 
                "org": org_id, 
                "dni": existing.dni,
                "sig_mode": payroll_core.SIGNATURE_MODE
            }).fetchall()

            for r_row in linked:
                create_signature_request(db, str(r_row.id), org_id, employee_id)

            audit(db, org_id, "admin", user["id"], "RESTORE_EMPLOYEE", employee_id, {})

        return {"status": "ok", "message": "empleado_restaurado"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("employees.restore_error")
        raise HTTPException(500, "error_al_restaurar_empleado")


@router.delete("/employees/{employee_id}")
async def delete_employee(
    employee_id: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    GAP-010: Blocks deletion if the employee has signed receipts with legal evidence.
    Signed receipts are legally binding and losing the employee link breaks audit trails.
    """
    org_id = user["organization_id"]

    try:
        with safe_transaction(db):
            existing = db.execute(
                text("SELECT id FROM employees WHERE id = :id AND organization_id = :org AND is_deleted = false FOR UPDATE"),
                {"id": employee_id, "org": org_id}
            ).fetchone()

            if not existing:
                raise HTTPException(404, "empleado_no_encontrado")

            # Eliminamos el bloqueo GAP-010 a pedido del usuario.
            # Los recibos firmados quedarÃ¡n en el historial como 'pending_match' (huÃ©rfanos).
            # Manual cleanup of NO ACTION dependencies
            db.execute(text("DELETE FROM employee_laboral WHERE employee_id = :id"), {"id": employee_id})
            db.execute(text("DELETE FROM employee_previsional WHERE employee_id = :id"), {"id": employee_id})
            db.execute(text("DELETE FROM employee_banking WHERE employee_id = :id"), {"id": employee_id})
            db.execute(text("DELETE FROM employee_affiliations WHERE employee_id = :id"), {"id": employee_id})
            db.execute(text("DELETE FROM email_events WHERE employee_id = :id"), {"id": employee_id})

            db.execute(
                text("UPDATE employees SET is_active = false, is_deleted = true WHERE id = :id"),
                {"id": employee_id}
            )
            
            # Detach user from company so they can be "recruited" by another one later
            db.execute(text("""
                UPDATE users 
                SET organization_id = NULL, employee_id = NULL 
                WHERE employee_id = :id
            """), {"id": employee_id})
            
            # DI-01 & DM-01: Orphan only UNSIGNED receipts.
            # Signed receipts keep their employee_id to preserve historical integrity.
            db.execute(text("""
                UPDATE payroll_receipts 
                SET status = 'pending_match'::receipt_status, employee_id = NULL
                WHERE employee_id = :id AND organization_id = :org
                  AND status != 'signed'
                  AND signed_at IS NULL
                  AND employee_signed_at IS NULL
            """), {"id": employee_id, "org": org_id})
            
            # Enterprise receipts: only orphan unsigned
            db.execute(text("""
                UPDATE receipts 
                SET user_id = NULL 
                WHERE user_id = (SELECT id FROM users WHERE employee_id = :id)
                  AND status != 'signed'
                  AND signed_at IS NULL
            """), {"id": employee_id})

            audit(db, org_id, "admin", user["id"], "DELETE_EMPLOYEE", employee_id, {})

        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("employees.delete_error")
        raise HTTPException(500, "error_al_eliminar_empleado")

@router.delete("/employees/{employee_id}/hard")
async def hard_delete_employee(
    employee_id: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Permanently removes an employee from the database.
    This is used for 'Baja definitiva'.
    """
    org_id = user["organization_id"]

    try:
        with safe_transaction(db):
            # Check ownership and state
            existing = db.execute(
                text("SELECT id FROM employees WHERE id = :id AND organization_id = :org FOR UPDATE"),
                {"id": employee_id, "org": org_id}
            ).fetchone()

            if not existing:
                raise HTTPException(404, "empleado_no_encontrado")

            # Cleanup dependencies that might block or need manual care
            db.execute(text("DELETE FROM employee_extra_data WHERE employee_id = :id"), {"id": employee_id})
            db.execute(text("DELETE FROM email_events WHERE employee_id = :id"), {"id": employee_id})
            db.execute(text("DELETE FROM signature_requests WHERE employee_id = :id"), {"id": employee_id})
            
            # Orphan receipts — but protect signed receipts' status.
            # Since this is a hard delete, the FK will break, so we must clear employee_id
            # on ALL receipts. But for signed receipts, the snapshot columns preserve identity
            # and we do NOT reset their status to pending_match.
            
            # Signed receipts: clear FK only, keep status intact (snapshot preserves identity)
            db.execute(text("""
                UPDATE payroll_receipts 
                SET employee_id = NULL
                WHERE employee_id = :id
                  AND (status = 'signed' OR signed_at IS NOT NULL OR employee_signed_at IS NOT NULL)
            """), {"id": employee_id})
            
            # Unsigned receipts: orphan them fully
            db.execute(text("""
                UPDATE payroll_receipts 
                SET employee_id = NULL, status = 'pending_match'::receipt_status 
                WHERE employee_id = :id
            """), {"id": employee_id})

            # Finally delete the employee
            db.execute(text("DELETE FROM employees WHERE id = :id"), {"id": employee_id})

            audit(db, org_id, "admin", user["id"], "HARD_DELETE_EMPLOYEE", employee_id, {})

        return {"status": "ok", "message": "empleado_eliminado_definitivamente"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("employees.hard_delete_error")
        raise HTTPException(500, "error_al_eliminar_definitivamente")

@router.patch("/employees/{employee_id}")
async def update_employee(
    employee_id: str,
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Actualiza datos de un empleado.
    """
    org_id = user["organization_id"]

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = {k: v for k, v in form.items()}

    try:
        with safe_transaction(db):
            existing = db.execute(
                text("SELECT id, dni, first_name, last_name FROM employees WHERE id = :id AND organization_id = :org AND is_deleted = false FOR UPDATE"),
                {"id": employee_id, "org": org_id}
            ).fetchone()

            if not existing:
                raise HTTPException(404, "empleado_no_encontrado")

            old_dni = existing.dni
            new_dni = None

            update_fields = []
            params = {"id": employee_id}

            # Si viene full_name y no first_name, splitear (Legacy)
            if "full_name" in payload and "first_name" not in payload:
                parts = str(payload["full_name"]).strip().split(None, 1)
                payload["first_name"] = parts[0]
                if "last_name" not in payload and len(parts) > 1:
                    payload["last_name"] = parts[1]

            allowed_fields = [
                "first_name", "last_name", "dni", "cuil", "file_number", "ieric_number",
                "gender", "birth_date", "marital_status", "nationality",
                "email", "phone", "address", "address_number", "city", "province", "postal_code",
                "document_type", "document_number", "health_insurance",
                "health_insurance_number", "union", "union_number",
                "hire_date", "termination_date", "hire_type", "work_location",
                "job_title", "category", "task", "cost_center", "union_agreement",
                "pension_regime", "activity", "labor_condition", "revista_situation",
                "bank", "bank_code", "bank_branch", "account_type", "account_number", "cbu", "bank_alias",
                "payment_method", "payment_place", "status", "status_reason", "is_active"
            ]

            family_members_raw = payload.get("family_members")
            has_family_update = family_members_raw is not None
            if has_family_update:
                persist_family_members(db, employee_id, family_members_raw, org_id)

            has_clothing_update = any(key in payload for key in (
                "ropa_desde", "ropa_hasta", "ropa_vencimiento", "ropa_proximo_vencimiento"
            ))
            has_template_update = "nuevo_legajo" in payload

            extra_table_fields = {
                "floor": "floor",
                "apartment": "apartment",
                "tower": "tower",
                "union_member_number": "union_member_number",
                "unemployment_fund_account": "unemployment_fund_account",
                "legajo_number": "legajo_number",
                "card_number": "card_number",
                "paraje": "paraje",
            }

            # Mapeos de retrocompatibilidad para PATCH
            legacy_map = {
                "position": "job_title",
                "contract_type": "hire_type",
                "bank_name": "bank"
            }
            for k, v in legacy_map.items():
                if k in payload and v not in payload:
                    payload[v] = payload[k]

            extra_data_updates = {}
            for field in allowed_fields:
                if field in payload:
                    val = payload[field]

                    # Sanitización y normalización
                    if isinstance(val, str) and field not in ("dni", "cuil", "email", "cbu", "birth_date", "hire_date", "termination_date"):
                        val = sanitize_text_input(val)
                    
                    if field == "dni":
                        val = normalize_dni(val)
                        if not DNI_REGEX.match(val):
                            raise HTTPException(400, "formato_dni_invalido")
                        new_dni = val
                    elif field == "cuil":
                        val = normalize_cuil(val) if val else None
                        if val and not CUIL_REGEX.match(val):
                            raise HTTPException(400, "formato_cuil_invalido")
                    elif field == "email":
                        if val:
                            validate_email_format(val)
                    elif field == "cbu" and val:
                        val = re.sub(r"\D", "", str(val).strip())
                        if not CBU_REGEX.match(val):
                            raise HTTPException(400, "formato_cbu_invalido_debe_tener_22_digitos")

                    if field == "ieric_number":
                        extra_data_updates["ieric_number"] = val
                    else:
                        update_fields.append(f'"{field}" = :{field}')
                        params[field] = val

            for field, column in extra_table_fields.items():
                if field in payload:
                    val = payload[field]
                    if isinstance(val, str):
                        val = sanitize_text_input(val)
                    extra_data_updates[column] = val

            if not update_fields and not extra_data_updates and not has_family_update and not has_clothing_update and not has_template_update:
                return {"status": "ok", "message": "no_fields_to_update"}

            # GAP-009: Bloquear cambio de DNI si hay recibos firmados
            if new_dni and new_dni != old_dni:
                signed_count = _has_signed_receipts(db, employee_id)
                if signed_count > 0:
                    raise HTTPException(409, f"cannot_change_dni_employee_has_{signed_count}_signed_receipts")

            if update_fields:
                update_query = f"UPDATE employees SET {', '.join(update_fields)} WHERE id = :id"
                db.execute(text(update_query), params)

            if extra_data_updates:
                existing_extra = db.execute(
                    text("SELECT employee_id FROM employee_extra_data WHERE employee_id = :id"),
                    {"id": employee_id}
                ).fetchone()

                if existing_extra:
                    set_clauses = ["ieric_number = :ieric_number"]
                    params_extra = {"ieric_number": extra_data_updates.get("ieric_number"), "id": employee_id}
                    for col_name, value in extra_data_updates.items():
                        if col_name == "ieric_number":
                            continue
                        set_clauses.append(f"{col_name} = :{col_name}")
                        params_extra[col_name] = value
                    db.execute(
                        text(f"UPDATE employee_extra_data SET {', '.join(set_clauses)} WHERE employee_id = :id"),
                        params_extra,
                    )
                else:
                    insert_cols = ["employee_id"]
                    insert_values = [":id"]
                    insert_params = {"id": employee_id}
                    for col_name, value in extra_data_updates.items():
                        insert_cols.append(col_name)
                        insert_values.append(f":{col_name}")
                        insert_params[col_name] = value
                    db.execute(
                        text(f"INSERT INTO employee_extra_data ({', '.join(insert_cols)}) VALUES ({', '.join(insert_values)})"),
                        insert_params,
                    )

            if has_clothing_update:
                persist_clothing_delivery(db, employee_id, payload, org_id)
            if has_template_update:
                persist_template_fields(db, employee_id, payload.get("nuevo_legajo"), org_id)

            # If status became 'inactive', detach the user account to leave it "free" for other companies
            if payload.get("status") == "inactive":
                db.execute(text("""
                    UPDATE users 
                    SET organization_id = NULL, employee_id = NULL 
                    WHERE employee_id = :id
                """), {"id": employee_id})

            # GAP-009 / GAP-F02: Re-matching de recibos
            if new_dni and new_dni != old_dni:
                # Desvincular antiguos
                unlinked = db.execute(text("""
                    UPDATE payroll_receipts
                    SET employee_id = NULL, status = 'pending_match'::receipt_status
                    WHERE organization_id = :org
                      AND employee_id = :emp
                      AND status != 'signed'
                      AND signed_at IS NULL
                      AND employee_signed_at IS NULL
                      AND (extracted_fields->>'dni' = :old_dni OR extracted_fields->>'document' = :old_dni)
                    RETURNING id
                """), {"emp": employee_id, "org": org_id, "old_dni": old_dni}).fetchall()

                unlinked_ids = [str(r.id) for r in unlinked]
                if unlinked_ids:
                    db.execute(text("DELETE FROM signature_requests WHERE receipt_id = ANY(CAST(:ids AS UUID[]))"), {"ids": unlinked_ids})

                # Vincular nuevos huÃƒÂ©rfanos con chequeo dual-signature
                import payroll_core
                linked = db.execute(text("""
                    UPDATE payroll_receipts
                    SET employee_id = :emp, 
                        status = (CASE 
                            WHEN :sig_mode = 'dual' AND employer_signed_at IS NULL THEN 'pending_employer_signature'
                            ELSE 'pending_employer_signature'
                        END)::receipt_status
                    WHERE organization_id = :org
                      AND employee_id IS NULL
                      AND (extracted_fields->>'dni' = :new_dni OR extracted_fields->>'document' = :new_dni)
                    RETURNING id
                """), {
                    "emp": employee_id, 
                    "org": org_id, 
                    "new_dni": new_dni,
                    "sig_mode": payroll_core.SIGNATURE_MODE
                }).fetchall()

                for r_row in linked:
                    create_signature_request(db, str(r_row.id), org_id, employee_id)

            audit(db, org_id, "admin", user["id"], "UPDATE_EMPLOYEE", employee_id, payload)

        return {"status": "ok"}

    except IntegrityError as e:
        msg = str(e)
        if "uq_employee_org_legajo" in msg:
            raise HTTPException(409, "employee_legajo_exists")
        if "uq_employee_org_cuil" in msg:
            raise HTTPException(409, "employee_cuil_exists")
        raise HTTPException(409, "el_dni_o_cuil_ya_esta_registrado")
    except HTTPException:
        raise
    except Exception:
        logger.exception("employees.update_error")
        raise HTTPException(500, "error_al_actualizar_empleado")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("employees.update_error")
        raise HTTPException(500, "error_al_actualizar_empleado")

from modules.ocr_service import extract_dni_data

@router.get("/employees/{employee_id}/dni-image")
async def get_dni_image(
    employee_id: str,
    side: str = "front",
    user=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Securely serves the DNI image (front or back) for an employee.
    """
    org_id = user["organization_id"]
    column = "dni_image_path" if side == "front" else "dni_back_image_path"
    
    row = db.execute(
        text(f"SELECT {column} AS path FROM employees WHERE id = :id AND organization_id = :org AND is_deleted = false"),
        {"id": employee_id, "org": org_id}
    ).fetchone()

    if not row or not row.path:
        raise HTTPException(404, f"dni_{side}_not_found")

    p = Path(row.path)
    if not p.exists():
        raise HTTPException(404, "file_not_found")

    # Determine media type from extension
    ext = p.suffix.lower()
    media_type = "image/jpeg" if ext in ['.jpg', '.jpeg'] else "image/png" if ext == '.png' else "application/octet-stream"

    if _encryption_metadata_exists(db, p, org_id):
        temp_path = get_encryption_service().decrypt_file_to_temp(
            db,
            p,
            organization_id=str(org_id),
            actor_id=str(user.get("id")) if user.get("id") else None,
            actor_type="admin",
            purpose=f"identity_snapshot:dni_{side}",
            suffix=p.suffix,
        )
        return FileResponse(
            str(temp_path),
            media_type=media_type,
            background=BackgroundTask(EncryptionService.cleanup_temp_file, temp_path),
        )

    return FileResponse(str(p), media_type=media_type)

@router.post("/employees/{employee_id}/dni-upload")
async def upload_dni_image(
    employee_id: str,
    side: str = Form("front"),
    file: UploadFile = File(...),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Uploads a DNI image (front or back), saves it. Runs OCR if it's the front side.
    """
    org_id = user["organization_id"]
    if side not in ["front", "back"]:
        raise HTTPException(400, "el_lado_debe_ser_front_o_back")
    column = "dni_image_path" if side == "front" else "dni_back_image_path"
    
    # 1. Validate employee belongs to org
    existing = db.execute(
        text("SELECT id FROM employees WHERE id = :id AND organization_id = :org AND is_deleted = false"),
        {"id": employee_id, "org": org_id}
    ).fetchone()
    
    if not existing:
        raise HTTPException(404, "empleado_no_encontrado")

    # 2. Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(400, "el_archivo_debe_ser_una_imagen")

    # 3. Storage path
    from config import DNI_STORAGE_PATH
    os.makedirs(DNI_STORAGE_PATH, exist_ok=True)
    
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in [".jpg", ".jpeg", ".png"]:
        raise HTTPException(400, "formato_no_soportado_use_jpg_o_png")
    
    # GAP-003: Randomize filename to prevent enumeration
    random_suffix = secrets.token_hex(8)
    filename = f"{employee_id}_dni_{side}_{random_suffix}{file_ext}"
    file_path = os.path.join(DNI_STORAGE_PATH, filename)

    # 4. Save file & cleanup old one (Atomic & Consistent)
    try:
        # Get old path for cleanup
        old_path_row = db.execute(
            text(f"SELECT {column} AS path FROM employees WHERE id = :id AND is_deleted = false"),
            {"id": employee_id}
        ).fetchone()
        old_path = old_path_row.path if old_path_row else None

        import tempfile
        import shutil
        from file_processing.dispatcher import process_file

        with file_transaction(file_path):
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
                shutil.copyfileobj(file.file, tmp)
                tmp_name = tmp.name
                
            try:
                opt_path = process_file(tmp_name, "dni")
                shutil.copy(opt_path, file_path)
            finally:
                if os.path.exists(opt_path):
                    os.remove(opt_path)
                if os.path.exists(tmp_name):
                    try: os.remove(tmp_name)
                    except: pass
            
            ocr_result = None
            if side == "front":
                # 5. Run OCR (Fail-fast before DB commit)
                with open(file_path, "rb") as f:
                    img_bytes = f.read()
                ocr_result = extract_dni_data(img_bytes)

            encryption_metadata = _encrypt_dni_file_or_fail(
                db,
                file_path,
                organization_id=str(org_id),
                actor_id=str(user["id"]),
                employee_id=str(employee_id),
                side=side,
            )

            # 6. Update employee record and Audit
            with safe_transaction(db):
                db.execute(
                    text(f"UPDATE employees SET {column} = :path WHERE id = :id"),
                    {"path": file_path, "id": employee_id}
                )
                if encryption_metadata:
                    get_encryption_service().persist_metadata_and_audit(
                        db,
                        encryption_metadata,
                        actor_id=str(user["id"]),
                        actor_type="admin",
                    )
                audit(
                    db,
                    org_id,
                    "admin",
                    user["id"],
                    f"UPLOAD_DNI_{side.upper()}",
                    employee_id,
                    {
                        "file_name": os.path.basename(file_path),
                        "side": side,
                        "encryption_file_id": encryption_metadata.get("file_id") if encryption_metadata else None,
                    },
                )

        # If transaction succeeded, cleanup old one
        if old_path and os.path.exists(old_path) and os.path.abspath(old_path) != os.path.abspath(file_path):
            try:
                os.remove(old_path)
                logger.info(f"dni_upload.cleanup_old: removed {old_path}")
            except Exception as cleanup_err:
                logger.warning(f"dni_upload.cleanup_failed: {cleanup_err}")

    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        logger.exception("DNI_UPLOAD_SAVE_ERROR")
        # If OCR or DB failed, we still catch it here. 
        # But we want to return a graceful OCR failure if it was specifically an OCR error.
        if "ocr_result" not in locals():
            return {
                "success": True,
                "data": {
                    "dni": None,
                    "first_name": None,
                    "last_name": None,
                    "birth_date": None,
                    "error": "OCR_FAILED"
                }
            }
        raise HTTPException(500, "error_al_guardar_imagen")

    return {
        "success": True,
        "data": ocr_result
    }

@router.post("/employees/bulk-import")
@limiter.limit("5/minute", key_func=user_ip_key)
async def bulk_import_employees(
    request: Request,
    payload: dict,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Bulk import employees from array of records.
    Idempotent: won't create duplicates if DNI already exists.
    
    Payload: {
        "employees": [
            {"first_name": "Juan", "last_name": "PÃƒÂ©rez", "dni": "12345678"},
            {"first_name": "MarÃƒÂ­a", "last_name": "GarcÃƒÂ­a", "dni": "87654321"}
        ],
        "status": "pre_registered" | "pending_verification" (default: "pre_registered")
    }
    
    Returns: {
        "created": 15,
        "skipped": 5,
        "errors": []
    }
    """
    org_id = user["organization_id"]
    employees = payload.get("employees", [])
    desired_status = payload.get("status", "pre_registered")
    
    if desired_status not in ["pre_registered", "pending_verification"]:
        raise HTTPException(400, "invalid_status_must_be_pre_registered_or_pending_verification")
    
    if not employees:
        raise HTTPException(400, "employees_array_is_required")
    
    if len(employees) > 1000:
        raise HTTPException(400, "max_1000_employees_per_import")
    
    stats = {
        "created": 0,
        "skipped": 0,
        "errors": []
    }
    
    try:
        for i, emp_data in enumerate(employees):
            try:
                # Validate required fields
                first_name = (emp_data.get("first_name") or "").strip()
                last_name = (emp_data.get("last_name") or "").strip()
                dni = (emp_data.get("dni") or "").strip()
                
                if not first_name:
                    stats["errors"].append({
                        "index": i,
                        "error": "first_name_required",
                        "dni": dni
                    })
                    continue
                
                if not dni:
                    stats["errors"].append({
                        "index": i,
                        "error": "dni_required",
                        "first_name": first_name
                    })
                    continue
                
                # Normalize DNI
                try:
                    clean_dni = normalize_dni(dni)
                except HTTPException:
                    stats["errors"].append({
                        "index": i,
                        "error": "invalid_dni_format",
                        "dni": dni
                    })
                    continue
                
                # Check if employee already exists
                existing = db.execute(
                    text("SELECT id FROM employees WHERE organization_id = :org AND dni = :dni AND is_deleted = false"),
                    {"org": org_id, "dni": clean_dni}
                ).fetchone()
                
                if existing:
                    stats["skipped"] += 1
                    continue
                
                # Prepare status_reason
                status_reason = None
                if desired_status == "pending_verification":
                    status_reason = "bulk_import_pending_verification"
                
                # Create employee
                with safe_transaction(db):
                    db.execute(
                        text("""
                            INSERT INTO employees (
                                organization_id, first_name, last_name, dni, 
                                status, status_reason, profile_completed, is_active
                            ) VALUES (:org, :fn, :ln, :dni, :status, :reason, :pc, :active)
                        """),
                        {
                            "org": org_id,
                            "fn": first_name,
                            "ln": last_name or None,
                            "dni": clean_dni,
                            "status": desired_status,
                            "reason": status_reason,
                            "pc": False,
                            "active": True
                        }
                    )
                    stats["created"] += 1
                    
            except HTTPException as e:
                stats["errors"].append({
                    "index": i,
                    "error": e.detail,
                    "first_name": emp_data.get("first_name")
                })
            except Exception as e:
                logger.warning(f"employees.bulk_import_error index={i} err={e}")
                stats["errors"].append({
                    "index": i,
                    "error": str(e)[:100],
                    "first_name": emp_data.get("first_name")
                })
        
        # Log the bulk import
        audit(db, org_id, "admin", user["id"], "BULK_IMPORT_EMPLOYEES", None,
              {"created": stats["created"], "skipped": stats["skipped"], "errors": len(stats["errors"]), "status": desired_status})
        
        return stats
        
    except Exception as e:
        logger.exception("employees.bulk_import_error")
        raise HTTPException(500, f"error_en_importacion_masiva: {str(e)[:100]}")

@router.post("/employees/bulk-delete")
async def bulk_delete_employees(
    payload: dict,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    GAP-010: Bulk delete skips employees with signed receipts, returns partial results.
    Payload: {"ids": ["uuid1", "uuid2", ...]}
    """
    org_id = user["organization_id"]
    ids = payload.get("ids", [])
    if not ids:
        return {"status": "ok", "deleted_count": 0, "blocked": []}

    try:
        blocked = []
        safe_ids = []

        for emp_id in ids:
            signed_count = _has_signed_receipts(db, emp_id)
            if signed_count > 0:
                blocked.append({"id": emp_id, "reason": f"has_{signed_count}_signed_receipts"})
            else:
                safe_ids.append(emp_id)

        deleted_count = 0
        if safe_ids:
            with safe_transaction(db):
                # Manual cleanup of NO ACTION dependencies
                conn = db.connection()
                conn.execute(text("DELETE FROM employee_laboral WHERE employee_id = ANY(CAST(:ids AS UUID[]))"), {"ids": safe_ids})
                conn.execute(text("DELETE FROM employee_previsional WHERE employee_id = ANY(CAST(:ids AS UUID[]))"), {"ids": safe_ids})
                conn.execute(text("DELETE FROM employee_banking WHERE employee_id = ANY(CAST(:ids AS UUID[]))"), {"ids": safe_ids})
                conn.execute(text("DELETE FROM employee_affiliations WHERE employee_id = ANY(CAST(:ids AS UUID[]))"), {"ids": safe_ids})
                conn.execute(text("DELETE FROM email_events WHERE employee_id = ANY(CAST(:ids AS UUID[]))"), {"ids": safe_ids})

                result = db.execute(
                    text("""
                        UPDATE employees
                        SET is_active = false, is_deleted = true
                        WHERE organization_id = :org AND id = ANY(CAST(:ids AS UUID[]))
                    """),
                    {"org": org_id, "ids": safe_ids}
                )
                
                # Simulate SET NULL on receipts
                db.execute(text("""
                    UPDATE payroll_receipts 
                    SET status = 'pending_match'::receipt_status, employee_id = NULL
                    WHERE employee_id = ANY(CAST(:ids AS UUID[])) AND organization_id = :org
                """), {"ids": safe_ids, "org": org_id})
                
                db.execute(text("""
                    UPDATE receipts 
                    SET user_id = NULL 
                    WHERE user_id IN (SELECT id FROM users WHERE employee_id = ANY(CAST(:ids AS UUID[])))
                """), {"ids": safe_ids})
                deleted_count = result.rowcount
                audit(db, org_id, "admin", user["id"], "BULK_DELETE_EMPLOYEES", None,
                      {"deleted": deleted_count, "blocked": len(blocked)})

        return {
            "status": "partial" if blocked else "ok",
            "deleted_count": deleted_count,
            "blocked": blocked,
        }
    except Exception as e:
        logger.exception("employees.bulk_delete_error")
        raise HTTPException(500, "error_en_eliminacion_masiva")


@router.post("/employees/bulk-restore")
async def bulk_restore_employees(
    payload: dict,
    user=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Restores multiple employees from soft-delete state.
    """
    org_id = user["organization_id"]
    employee_ids = payload.get("employee_ids", [])

    if not employee_ids:
        return {"status": "ok", "restored": 0}

    try:
        with safe_transaction(db):
            result = db.execute(
                text("""
                    UPDATE employees 
                    SET is_deleted = false, is_active = true, deleted_at = NULL 
                    WHERE id = ANY(CAST(:ids AS uuid[])) AND organization_id = :org AND is_deleted = true
                    RETURNING id
                """),
                {"ids": employee_ids, "org": org_id}
            ).fetchall()
            
            restored_ids = [str(r.id) for r in result]
            audit(db, org_id, "admin", user["id"], "BULK_RESTORE_EMPLOYEES", None, {"count": len(restored_ids)})

        return {"status": "ok", "restored": len(restored_ids)}
    except Exception as e:
        logger.exception("employees.bulk_restore_error")
        raise HTTPException(500, "error_al_restaurar_empleados")


@router.post("/employees/bulk-hard-delete")
async def bulk_hard_delete_employees(
    payload: dict,
    user=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Permanently removes multiple employees.
    """
    org_id = user["organization_id"]
    employee_ids = payload.get("employee_ids", [])

    if not employee_ids:
        return {"status": "ok", "deleted": 0}

    try:
        with safe_transaction(db):
            # 1. Clean up dependencies for all selected employees
            db.execute(text("DELETE FROM employee_extra_data WHERE employee_id = ANY(CAST(:ids AS uuid[]))"), {"ids": employee_ids})
            db.execute(text("DELETE FROM email_events WHERE employee_id = ANY(CAST(:ids AS uuid[]))"), {"ids": employee_ids})
            db.execute(text("DELETE FROM signature_requests WHERE employee_id = ANY(CAST(:ids AS uuid[]))"), {"ids": employee_ids})
            
            db.execute(text("""
                UPDATE payroll_receipts 
                SET employee_id = NULL, status = 'pending_match'::receipt_status 
                WHERE employee_id = ANY(CAST(:ids AS uuid[]))
            """), {"ids": employee_ids})

            # 2. Delete the employees
            result = db.execute(
                text("DELETE FROM employees WHERE id = ANY(CAST(:ids AS uuid[])) AND organization_id = :org RETURNING id"),
                {"ids": employee_ids, "org": org_id}
            ).fetchall()

            deleted_ids = [str(r.id) for r in result]
            audit(db, org_id, "admin", user["id"], "BULK_HARD_DELETE_EMPLOYEES", None, {"count": len(deleted_ids)})

        return {"status": "ok", "deleted": len(deleted_ids)}
    except Exception as e:
        logger.exception("employees.bulk_hard_delete_error")
        raise HTTPException(500, "error_al_eliminar_definitivamente")


@router.get("/employees/me/signature")
async def get_my_signature(
    user=Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    GAP-004 & GAP 4 (UI Consistency): Returns the stored signature of the authenticated employee for UI preview.
    """
    if user["role"] != "employee" or not user.get("employee_id"):
        raise HTTPException(403, "solo_empleados_pueden_tener_firma_guardada")
        
    org_id = user["organization_id"]
    emp_id = user["employee_id"]
    
    # Use user_id to fetch from user_signatures Source of Truth
    user_id = user["id"]
    
    row = db.execute(
        text("SELECT signature_path FROM user_signatures WHERE user_id = :uid AND is_active = true ORDER BY created_at DESC LIMIT 1"),
        {"uid": user_id}
    ).fetchone()
    
    if not row or not row.signature_path:
        return {"has_signature": False}
        
    try:
        import base64
        sig_path = Path(resolve_storage_path(row.signature_path))
        if not sig_path.exists():
            return {"has_signature": False}
            
        b64_img = base64.b64encode(sig_path.read_bytes()).decode('utf-8')
        return {
            "has_signature": True,
            "signature_data": f"data:image/png;base64,{b64_img}"
        }
    except Exception as e:
        logger.error(f"failed_to_load_signature: {e}")
        return {"has_signature": False}


@router.get("/employees/{emp_id}/record-pdf")
async def get_employee_record_pdf(
    emp_id: str,
    include_termination_notice: bool = Query(default=False),
    user=Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    Phase 45: Generate and download the Employee Record PDF.
    """
    org_id = user["organization_id"]
    
    # Verify access: Needs to be admin, or the employee themselves
    if user["role"] != "admin" and user.get("employee_id") != emp_id:
        raise HTTPException(403, "acceso_denegado")
    if include_termination_notice and user["role"] != "admin":
        raise HTTPException(403, "solo_admin_puede_generar_notificacion_de_baja")

    from services.employee_pdf_service import EmployeePDFService
    import io
    from fastapi.responses import StreamingResponse
    from urllib.parse import quote
    import re
    
    try:
        pdf_service = EmployeePDFService(db)
        pdf_bytes = pdf_service.generate_record_pdf(emp_id, org_id, include_termination_notice=include_termination_notice)
        employee = db.execute(text("""
            SELECT first_name, last_name FROM employees
            WHERE id = :id AND organization_id = :org
        """), {"id": emp_id, "org": org_id}).fetchone()
        employee_name = " ".join(part for part in (employee.first_name, employee.last_name) if part).strip() if employee else "Empleado"
        document_title = f"NOTIFICACIÓN DE BAJA - {employee_name or 'Empleado'}" if include_termination_notice else f"LEGAJO - {employee_name or 'Empleado'}"
        safe_filename = re.sub(r"[^A-Za-z0-9._ -]", "", document_title).strip() or "LEGAJO DE PERSONAL"
        
        # Audit log
        audit(db, org_id, user["role"], user["id"], "EMPLOYEE_RECORD_DOWNLOADED", emp_id, {"format": "pdf", "termination_notice": include_termination_notice})
        
        return StreamingResponse(
            io.BytesIO(pdf_bytes), 
            media_type="application/pdf", 
            headers={
                "Content-Disposition": f"inline; filename=\"{safe_filename}.pdf\"; filename*=UTF-8''{quote(document_title + '.pdf')}",
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except ValueError as e:
        if str(e) == "employee_not_found":
            raise HTTPException(404, "empleado_no_encontrado")
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("record_pdf_generation_error")
        raise HTTPException(500, "error_generando_pdf")
