"""
Receipts API (SaaS DNI identity)

- ConciliaciÃ³n automÃ¡tica por DNI
- AutocreaciÃ³n empleados OCR
- Listado pendientes
- Descarga PDF
- Firma empleador
"""

import os
import secrets
import json
import base64
import shutil
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session
from sqlalchemy import text

import config
from payroll_core import (
    get_db, require_auth, require_admin, logger, safe_transaction,
    create_signature_request, get_existing_signature_request,
    utc_now, validate_organization_access,
    audit, safe_join_under_storage, hash_token, compute_file_sha256,
    validate_token_format, ALLOWED_STORAGE_DIR, resolve_storage_path
)
from payroll_utils import get_real_ip
from modules.signature import get_signature_engine
from modules.digital_signature import DigitalSignatureEngine, SignatureError
from services.signature_service import validate_and_fetch_signature_request
from services.document_repository import DocumentRepository
from services.encryption_service import (
    EncryptionService,
    KmsError,
    encryption_actor_type,
    get_encryption_service,
    record_kms_error_event,
)
from models.receipts import Receipt
from models.tables import Organization, UserSignature


router = APIRouter(prefix="/api/receipts", tags=["receipts"])


# =====================================================
# HELPERS
# =====================================================

def _validate_signature_image(sig_data: str) -> bytes:
    if not sig_data or not sig_data.startswith("data:image/"):
        raise HTTPException(400, "invalid_signature_format")
    try:
        _, b64data = sig_data.split(",", 1)
        return base64.b64decode(b64data)
    except Exception:
        raise HTTPException(400, "invalid_signature_format")


def _dni_sql_expr() -> str:
    """
    Extrae DNI desde extracted_fields con fallback:
    dni â†’ document â†’ CUIL
    """
    return """
        COALESCE(
            pr.extracted_fields->>'dni',
            pr.extracted_fields->>'document',
            SUBSTRING(REPLACE(pr.extracted_fields->>'cuil','-','') FROM 3 FOR 8)
        )
    """


def _encryption_metadata_exists(db: Session, file_path: str | Path, organization_id: str) -> bool:
    """Checks encrypted state without instantiating a KMS provider."""
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
        # The migration may not be applied yet in legacy/dev environments.
        try:
            db.rollback()
        except Exception:
            pass
        return False


def _maybe_decrypted_file_response(
    db: Session,
    file_path: str | Path,
    *,
    organization_id: str,
    user: Dict[str, Any],
    purpose: str,
    media_type: str,
    filename: Optional[str] = None,
    expected_plaintext_sha256: Optional[str] = None,
) -> FileResponse:
    path = Path(file_path)
    if _encryption_metadata_exists(db, path, organization_id):
        temp_path = get_encryption_service().decrypt_file_to_temp(
            db,
            path,
            organization_id=str(organization_id),
            actor_id=str(user.get("id")) if user.get("id") else None,
            actor_type=encryption_actor_type(user),
            purpose=purpose,
            expected_plaintext_sha256=expected_plaintext_sha256,
            suffix=path.suffix,
        )
        return FileResponse(
            str(temp_path),
            media_type=media_type,
            filename=filename,
            background=BackgroundTask(EncryptionService.cleanup_temp_file, temp_path),
        )

    return FileResponse(str(path), media_type=media_type, filename=filename)


def _record_kms_error_best_effort(
    db: Session,
    *,
    organization_id: str,
    actor_id: Optional[str],
    actor_type: str,
    file_id: str,
    purpose: str,
    error_code: str,
) -> None:
    try:
        record_kms_error_event(
            db,
            organization_id=str(organization_id),
            actor_id=actor_id,
            actor_type=actor_type,
            file_id=file_id,
            purpose=purpose,
            error_code=error_code,
        )
    except Exception:
        logger.exception("encryption.kms_error_audit_failed")


def _encrypt_signed_pdf_result(
    db: Session,
    pdf_result: Dict[str, Any],
    *,
    organization_id: str,
    actor_id: str,
    actor_type: str,
) -> None:
    """Encrypts the signed PDF before DB finalization."""
    if not config.APP_ENCRYPTION_ENABLED:
        return

    file_id = str(uuid.uuid4())
    signed_path = Path(pdf_result["signed_pdf_path"])
    metadata_items = []
    current_file_id = file_id
    current_purpose = "signed_receipt_pdf"
    try:
        service = get_encryption_service()
        metadata = service.encrypt_file_in_place(
            signed_path,
            organization_id=str(organization_id),
            purpose="signed_receipt_pdf",
            file_id=file_id,
            plaintext_sha256=pdf_result["new_pdf_sha256"],
        )
        pdf_result["encryption_metadata"] = metadata
        metadata_items.append(metadata)

        sig_path = Path(pdf_result["sig_image_path"])
        sig_file_id = str(uuid.uuid4())
        current_file_id = sig_file_id
        current_purpose = "signature_evidence_image"
        sig_metadata = service.encrypt_file_in_place(
            sig_path,
            organization_id=str(organization_id),
            purpose="signature_evidence_image",
            file_id=sig_file_id,
            plaintext_sha256=pdf_result["sig_image_sha256"],
        )
        metadata_items.append(sig_metadata)
        pdf_result["encryption_metadata_items"] = metadata_items
    except KmsError as exc:
        _record_kms_error_best_effort(
            db,
            organization_id=str(organization_id),
            actor_id=actor_id,
            actor_type=actor_type,
            file_id=current_file_id,
            purpose=current_purpose,
            error_code=str(exc),
        )
        try:
            signed_path.unlink(missing_ok=True)
        except Exception:
            logger.exception("encryption.plaintext_cleanup_failed_after_kms_error")
        try:
            Path(pdf_result["sig_image_path"]).unlink(missing_ok=True)
        except Exception:
            logger.exception("encryption.signature_image_cleanup_failed_after_kms_error")
        raise SignatureError("encryption_kms_failed_no_plaintext_persisted") from exc


def _encrypt_uploaded_file_or_503(
    db: Session,
    file_path: str | Path,
    *,
    organization_id: str,
    actor_id: str,
    actor_type: str,
    purpose: str,
    plaintext_sha256: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not config.APP_ENCRYPTION_ENABLED:
        return None

    file_id = str(uuid.uuid4())
    path = Path(file_path)
    try:
        return get_encryption_service().encrypt_file_in_place(
            path,
            organization_id=str(organization_id),
            purpose=purpose,
            file_id=file_id,
            plaintext_sha256=plaintext_sha256,
        )
    except KmsError as exc:
        _record_kms_error_best_effort(
            db,
            organization_id=str(organization_id),
            actor_id=actor_id,
            actor_type=actor_type,
            file_id=file_id,
            purpose=purpose,
            error_code=str(exc),
        )
        try:
            path.unlink(missing_ok=True)
        except Exception:
            logger.exception("encryption.upload_plaintext_cleanup_failed_after_kms_error")
        raise HTTPException(503, "kms_unavailable_encryption_failed") from exc


# =====================================================
# ENDPOINTS
# =====================================================

import time
_summary_cache = {}

def COALESCE_KEYS(data, keys, default=None):
    if not data: return default
    for k in keys:
        if k in data and data[k]:
            return str(data[k])
    return default

@router.get("/summary")
async def get_receipts_summary(
    user=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Returns a summary of counts for dashboard KPIs.
    Cached for 10 seconds to prevent DB overhead on fast reloads.
    """
    org_id = user["organization_id"]
    now = time.time()
    
    # GAP-012 Fix: Cache summary for 10 seconds to reduce DB load
    if org_id in _summary_cache and (now - _summary_cache[org_id]["ts"] < 10):
        return _summary_cache[org_id]["data"]
        
    unified_rows = db.execute(text("""
        WITH active_batches AS (
            SELECT DISTINCT batch_id 
            FROM payroll_receipts 
            WHERE organization_id = :oid 
              AND is_deleted = false 
              AND status != 'signed'
        ),
        all_receipts AS (
            SELECT status::text, receipt_pdf_sha256 as file_hash
            FROM payroll_receipts 
            WHERE organization_id = :oid 
              AND is_deleted = false
              AND batch_id IN (SELECT batch_id FROM active_batches)
        )
        SELECT status, COUNT(*) as count
        FROM all_receipts
        GROUP BY status
    """), {"oid": org_id}).fetchall()
    
    # Total active employees
    emp_count = db.execute(text("""
        SELECT COUNT(*) FROM employees 
        WHERE organization_id = :oid AND is_active = true AND is_deleted = false
    """), {"oid": org_id}).scalar()
    
    summary = {
        "pending": 0,
        "signed": 0,
        "rejected": 0,
        "pending_match": 0,
        "total_receipts": 0,
        "total_employees": emp_count
    }
    
    total = 0
    for row in unified_rows:
        status = row[0]
        cnt = row[1]
        total += cnt
        if status in ("pending_employee_signature", "pending_employer_signature", "pending_signature", "pending"):
            summary["pending"] += cnt
        elif status == "signed":
            summary["signed"] += cnt
        elif status == "rejected":
            summary["rejected"] += cnt
        elif status == "pending_match":
            summary["pending_match"] += cnt

    summary["total_receipts"] = total
    
    _summary_cache[org_id] = {"ts": now, "data": summary}
    return summary

@router.get("/pending")
async def list_pending_receipts(
    include_signed: bool = False,
    user=Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    Lista todos los recibos de la organizaciÃ³n.
    GAP-005: GET is now read-only â€” no tokens are created or rotated here.
    UX-07: Uses LEFT JOIN so pending_match receipts (no employee) are also visible.
    The sign_url is included only when a valid pending SR already exists (token not recoverable).
    """
    org_id = user["organization_id"]

    rows = db.execute(
        text("""
            SELECT
                pr.id,
                COALESCE(pr.extracted_fields->>'periodo','N/A') AS period,
                pr.status,
                pr.employee_id,
                COALESCE(pr.snapshot_employee_name, TRIM(e.first_name || ' ' || COALESCE(e.last_name, ''))) AS full_name,
                COALESCE(pr.snapshot_employee_dni, e.dni) AS dni,
                CASE WHEN sr.id IS NOT NULL THEN true ELSE false END AS has_pending_token
            FROM payroll_receipts pr
            LEFT JOIN employees e ON e.id = pr.employee_id
            LEFT JOIN LATERAL (
                SELECT id FROM signature_requests
                WHERE receipt_id = pr.id
                  AND organization_id = :org
                  AND status = 'pending'
                  AND token_expires_at > :now
                LIMIT 1
            ) sr ON true
            WHERE pr.organization_id = :org
              AND pr.is_deleted = false
              AND (:inc_signed = true OR pr.status != 'signed')
              AND pr.batch_id IN (
                  SELECT DISTINCT batch_id 
                  FROM payroll_receipts 
                  WHERE organization_id = :org 
                    AND is_deleted = false 
                    AND status != 'signed'
              )
            ORDER BY pr.created_at DESC
        """),
        {"org": org_id, "inc_signed": include_signed, "now": utc_now()}
    ).fetchall()

    results = []
    for r in rows:
        results.append({
            "id": str(r.id),
            "employee_name": r.full_name,
            "employee_dni": r.dni,
            "period": r.period,
            "status": r.status,
            # sign_url is intentionally None â€” admin must use "Obtener link" (POST /token)
            # to get an actual URL. This prevents token churn on every dashboard refresh.
            "signature_url": None,
            "has_pending_token": r.has_pending_token,
        })

    return results


@router.get("/history")
async def list_receipts_history(
    limit: Optional[int] = None,
    user=Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Returns all receipts for the organization ordered chronologically
    by created_at. Intended to be grouped by the frontend into a tree view.
    Now bimodal (Legacy + Enterprise).
    """
    org_id = user["organization_id"]

    # GAP-014 Fix: Defensive LIMIT to prevent OOM
    MAX_LIMIT = 2000
    safe_limit = min(limit or MAX_LIMIT, MAX_LIMIT)

    rows = db.execute(
        text("""
            SELECT * FROM (
                SELECT 
                    r.id, 
                    COALESCE(r.snapshot_employee_name, TRIM(e.first_name || ' ' || COALESCE(e.last_name, ''))) as employee_name,
                    r.employee_id,
                    COALESCE(r.snapshot_employee_dni, e.dni, r.extracted_fields->>'dni', r.extracted_fields->>'document') as employee_dni,
                    r.status::text as status,
                    r.created_at,
                    r.signed_at,
                    r.employer_signed_at,
                    r.extracted_fields->>'periodo' as period,
                    CASE WHEN r.payment_receipt_path IS NOT NULL THEN true ELSE false END AS has_payment_receipt,
                    r.receipt_pdf_sha256 as file_hash
                FROM payroll_receipts r
                LEFT JOIN employees e ON r.employee_id = e.id
                WHERE r.organization_id = :org_id AND r.is_deleted = false

                UNION ALL

                SELECT 
                    r.id, 
                    COALESCE(r.snapshot_employee_name, u.full_name) as employee_name,
                    u.employee_id,
                    COALESCE(r.snapshot_employee_dni, e.dni, r.receipt_metadata->>'dni') as employee_dni,
                    r.status::text as status,
                    r.created_at,
                    r.signed_at,
                    r.signed_at as employer_signed_at,
                    r.receipt_metadata->>'periodo' as period,
                    false AS has_payment_receipt,
                    r.file_hash as file_hash
                FROM receipts r
                LEFT JOIN users u ON r.user_id = u.id
                LEFT JOIN employees e ON u.employee_id = e.id
                WHERE r.company_id = :org_id AND r.is_deleted = false
            ) combined
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"org_id": org_id, "limit": safe_limit}
    ).mappings().fetchall()

    seen = set()
    deduped = []
    for r in rows:
        h = r.get("file_hash")
        if h and h in seen: continue
        if h: seen.add(h)
        d = dict(r)
        d.pop("file_hash", None)
        deduped.append(d)

    return {"receipts": deduped}



@router.get("/employee/{employee_id}")
async def list_employee_receipts(
    employee_id: str,
    user=Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    Lista los recibos de un empleado especÃ­fico.
    GAP-006: GET is now read-only â€” no tokens are created here.
    The employee sees their receipts and a sign_url only if a valid pending SR exists.
    If no SR exists, the admin must generate one; the employee sees the receipt status only.
    """
    org_id = user["organization_id"]
    is_admin = user["role"] == "admin"

    # Seguridad: si no es admin, solo puede ver sus propios recibos
    if not is_admin and str(user["employee_id"]) != str(employee_id):
        raise HTTPException(403, "not_authorized_to_view_other_employees_receipts")

    rows = db.execute(
        text("""
            SELECT
                id,
                status,
                extracted_fields,
                signed_at,
                created_at
            FROM payroll_receipts
            WHERE organization_id = :org AND employee_id = :emp AND is_deleted = false
            ORDER BY created_at DESC
        """),
        {"org": org_id, "emp": employee_id}
    ).fetchall()

    results = []
    for r in rows:
        sign_url = None
        sr_row = None
        if r.status == "pending_employee_signature":
            # GAP-006: Only reuse an existing valid token â€” never create one in a GET.
            # The token hash is stored; the raw token is not recoverable from DB.
            # If no valid SR exists, sign_url remains None and the admin must generate one.
            sr_row = db.execute(
                text("""
                    SELECT token_hash FROM signature_requests
                    WHERE receipt_id = :rid AND status = 'pending'
                      AND token_expires_at > :now
                    ORDER BY requested_at DESC LIMIT 1
                """),
                {"rid": str(r.id), "now": utc_now()}
            ).fetchone()
            # sign_url stays None â€” raw token cannot be recovered from hash.
            # This is intentional: employee uses the link they received via email/admin.

        results.append({
            "id": str(r.id),
            "status": r.status,
            "period": r.extracted_fields.get("periodo", "N/A") if r.extracted_fields else "N/A",
            "extracted_fields": r.extracted_fields,
            "signed_at": r.signed_at.isoformat() if r.signed_at else None,
            "created_at": r.created_at.isoformat(),
            "sign_url": sign_url,
            "has_pending_token": sr_row is not None if r.status == "pending_employee_signature" else None,
        })

    return {"receipts": results}


@router.get("/my-history")
async def get_my_receipt_history(
    user=Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    Unified Source of Truth: Returns all receipts (Legacy and Enterprise) 
    for the authenticated user, normalized for the frontend.
    """
    user_id = user["id"]
    employee_id = user.get("employee_id")
    results = []

    # 1. Fetch from 'receipts' (New Enterprise Architecture)
    rows_ent = db.execute(text("""
        SELECT 
            r.id, r.created_at, r.status, r.signed_at, 
            o.name as company_name, r.receipt_metadata as metadata,
            r.file_hash
        FROM receipts r
        JOIN organizations o ON r.company_id = o.id
        WHERE r.user_id = :uid AND r.is_deleted = false
    """), {"uid": user_id}).fetchall()

    for r in rows_ent:
        results.append({
            "id": str(r.id),
            "source": "enterprise",
            "date": r.created_at.isoformat(),
            "company_name": r.company_name,
            "status": r.status,
            "period": r.metadata.get("periodo", "N/D") if r.metadata else "N/D",
            "dni": r.metadata.get("dni", "N/D") if r.metadata else "N/D",
            "signed_at": r.signed_at.isoformat() if r.signed_at else None,
            "can_sign": r.status in ("pending", "pending_signature", "pending_employee_signature"),
            "file_hash": r.file_hash
        })

    # 2. Fetch from 'payroll_receipts' (Legacy Architecture)
    # Robust Visibility: Find by direct link OR DNI/Email match
    user_dni = None
    user_email = user.get("email", "").strip().lower()
    
    if user_email:
        # Phase 1: Try direct employee link if present
        if employee_id:
            dni_row = db.execute(text("SELECT dni FROM employees WHERE id = :eid"), {"eid": employee_id}).fetchone()
            if dni_row:
                user_dni = dni_row.dni
        
        # Phase 2: Try email fallback (find DNI from any employee profile with this email)
        if not user_dni:
            dni_row = db.execute(text("""
                SELECT dni FROM employees 
                WHERE LOWER(TRIM(email)) = :email AND organization_id = :org
                ORDER BY is_deleted ASC, created_at DESC
                LIMIT 1
            """), {"email": user_email, "org": user["organization_id"]}).fetchone()
            if dni_row:
                user_dni = dni_row.dni

    # Execute Legacy Query with maximum inclusion
    rows_leg = db.execute(text("""
        SELECT 
            pr.id, pr.created_at, pr.status, pr.employee_signed_at as signed_at,
            o.name as company_name, pr.extracted_fields as metadata,
            pr.receipt_pdf_sha256 as file_hash
        FROM payroll_receipts pr
        JOIN organizations o ON pr.organization_id = o.id
        WHERE (
            pr.employee_id = :eid 
            OR (
                pr.organization_id = :org 
                AND (
                    COALESCE(
                        pr.extracted_fields->>'dni', 
                        pr.extracted_fields->>'DNI', 
                        pr.extracted_fields->>'documento',
                        pr.extracted_fields->>'cuil'
                    ) = :dni
                    OR LOWER(TRIM(pr.extracted_fields->>'email')) = :email
                )
            )
        )
        AND pr.is_deleted = false
    """), {
        "eid": employee_id, 
        "dni": user_dni, 
        "email": user_email, 
        "org": user["organization_id"]
    }).fetchall()

    for r in rows_leg:
        results.append({
            "id": str(r.id),
            "source": "legacy",
            "date": r.created_at.isoformat(),
            "company_name": r.company_name,
            "status": r.status,
            "period": r.metadata.get("periodo", "N/D") if r.metadata else "N/D",
            "dni": r.metadata.get("dni", "N/D") if r.metadata else "N/D",
            "signed_at": r.signed_at.isoformat() if r.signed_at else None,
            # In legacy, employee can sign if it's pending their signature
            "can_sign": r.status in ("pending", "pending_signature", "pending_employee_signature"),
            "file_hash": r.file_hash
        })

    # 3. Deduplicate and Sort
    seen = set()
    deduped = []
    for res in results:
        h = res.pop("file_hash", None)
        if h and h in seen: continue
        if h: seen.add(h)
        deduped.append(res)

    # 4. Include company_documents uploaded by the user so employees
    # can see files they uploaded (e.g. signed custom documents like UNEMPLOYMENT)
    try:
        docs_rows = db.execute(text("""
            SELECT cd.id, cd.created_at, cd.status, cd.doc_type, cd.file_name, cd.metadata, o.name as company_name
            FROM company_documents cd
            JOIN organizations o ON cd.organization_id = o.id
            WHERE cd.organization_id = :org AND cd.status != 'DELETED'
              AND (cd.metadata->'uploaded_by'->>'user_id') = :uid
        """), {"org": user["organization_id"], "uid": user_id}).fetchall()

        for r in docs_rows:
            deduped.append({
                "id": str(r.id),
                "source": "company_document",
                "date": r.created_at.isoformat(),
                "company_name": r.company_name,
                "status": r.status,
                "period": r.metadata.get("periodo", "N/D") if r.metadata else "N/D",
                "dni": r.metadata.get("dni", "N/D") if r.metadata else "N/D",
                "signed_at": None,
                "can_sign": False,
                "doc_type": (r.doc_type or "MISC") if hasattr(r, 'doc_type') else (r.metadata.get('doc_type') if r.metadata else 'MISC'),
            })
    except Exception:
        # Non-fatal: if company_documents cannot be fetched, continue returning receipts
        logger = __import__('logging').getLogger('dircom.payroll')
        logger.exception('employee_history_company_documents_fetch_failed')

    deduped.sort(key=lambda x: x["date"], reverse=True)
    
    return {"receipts": deduped}


@router.post("/{receipt_id}/simple-sign")
async def simple_sign_receipt(
    receipt_id: str,
    request: Request,
    user=Depends(require_auth),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None
):
    """
    High-Integrity Simple Signing:
    1. Validates ownership and status.
    2. Fetches active UserSignature.
    3. Creates a permanent legal snapshot in the Receipt record.
    4. Applies PAdES signature to the PDF.
    5. Locks the record (immutability).
    """
    user_id = user["id"]
    
    # 1. Fetch receipt from either table and set processing flag
    with safe_transaction(db):
        # Try enterprise table first
        from models.receipts import Receipt
        from models import PayrollReceipt
        
        receipt = db.query(Receipt).filter(
            Receipt.id == receipt_id,
            Receipt.user_id == user_id
        ).with_for_update().first()
        
        source = "enterprise"
        
        if not receipt:
            # Try legacy table with Robust Identity Check
            # 1. Fetch user's DNI (even from deleted profile)
            user_dni = None
            dni_row = db.execute(text("SELECT dni FROM employees WHERE email = :email AND organization_id = :org LIMIT 1"), 
                                {"email": user["email"], "org": user["organization_id"]}).fetchone()
            if dni_row:
                user_dni = dni_row.dni

            # 2. Query legacy table (locked by org)
            receipt = db.query(PayrollReceipt).filter(
                PayrollReceipt.id == receipt_id,
                PayrollReceipt.organization_id == user["organization_id"]
            ).with_for_update().first()
            if receipt:
                # Validate ownership: by employee_id link OR metadata (DNI/Email)
                is_owner = (
                    (receipt.employee_id and str(receipt.employee_id) == str(user.get("employee_id"))) or
                    (receipt.extracted_fields.get("dni") == user_dni) or
                    (receipt.extracted_fields.get("email") == user["email"])
                )
                if is_owner:
                    source = "legacy"
                else:
                    receipt = None # Access denied
        
        if not receipt:
            raise HTTPException(404, "receipt_not_found_or_access_denied")
            
        if receipt.status == "signed":
            raise HTTPException(400, "recibo_ya_firmado")
            
        if getattr(receipt, "processing_signature", False):
            raise HTTPException(409, "recibo_en_proceso")
            
        # 2. Fetch active signature
        sig = db.query(UserSignature).filter(
            UserSignature.user_id == user_id,
            UserSignature.is_active == True
        ).order_by(UserSignature.created_at.desc()).first()
        
        if not sig:
            raise HTTPException(400, "signature_required")
            
        try:
            sig_path = Path(resolve_storage_path(sig.signature_path))
        except Exception:
            raise HTTPException(400, "archivo_firma_no_encontrado")
            
        if not sig_path.exists():
            raise HTTPException(400, "archivo_firma_no_encontrado")
            
        sig_bytes = sig_path.read_bytes()
        
        # 3. Legal Snapshot
        from hashlib import sha256
        sig_hash = sha256(sig_bytes).hexdigest()
        
        receipt.signature_snapshot = sig_bytes
        receipt.signature_hash = sig_hash
          # 4. Apply Digital Signature (PAdES)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    
    # Robust Identity Extraction
    dni = None
    cuil = None
    
    if source == "legacy":
        # Legacy fields
        dni = receipt.extracted_fields.get("dni")
        cuil = receipt.extracted_fields.get("cuil")
        org_id = receipt.organization_id
        pdf_path = receipt.receipt_pdf_path
    else:
        # Enterprise fields
        dni = receipt.receipt_metadata.get("dni")
        cuil = receipt.receipt_metadata.get("cuil")
        org_id = receipt.company_id
        pdf_path = receipt.file_path

    # Fallback to employee profile if still missing
    if not dni or not cuil:
        emp_details = db.execute(text("SELECT cuil, dni FROM employees WHERE id = :eid"), {"eid": user["employee_id"]}).fetchone() if user.get("employee_id") else None
        if emp_details:
            dni = dni or emp_details.dni
            cuil = cuil or emp_details.cuil
    
    if not dni and not cuil:
        with safe_transaction(db):
             receipt.processing_signature = False
        raise HTTPException(400, "identidad_incompleta_contacte_rrhh")

    ctx = {
        "receipt_id": receipt_id,
        "organization_id": org_id,
        "role": "employee",
        "employee_id": user.get("employee_id"),
        "user_id": user_id,
        "receipt_pdf_path": pdf_path,
        "next_status": "signed",
        "doc_id": receipt_id,
        "full_name": user["full_name"],
        "cuil": cuil,
        "dni": dni,
        "source": "receipts" if source == "enterprise" else "payroll",
        "signing_nonce": f"NONCE-{secrets.token_hex(16).upper()}"
    }

    # Process PDF
    import asyncio
    from modules.digital_signature import _pdf_executor
    loop = asyncio.get_running_loop()
    try:
        pdf_result = await loop.run_in_executor(_pdf_executor, DigitalSignatureEngine.process_pdf, ctx, sig_bytes)
    except Exception as e:
        logger.error(f"pdf_signing_failed: {e}")
        with safe_transaction(db):
            # Fetch fresh since we committed the first part
            from models import PayrollReceipt
            from models.receipts import Receipt
            r = db.query(PayrollReceipt).get(receipt_id) if source == "legacy" else db.query(Receipt).get(receipt_id)
            if r: r.processing_signature = False
        raise HTTPException(500, "error_al_firmar_pdf")

    # 5. Finalize and Lock (and Mirror)
    with safe_transaction(db):
        from models import PayrollReceipt
        from models.receipts import Receipt
        r = db.query(PayrollReceipt).get(receipt_id) if source == "legacy" else db.query(Receipt).get(receipt_id)
        
        r.status = "signed"
        if source == "legacy":
            r.employee_signed_at = now
            r.signed_at = now
            r.receipt_pdf_sha256 = pdf_result["new_pdf_sha256"]
        else:
            r.employee_signed_at = now
            r.signed_at = now
            r.file_hash = pdf_result["new_pdf_sha256"]
            
        r.tsa_timestamp = now
        r.processing_signature = False
        
        # MIRRORING: If we sign in one table, try to update the other if it exists (linked by hash or ID)
        if source == "legacy":
            # Update enterprise table if mirrored
            db.execute(text("""
                UPDATE receipts SET status = 'signed', signed_at = :now, file_hash = :hash, employee_signed_at = :now
                WHERE company_id = :org AND file_hash = :old_hash
            """), {"now": now, "hash": pdf_result["new_pdf_sha256"], "org": org_id, "old_hash": pdf_result["old_pdf_sha256"]})
        else:
            # Update legacy table if mirrored
            db.execute(text("""
                UPDATE payroll_receipts SET status = 'signed', signed_at = :now, receipt_pdf_sha256 = :hash, employee_signed_at = :now
                WHERE organization_id = :org AND receipt_pdf_sha256 = :old_hash
            """), {"now": now, "hash": pdf_result["new_pdf_sha256"], "org": org_id, "old_hash": pdf_result["old_pdf_sha256"]})

        # Log and Seal
        audit(db, org_id, "employee", user_id, "SIMPLE_SIGN", receipt_id, {"source": source, "pdf_hash": pdf_result["new_pdf_sha256"]})
        
        seal_id = pdf_result.get("sig_id") or pdf_result.get("generated_seal_id")
        if seal_id:
            db.execute(text("""
                INSERT INTO receipt_seals (seal_id, receipt_id, organization_id, signer_dni, signer_name, signer_role, pdf_hash, metadata)
                VALUES (:sid, :rid, :org, :dni, :name, 'employee', :hash, :meta) ON CONFLICT (seal_id) DO NOTHING
            """), {
                "sid": seal_id, "rid": receipt_id, "org": org_id, "dni": dni or "N/D", "name": user["full_name"],
                "hash": pdf_result["new_pdf_sha256"], "meta": json.dumps({"ip": get_real_ip(request), "v_id": pdf_result.get("verification_id")})
            })
        
    return {"status": "signed", "signed_at": now.isoformat(), "pdf_hash": pdf_result["new_pdf_sha256"]}


@router.get("/pending-match")
async def list_pending_match(
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    GAP-R16: Returns receipts that are pending match explicitly, 
    with extracted DNI visible for admin resolution.
    """
    org_id = user["organization_id"]

    # GAP-005, UX-07, GAP-R16: Include receipts without an employee (pending_match).
    # The ON clause must not filter out NULL employee_ids from payroll_receipts.
    res = db.execute(
        text("""
            SELECT 
                r.id, 
                COALESCE(r.snapshot_employee_name, TRIM(e.first_name || ' ' || COALESCE(e.last_name, ''))) as employee_name,
                r.employee_id,
                COALESCE(r.snapshot_employee_dni, e.dni, r.extracted_fields->>'dni', r.extracted_fields->>'document') as employee_dni,
                r.status,
                r.created_at,
                (SELECT COUNT(*) FROM signature_requests sr WHERE sr.receipt_id = r.id AND sr.status = 'pending') > 0 as has_pending_token
            FROM payroll_receipts r
            LEFT JOIN employees e ON r.employee_id = e.id
            WHERE r.organization_id = :org_id
              AND r.is_deleted = false
              AND (r.status LIKE 'pending_%' OR r.status = 'rejected')
            ORDER BY r.created_at DESC
        """),
        {"org_id": org_id}
    ).mappings().fetchall()

    return {"receipts": [dict(r) for r in res]}

@router.delete("/{receipt_id}")
async def delete_receipt(
    receipt_id: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Delete a receipt and its associated file.
    Admin only. Organization check required.
    """
    org_id = user["organization_id"]

    with safe_transaction(db):
        # 1. Fetch receipt and lock â€” org boundary enforced at DB level (GAP-016 pattern)
        row = db.execute(
            text("""
                SELECT id, organization_id, receipt_pdf_path, status
                FROM payroll_receipts
                WHERE id = :id AND organization_id = :org
                FOR UPDATE
            """),
            {"id": receipt_id, "org": org_id},
        ).fetchone()

        if not row:
            raise HTTPException(404, "receipt_not_found")

        # 2. Delete from DB (CASCADE handles signature_requests)
        # SignatureEvidence has RESTRICT, so signed receipts with evidence will fail deletion.
        try:
            db.execute(
                text("UPDATE payroll_receipts SET is_deleted = true WHERE id = :id AND organization_id = :org"),
                {"id": receipt_id, "org": org_id}
            )
        except Exception as e:
            logger.error(
                "receipts.delete_failed",
                extra={"receipt_id": receipt_id, "error": str(e)}
            )
            raise HTTPException(
                400,
                "cannot_delete_signed_receipt_with_legal_evidence"
            )

        # 3. Audit
        audit(
            db,
            org_id,
            "admin",
            user["id"],
            "DELETE_RECEIPT",
            receipt_id,
            {"path": row.receipt_pdf_path}
        )

    # 4. Cleanup file outside transaction
    try:
        if row.receipt_pdf_path:
            # DM-03: Limpiar directorio de recibos si existe
            receipt_path = Path(row.receipt_pdf_path)
            if receipt_path.exists():
                try:
                    os.remove(receipt_path)
                except Exception:
                    pass

            # DM-03: Limpiar directorio de firmas si existe
            sig_dir = Path(ALLOWED_STORAGE_DIR) / "signatures" / org_id / receipt_id
            if sig_dir.exists() and sig_dir.is_dir():
                try:
                    shutil.rmtree(sig_dir)
                except Exception:
                    pass

            logger.info(f"Deleted physical file: {row.receipt_pdf_path}")
    except Exception as e:
        logger.warning(
            "receipts.file_cleanup_failed",
            extra={"path": row.receipt_pdf_path, "error": str(e)}
        )

    return {"status": "deleted"}

@router.post("/bulk-delete")
async def bulk_delete_receipts(
    payload: dict,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    GAP-011: Partial bulk delete â€” skips signed receipts protected by RESTRICT evidence FK.
    Returns per-id results: deleted list + blocked list with reasons.
    Payload: {"ids": ["uuid1", "uuid2", ...]}
    """
    org_id = user["organization_id"]
    ids = payload.get("ids", [])
    if not ids:
        return {"status": "ok", "deleted_count": 0, "blocked": []}

    # 1. Fetch status and paths for all requested IDs within this org
    rows = db.execute(
        text("""
            SELECT id, receipt_pdf_path, status, employer_signed_at
            FROM payroll_receipts
            WHERE organization_id = :org AND id = ANY(CAST(:ids AS UUID[]))
        """),
        {"org": org_id, "ids": ids}
    ).fetchall()

    # 2. Classify: check for SignatureEvidence (RESTRICT FK protects these)
    blocked = []
    safe_ids = []
    safe_paths = []

    for r in rows:
        has_evidence = db.execute(
            text("""
                SELECT 1 FROM signature_evidence
                WHERE receipt_id = :rid
                LIMIT 1
            """),
            {"rid": str(r.id)}
        ).fetchone()

        if has_evidence:
            blocked.append({
                "id": str(r.id),
                "reason": "signed_receipt_with_legal_evidence"
            })
        elif getattr(r, "employer_signed_at", None) is not None:
            blocked.append({
                "id": str(r.id),
                "reason": "has_employer_signature"
            })
        else:
            safe_ids.append(str(r.id))
            if r.receipt_pdf_path:
                safe_paths.append(r.receipt_pdf_path)

    deleted_count = 0
    if safe_ids:
        with safe_transaction(db):
            result = db.execute(
                text("UPDATE payroll_receipts SET is_deleted = true WHERE id = ANY(CAST(:ids AS UUID[]))"),
                {"ids": safe_ids}
            )
            deleted_count = result.rowcount
            audit(db, org_id, "admin", user["id"], "BULK_DELETE_RECEIPTS", None,
                  {"deleted": deleted_count, "blocked": len(blocked), "ids": safe_ids})

    # 3. Cleanup files outside transaction
    deleted_files = 0
    for path in safe_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                deleted_files += 1
        except Exception as e:
            logger.warning(f"File cleanup failed for {path}: {str(e)}")

    return {
        "status": "partial" if blocked else "ok",
        "deleted_count": deleted_count,
        "files_deleted": deleted_files,
        "blocked": blocked,
    }


@router.post("/{receipt_id}/token")
async def generate_receipt_token(
    receipt_id: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Generates a signature token for employee to sign.
    - If employer already signed (status=pending_employee_signature): Returns token directly
    - Admin only. Organization check required.
    """
    org_id = user["organization_id"]

    # 1. Fetch receipt — org boundary enforced at DB level (GAP-016)
    row = db.execute(
        text("""
            SELECT id, employee_id, organization_id, status
            FROM payroll_receipts
            WHERE id = :id AND organization_id = :org AND is_deleted = false
        """),
        {"id": receipt_id, "org": org_id},
    ).fetchone()

    if not row:
        raise HTTPException(404, "receipt_not_found")

    if not row.employee_id:
        raise HTTPException(400, "receipt_not_matched_to_employee")

    # Terminal states: Cannot generate tokens
    if row.status == "signed":
        raise HTTPException(409, "cannot_generate_token_for_signed_receipt")
    
    if row.status == "rejected":
        raise HTTPException(409, "cannot_generate_token_for_rejected_receipt")

    # If status is pending_employee_signature: employer already signed, return token directly
    # Otherwise: raise error (receipt still needs employer signature)
    # GAP-022: Allow 'pending_signature' for first signers, and specific pending states for sequential signers.
    allowed_statuses = ("pending_signature", "pending_employee_signature", "pending_employer_signature")
    if row.status not in allowed_statuses:
        raise HTTPException(400, f"receipt_in_invalid_state_for_token_generation:{row.status}")

    # Create fresh signature request token
    with safe_transaction(db):
        sr = create_signature_request(db, str(row.id), org_id, str(row.employee_id))

        audit(
            db,
            org_id,
            "admin",
            user["id"],
            "GENERATE_TOKEN",
            receipt_id,
            {"token_expires_at": sr["expires_at"].isoformat(), "receipt_status": row.status}
        )

    return {
        "status": "ok",
        "sign_url": sr["sign_url"],
        "token": sr["token"],
        "expires_at": sr["expires_at"].isoformat()
    }


@router.post("/{receipt_id}/token/me")
async def get_my_signature_token(
    receipt_id: str,
    user=Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Allows a logged-in employee to retrieve or generate a token for their own receipt.
    """
    org_id = user["organization_id"]
    employee_id = user.get("employee_id")

    # 1. Fetch receipt and verify ownership (bimodal)
    doc = DocumentRepository.get_document(db, receipt_id)

    if not doc:
        raise HTTPException(404, "receipt_not_found")

    # 2. Verify ownership for employees (bimodal)
    is_enterprise = doc.get("source") == "enterprise"

    if is_enterprise:
        # Enterprise source maps to user_id directly
        if str(doc.get("employee_id")) != str(user["id"]):
             raise HTTPException(403, "access_denied_not_your_receipt")
    else:
        # Legacy source: Robust ownership check (link OR metadata)
        is_owner = False
        if doc.get("employee_id") and str(doc["employee_id"]) == str(employee_id):
            is_owner = True
        else:
            # Fallback to metadata check
            user_dni = None
            user_email = user.get("email", "").strip().lower()
            if employee_id:
                dni_row = db.execute(text("SELECT dni FROM employees WHERE id = :eid"), {"eid": employee_id}).fetchone()
                if dni_row: user_dni = dni_row.dni
            
            # Check DNI or Email in metadata
            meta = doc.get("metadata", {})
            if meta:
                meta_dni = COALESCE_KEYS(meta, ["dni", "DNI", "documento"])
                meta_email = str(meta.get("email", "")).strip().lower()
                if (user_dni and meta_dni == user_dni) or (user_email and meta_email == user_email):
                    is_owner = True
        
        if not is_owner:
            raise HTTPException(403, "access_denied_not_your_receipt")
    
    # GAP-022: Employees can sign if it's generally pending or explicitly pending for them.
    if doc["status"] not in ("pending", "pending_signature", "pending_employee_signature"):
        raise HTTPException(400, f"receipt_is_not_pending_employee_signature (current: {doc['status']})")

    # Create a fresh signature request token (always, to simplify UX)
    with safe_transaction(db):
        # For enterprise receipts, pass user["id"] as the receiver (employee_id column in signature_requests may hold user_id)
        # For legacy receipts, pass employee_id.
        receiver_id = user["id"] if is_enterprise else str(employee_id)
        sr = create_signature_request(db, receipt_id, org_id, receiver_id)

    return {
        "status": "ok",
        "token": sr["token"],
        "sign_url": sr["sign_url"],
        "expires_at": sr["expires_at"].isoformat()
    }


# =====================================================
# DOWNLOAD
# =====================================================

def _cleanup_temp_file(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        logger.warning(f"could_not_cleanup_temp_file {path}")


def _rebuild_legacy_receipt_page(db: Session, batch_id: str, page_number: int) -> str | None:
    """Attempts to rebuild a legacy payroll receipt page from the source batch PDF."""
    try:
        row = db.execute(
            text("""
                SELECT source_pdf_path FROM payroll_batches
                WHERE id = :id AND source_pdf_path IS NOT NULL
            """),
            {"id": batch_id}
        ).fetchone()
        if not row or not row.source_pdf_path:
            return None

        source_path = row.source_pdf_path
        if not os.path.exists(source_path):
            return None

        import fitz
        import tempfile

        with fitz.open(source_path) as doc:
            if page_number < 1 or page_number > doc.page_count:
                return None
            page = doc.load_page(page_number - 1)
            pdf_bytes = page.write_pdf()

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_file.write(pdf_bytes)
        temp_file.close()
        return temp_file.name
    except Exception:
        logger.exception("receipt_rebuild_failed")
        return None


@router.get("/{receipt_id}/download")
async def download_receipt(
    receipt_id: str,
    user=Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Supports downloading from both the new Receipt table and the legacy payroll_receipts table.
    Enforces organization boundary or user ownership depending on the role.
    """
    org_id = user.get("organization_id")

    # Use Repository (Bimodal)
    doc = DocumentRepository.get_document(db, receipt_id)
    
    if not doc:
        raise HTTPException(404, "receipt_not_found")

    # Boundary Check (GAP-016)
    if user.get("role") == "admin":
        if str(doc["organization_id"]) != str(org_id):
            raise HTTPException(403, "access_denied_org_boundary")
    else:
        # For employees, ensure they own the receipt (Bimodal)
        if doc.get("source") == "enterprise":
            if str(doc.get("employee_id")) != str(user.get("id")):
                raise HTTPException(403, "access_denied_not_your_receipt")
        else:
            # Legacy source: Robust ownership check (link OR metadata)
            is_owner = False
            emp_id = user.get("employee_id")
            if doc.get("employee_id") and str(doc["employee_id"]) == str(emp_id):
                is_owner = True
            else:
                # Fallback to metadata check
                user_dni = None
                user_email = str(user.get("email", "")).strip().lower()
                if emp_id:
                    dni_row = db.execute(text("SELECT dni FROM employees WHERE id = :eid"), {"eid": emp_id}).fetchone()
                    if dni_row: user_dni = dni_row.dni
                
                meta = doc.get("metadata", {})
                if meta:
                    meta_dni = COALESCE_KEYS(meta, ["dni", "DNI", "documento"])
                    meta_email = str(meta.get("email", "")).strip().lower()
                    if (user_dni and meta_dni == user_dni) or (user_email and meta_email == user_email):
                        is_owner = True
            
            if not is_owner:
                raise HTTPException(403, "access_denied_not_your_receipt")

    file_path = doc["path"]
    if not file_path:
         raise HTTPException(404, "file_path_missing_in_record")

    safe_path = safe_join_under_storage(file_path)
    if os.path.exists(safe_path):
        return _maybe_decrypted_file_response(
            db,
            safe_path,
            organization_id=str(doc["organization_id"]),
            user=user,
            purpose="signed_receipt_pdf",
            media_type="application/pdf",
            expected_plaintext_sha256=doc.get("hash"),
        )

    # Fallback: Rebuild missing legacy batch pages if available.
    if doc.get("source") == "payroll" and doc.get("batch_id") and doc.get("page_number"):
        rebuilt_path = _rebuild_legacy_receipt_page(db, doc["batch_id"], doc["page_number"])
        if rebuilt_path:
            logger.info(
                f"receipt_fallback_rebuilt: receipt_id={receipt_id} batch_id={doc['batch_id']} page_number={doc['page_number']}"
            )
            return FileResponse(
                rebuilt_path,
                media_type="application/pdf",
                filename=f"receipt_{receipt_id}.pdf",
                headers={"X-Delivery-Fallback": "reconstructed"},
                background=BackgroundTask(_cleanup_temp_file, rebuilt_path),
            )

    raise HTTPException(404, "file_not_found")


async def _perform_employer_signature(
    db: Session,
    receipt_id: str,
    org_id: str,
    signer_id: str,
    img_bytes: bytes,
    actor_id: str,
    ip_address: str,
    user_agent: str,
    user: Dict[str, Any], # Added user parameter
    background_tasks: BackgroundTasks = None
) -> Dict[str, Any]:
    """
    Internal helper to execute the 3-phase signature pipeline for an employer.
    """
    # Phase 1: Lock & Validate
    with safe_transaction(db):
        ctx = DigitalSignatureEngine.validate_and_lock(
            db,
            receipt_id=receipt_id,
            organization_id=org_id,
            role="employer"
        )
        ctx["user"] = user
        ctx["signature_origin"] = "STORED" if signer_id else "CANVAS"
        # Phase 2 Fix: Nonce Injection for Replay Protection
        import secrets
        ctx["signing_nonce"] = f"NONCE-{secrets.token_hex(16).upper()}"
        ctx["signer_identity"] = {
            "dni": user.get("dni", "00000000"),
            "full_name": user.get("full_name", "Admin"),
            "email": user.get("email", "admin@test.com")
        }
        if ctx.get("idempotent"):
            return {"status": "idempotent", "current_status": ctx["current_status"]}

    # Phase 2: PDF Processing (CPU bound)
    import asyncio
    loop = asyncio.get_event_loop()
    pdf_result = await loop.run_in_executor(
        None,
        DigitalSignatureEngine.process_pdf,
        ctx,
        img_bytes,
    )
    # Phase 3: Finalize DB
    try:
        _encrypt_signed_pdf_result(
            db,
            pdf_result,
            organization_id=org_id,
            actor_id=actor_id,
            actor_type="admin",
        )

        with safe_transaction(db):
            result = await DigitalSignatureEngine.finalize_db(
                db,
                ctx,
                pdf_result,
                actor_id=actor_id,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            
            # Audit
            audit(
                db,
                org_id,
                "admin",
                actor_id,
                "EMPLOYER_SIGN",
                receipt_id,
                {
                    "ip": ip_address,
                    "company_signer_id": signer_id,
                    "pdf_sha256_before": ctx["receipt_pdf_sha256"],
                    "pdf_sha256_after": result["pdf_sha256"],
                }
            )

            # Trigger background email if token was generated
            if background_tasks and result.get("employee_token"):
                from notifications.service import NotificationService
                notifier = NotificationService.get_instance()
                background_tasks.add_task(
                    notifier.send_signature_pending_notification,
                    receipt_id=receipt_id,
                    organization_id=result["organization_id"],
                    employee_id=result["employee_id"],
                    employee_token=result["employee_token"]
                )

            return result
    except Exception as e:
        # GAP-003: Error recovery â€” clear flag and clean up orphaned PDF
        try:
            with safe_transaction(db):
                DigitalSignatureEngine.clear_processing_flag(db, receipt_id)
        except:
            logger.error("signature.flag_cleanup_failed_employer")

        if pdf_result and pdf_result.get("signed_pdf_path"):
            signed_path = Path(pdf_result["signed_pdf_path"])
            try:
                if signed_path.exists():
                    # Gap 10.1: Forensic Quarantine — move instead of delete
                    quarantine_dir = Path(ALLOWED_STORAGE_DIR) / "forensics" / "failed_signatures"
                    quarantine_dir.mkdir(parents=True, exist_ok=True)
                    from datetime import datetime as _dt
                    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                    quarantine_path = quarantine_dir / f"{ts}_{signed_path.name}"
                    import shutil
                    shutil.move(str(signed_path), str(quarantine_path))
                    logger.warning(f"signature.forensic_quarantine_employer: {signed_path} -> {quarantine_path}")
            except Exception:
                logger.error("signature.forensic_quarantine_failed_employer")
        raise e


# =====================================================
# SIGN EMPLOYER
# =====================================================
@router.post("/{receipt_id}/sign-employer")
async def sign_employer(
    receipt_id: str,
    payload: Dict[str, str],
    request: Request,
    background_tasks: BackgroundTasks,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Phase 2: Use company signer profile or drawn signature to stamp the PDF.
    Expects either:
    - {"company_signer_id": "uuid"} (pre-registered signer), or
    - {"signature": "<data:image/png;base64,...>"} (drawn signature)
    """
    org_id = user["organization_id"]
    signer_id = payload.get("company_signer_id")
    signature_data = payload.get("signature")
    img_bytes = None

    # GAP-013: Support both registered signers and drawn signatures
    signature_mode = "full_signature"
    
    if signer_id:
        # Use pre-registered company signer
        from payroll_core import sync_signer_image_from_db
        sig_path_str = sync_signer_image_from_db(db, signer_id)
        
        if not sig_path_str:
            # Legal Logging of missing signature (Requirement 2)
            logger.warning("SIGNATURE_IMAGE_MISSING", extra={
                "signer_id": signer_id,
                "org_id": org_id,
                "action": "sign_employer"
            })
            
            import config
            if config.SIGNATURE_VERSION == "v2":
                logger.info(f"signature_contingency_mode: signer {signer_id} missing file, using seal-only (v2)")
                img_bytes = None
                signature_mode = "seal_only"
            else:
                raise HTTPException(400, "Signature image missing. Please re-upload in Settings > Signers.")
        else:
            sig_path = Path(sig_path_str)
            img_bytes = sig_path.read_bytes()
    
    elif signature_data:
        # Use drawn signature from admin
        if not signature_data.startswith("data:image"):
            raise HTTPException(400, "invalid_signature_format")
        
        # Extract base64 part from data URL
        try:
            _, b64_str = signature_data.split(",", 1)
            img_bytes = base64.b64decode(b64_str)
            signer_id = None  # Explicitly set to None for drawn signatures
        except (ValueError, Exception):
            raise HTTPException(400, "malformed_signature_data_url")
    else:
        raise HTTPException(400, "company_signer_id_o_signature_requerido")

    try:
        result = await _perform_employer_signature(
            db,
            receipt_id=receipt_id,
            org_id=org_id,
            signer_id=signer_id,
            img_bytes=img_bytes,
            actor_id=user["id"],
            ip_address=get_real_ip(request),
            user_agent=request.headers.get("User-Agent", "unknown"),
            user=user,
            background_tasks=background_tasks
        )
        
        result["signature_mode"] = signature_mode

        if result.get("status") == "idempotent":
            return {"status": "signed", "idempotent": True}

        # Fetch employee info for email preview (GAP-018: Unified Bimodal Fetch)
        doc_info = DocumentRepository.get_document(db, receipt_id)
        if not doc_info:
             raise HTTPException(404, "receipt_not_found_post_sign")
        
        emp_email = doc_info["email"]
        emp_name = doc_info["full_name"]

        return {
            "status": "ok",
            "signed_at": result["signed_at"],
            "hash": result["pdf_sha256"],
            # GAP-004 FIX: Never leak employee token to admin
            "employee_email": emp_email,
            "employee_name": emp_name,
        }

    except Exception as e:
        logger.exception("sign_employer_error")
        from modules.digital_signature import InvalidStateError, SignatureError
        if isinstance(e, (InvalidStateError, SignatureError)):
            raise HTTPException(400 if isinstance(e, SignatureError) else 409, str(e))
        raise HTTPException(500, "error_al_firmar_recibo_empresa")


# =====================================================
# BULK SIGN EMPLOYER
# =====================================================
@router.post("/bulk-sign-employer")
async def bulk_sign_employer(
    payload: Dict[str, Any],
    request: Request,
    background_tasks: BackgroundTasks,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Signs multiple receipts at once using the specified company signer.
    Expects {"receipt_ids": ["uuid", ...], "company_signer_id": "uuid"}.
    """
    org_id = user["organization_id"]
    receipt_ids = payload.get("receipt_ids", [])
    signer_id = payload.get("company_signer_id")

    if not receipt_ids:
        raise HTTPException(400, "lista_de_ids_vacia")
    if not signer_id:
        raise HTTPException(400, "company_signer_id_requerido")

    # Fetch signer image once
    signer_row = db.execute(
        text("SELECT signature_image_path FROM company_signers WHERE id = :id AND organization_id = :org AND is_active = true"),
        {"id": signer_id, "org": org_id}
    ).fetchone()

    if not signer_row or not signer_row.signature_image_path:
        raise HTTPException(400, "firmante_invalido_o_sin_firma")

    sig_path = Path(signer_row.signature_image_path)
    if not sig_path.exists():
        raise HTTPException(400, "archivo_de_firma_extraviado")

    img_bytes = sig_path.read_bytes()
    actor_id = user["id"]
    ip = get_real_ip(request)
    ua = request.headers.get("User-Agent", "unknown")

    results = []
    errors = []

    for rid in receipt_ids:
        try:
            res = await _perform_employer_signature(
                db, rid, org_id, signer_id, img_bytes, actor_id, ip, ua, user, background_tasks
            )
            results.append({"id": rid, "status": "signed" if res.get("status") != "idempotent" else "already_signed"})
        except Exception as e:
            logger.warning(f"bulk_sign.item_failed rid={rid} err={e}")
            errors.append({"id": rid, "error": str(e)})

    return {
        "status": "partial" if errors and results else ("ok" if not errors else "error"),
        "signed_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors
    }


# =====================================================
# PAYMENT RECEIPT (Comprobante de Pago)
# =====================================================

@router.post("/{receipt_id}/payment-receipt")
async def upload_payment_receipt(
    receipt_id: str,
    request: Request,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Attach a payment proof (comprobante de pago) to a signed receipt.
    Accepts multipart form with 'file' field.
    """
    org_id = user["organization_id"]
    
    # 1. Verify receipt exists, belongs to org, and is signed
    row = db.execute(
        text("""
            SELECT id, status, organization_id FROM payroll_receipts
            WHERE id = :id AND organization_id = :org AND is_deleted = false
        """),
        {"id": receipt_id, "org": org_id}
    ).fetchone()
    
    if not row:
        raise HTTPException(404, "receipt_not_found")
    
    if row.status != "signed":
        raise HTTPException(400, "solo_se_puede_adjuntar_comprobante_a_recibos_firmados")
    
    # 2. Read file from multipart
    form = await request.form()
    file = form.get("file")
    if not file:
        raise HTTPException(400, "archivo_requerido")
    
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(413, "archivo_excede_10mb")
    
    # 3. Save file
    payment_dir = os.path.join(ALLOWED_STORAGE_DIR, "payment_receipts", org_id)
    os.makedirs(payment_dir, exist_ok=True)
    
    ext = os.path.splitext(file.filename)[1] if file.filename else ".pdf"
    safe_filename = f"{receipt_id}_comprobante_{secrets.token_hex(8)}{ext}"
    file_path = os.path.join(payment_dir, safe_filename)
    
    with open(file_path, "wb") as f:
        f.write(content)
    payment_plaintext_sha256 = compute_file_sha256(file_path)
    encryption_metadata = _encrypt_uploaded_file_or_503(
        db,
        file_path,
        organization_id=str(org_id),
        actor_id=str(user["id"]),
        actor_type="admin",
        purpose="payment_receipt",
        plaintext_sha256=payment_plaintext_sha256,
    )
    
    # 4. Update DB
    from datetime import datetime, timezone
    with safe_transaction(db):
        db.execute(
            text("""
                UPDATE payroll_receipts
                SET payment_receipt_path = :path,
                    payment_upload_date = :date,
                    payment_uploaded_by = :user_id
                WHERE id = :id AND organization_id = :org
            """),
            {
                "path": file_path,
                "date": datetime.now(timezone.utc),
                "user_id": user["id"],
                "id": receipt_id,
                "org": org_id
            }
        )
        if encryption_metadata:
            get_encryption_service().persist_metadata_and_audit(
                db,
                encryption_metadata,
                actor_id=str(user["id"]),
                actor_type="admin",
            )
        audit(db, org_id, "admin", user["id"], "UPLOAD_PAYMENT_RECEIPT", receipt_id,
              {
                  "filename": file.filename,
                  "size": len(content),
                  "encryption_file_id": encryption_metadata.get("file_id") if encryption_metadata else None,
                  "plaintext_sha256": payment_plaintext_sha256,
              })
    
    return {
        "status": "ok",
        "message": "comprobante_adjuntado",
        "filename": file.filename
    }


@router.get("/{receipt_id}/payment-receipt")
async def download_payment_receipt(
    receipt_id: str,
    user=Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Download the payment proof attached to a receipt."""
    org_id = user["organization_id"]
    
    row = db.execute(
        text("""
            SELECT payment_receipt_path FROM payroll_receipts
            WHERE id = :id AND organization_id = :org AND is_deleted = false
        """),
        {"id": receipt_id, "org": org_id}
    ).fetchone()
    
    if not row:
        raise HTTPException(404, "receipt_not_found")
    
    if not row.payment_receipt_path:
        raise HTTPException(404, "no_payment_receipt_attached")
    
    if not os.path.exists(row.payment_receipt_path):
        raise HTTPException(404, "payment_receipt_file_not_found")
    
    return _maybe_decrypted_file_response(
        db,
        row.payment_receipt_path,
        organization_id=str(org_id),
        user=user,
        purpose="payment_receipt",
        media_type="application/octet-stream",
        filename=os.path.basename(row.payment_receipt_path),
    )

# =====================================================
# PUBLIC SEAL VERIFICATION
# =====================================================

@router.get("/v/{seal_id}")
async def verify_seal(seal_id: str, db: Session = Depends(get_db)):
    """
    Public endpoint to verify a seal_id signature.
    Source of truth: receipt_seals table.
    """
    row = db.execute(text("""
        SELECT s.*, o.name as organization_name
        FROM receipt_seals s
        JOIN organizations o ON o.id = s.organization_id
        WHERE s.seal_id = :sid
    """), {"sid": seal_id}).fetchone()

    if not row:
        raise HTTPException(404, "seal_not_found")

    return {
        "status": "valid",
        "seal_id": row.seal_id,
        "document_id": str(row.receipt_id),
        "organization": row.organization_name,
        "signer": {
            "name": row.signer_name,
            "dni": row.signer_dni,
            "role": row.signer_role
        },
        "timestamp": row.created_at.isoformat(),
        "integrity_hash": row.pdf_hash
    }
