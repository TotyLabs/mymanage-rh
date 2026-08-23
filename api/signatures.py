"""
User Signature Storage API
Allows users to save their signature once and reuse it for one-click signing.
"""

import os
import base64
import tempfile
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
import imghdr
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

# Import from core
from payroll_core import get_db, logger, safe_transaction, require_auth, resolve_storage_path, ALLOWED_STORAGE_DIR
from services.document_service import DocumentService
from modules.digital_signature import DigitalSignatureEngine, _pdf_executor

router = APIRouter(prefix="/api/signatures", tags=["signatures"])

STORAGE_BASE = Path(ALLOWED_STORAGE_DIR)
SIGNATURES_DIR = STORAGE_BASE / "signatures" / "users"


def _sanitize_extra(extra: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Remove keys from `extra` that would overwrite LogRecord attributes.

    Logger's `extra` must not contain reserved LogRecord keys like 'filename'.
    """
    if not extra:
        return {}
    reserved = {
        'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
        'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
        'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
        'processName', 'process'
    }
    return {k: v for k, v in extra.items() if k not in reserved}


def _safe_log_info(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    try:
        if extra:
            logger.info(message, extra=_sanitize_extra(extra))
        else:
            logger.info(message)
    except Exception:
        try:
            logger.info(message)
        except Exception:
            pass


def _safe_log_exception(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    try:
        if extra:
            logger.exception(message, extra=_sanitize_extra(extra))
        else:
            logger.exception(message)
    except Exception:
        try:
            logger.exception(message)
        except Exception:
            pass


def _resolve_signature_with_fallback(path_str: str) -> Optional[Path]:
    """Try sensible legacy variants for a stored signature_path and return the first existing Path.
    This avoids deactivating DB records when files were migrated with different folder layouts.
    """
    tried = set()
    candidates = []

    # As-stored
    candidates.append(path_str)

    p = Path(path_str)

    # Remove leading 'storage/' prefix if present
    s = str(p)
    if s.startswith('storage/'):
        candidates.append(s[len('storage/'):])

    # If path contains '/source/' try without it
    if '/source/' in s:
        candidates.append(s.replace('/source/', '/'))
    else:
        # Try inserting a 'source' folder before the filename
        candidates.append(str(p.parent / 'source' / p.name))

    # Try placing the file under the canonical signatures directory (basename fallback)
    candidates.append(str(SIGNATURES_DIR / p.name))

    for cand in candidates:
        if not cand or cand in tried:
            continue
        tried.add(cand)
        try:
            resolved = resolve_storage_path(cand)
            sig_file = Path(resolved)
            if sig_file.exists():
                logger.info(f"signature.found_via_fallback: {cand} -> {resolved}")
                return sig_file
        except Exception:
            # ignore resolution errors and try next candidate
            continue

    return None


def _validate_image_format(img_bytes: bytes) -> str:
    """Valida que sea PNG o JPG real inspeccionando el contenido.

    Usa `imghdr.what` para cubrir variantes de JPEG/PNG (p.ej. progressive,
    metadatos adicionales) y cae en comprobaciones de magic bytes como respaldo.
    """
    try:
        kind = imghdr.what(None, img_bytes)
    except Exception:
        kind = None

    if kind == 'png':
        return '.png'
    if kind in ('jpeg', 'jpg'):
        return '.jpg'

    # Fallback: explicit magic-bytes checks
    if img_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if img_bytes.startswith(b"\xff\xd8"):
        return ".jpg"

    raise HTTPException(400, "el_formato_de_firma_debe_ser_png_o_jpg")

def _compute_sha256(img_bytes: bytes) -> str:
    sha256_hash = hashlib.sha256()
    sha256_hash.update(img_bytes)
    return sha256_hash.hexdigest()


def _resolve_active_signature_path(user_id: str, db: Session) -> Optional[Path]:
    row = db.execute(
        text("SELECT signature_path FROM user_signatures WHERE user_id = :id AND is_active = true ORDER BY created_at DESC LIMIT 1"),
        {"id": user_id}
    ).fetchone()

    if not row or not row.signature_path:
        return None

    sig_file = None
    try:
        resolved = resolve_storage_path(row.signature_path)
        sig_file = Path(resolved)
        if not sig_file.exists():
            sig_file = _resolve_signature_with_fallback(row.signature_path)
    except Exception:
        sig_file = _resolve_signature_with_fallback(row.signature_path)

    if sig_file and sig_file.exists():
        return sig_file

    with safe_transaction(db):
        db.execute(
            text("UPDATE user_signatures SET is_active = false WHERE user_id = :id"),
            {"id": user_id}
        )

    return None


@router.get("/user/me")
async def check_user_signature(
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Check if the current user has a stored signature."""
    user_id = user["id"]

    row = db.execute(
        text("SELECT signature_path, signature_hash FROM user_signatures WHERE user_id = :id AND is_active = true ORDER BY created_at DESC LIMIT 1"),
        {"id": user_id}
    ).fetchone()

    has_signature = False
    if row and row.signature_path:
        sig_file = None
        try:
            # First try the stored path as-is
            resolved = resolve_storage_path(row.signature_path)
            sig_file = Path(resolved)
            if not sig_file.exists():
                # Try legacy variants
                sig_file = _resolve_signature_with_fallback(row.signature_path)
        except Exception:
            # If direct resolution failed, try fallback candidates
            sig_file = _resolve_signature_with_fallback(row.signature_path)

        if sig_file and sig_file.exists():
            has_signature = True
        else:
            # Clean up stale reference only after all fallbacks fail
            with safe_transaction(db):
                db.execute(
                    text("UPDATE user_signatures SET is_active = false WHERE user_id = :id"),
                    {"id": user_id}
                )
    
    return {"has_signature": has_signature, "user_id": user_id}


@router.post("/user/save")
async def save_user_signature(
    request: Request,
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Save the user's signature image (base64 from canvas or upload)."""
    user_id = user["id"]

    body = await request.json()
    sig_data = body.get("signature_image", "")
    if not sig_data or len(sig_data) < 50:
        raise HTTPException(400, "firma_invalida")

    try:
        # Decode base64
        if "," in sig_data:
            sig_data = sig_data.split(",")[1]
        try:
            img_bytes = base64.b64decode(sig_data)
        except Exception:
            raise HTTPException(400, "firma_base64_invalida")

        # Validate format and size
        if len(img_bytes) > 2 * 1024 * 1024:  # 2MB
            raise HTTPException(400, "firma_excede_tamano_maximo")
        ext = _validate_image_format(img_bytes)

        user_dir = SIGNATURES_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        # Save atomically via a temp file and process it
        tmp_fd, tmp_path = tempfile.mkstemp(dir=user_dir, suffix=ext)
        with os.fdopen(tmp_fd, 'wb') as f:
            f.write(img_bytes)

        # Optimization Pipeline
        from file_processing.dispatcher import process_file
        opt_path = process_file(tmp_path, "signature")

        # Compute hash of the final optimized image
        with open(opt_path, "rb") as f:
            opt_bytes = f.read()
        img_hash = _compute_sha256(opt_bytes)

        # Get next version
        row_v = db.execute(
            text("SELECT max(version) as max_v FROM user_signatures WHERE user_id = :uid"),
            {"uid": user_id}
        ).fetchone()
        next_version = (row_v.max_v or 0) + 1

        # Check if hash is exactly the same as current active (prevent duplicates)
        current = db.execute(
            text("SELECT signature_hash FROM user_signatures WHERE user_id = :uid AND is_active = true ORDER BY created_at DESC LIMIT 1"),
            {"uid": user_id}
        ).fetchone()
        if current and current.signature_hash == img_hash:
            if os.path.exists(opt_path):
                os.remove(opt_path)
            return {"status": "ok", "message": "firma_ya_se_encuentra_actualizada"}

        sig_path = user_dir / f"v{next_version}{ext}"
        os.replace(opt_path, str(sig_path))

        # Update DB: Archive old signatures and insert new one
        with safe_transaction(db):
            db.execute(text("UPDATE user_signatures SET is_active = false WHERE user_id = :uid"), {"uid": user_id})
            db.execute(
                text("""
                INSERT INTO user_signatures (user_id, signature_path, signature_hash, version, is_active)
                VALUES (:uid, :path, :hash, :v, true)
                """),
                {"uid": user_id, "path": str(sig_path), "hash": img_hash, "v": next_version}
            )
            
            # Gap 8.3: Prune old versions beyond retention limit (keep last 5)
            MAX_SIGNATURE_VERSIONS = int(os.getenv("MAX_SIGNATURE_VERSIONS", "5"))
            old_versions = db.execute(
                text("""
                    SELECT id, signature_path FROM user_signatures 
                    WHERE user_id = :uid AND is_active = false
                    ORDER BY version DESC
                    OFFSET :keep
                """),
                {"uid": user_id, "keep": MAX_SIGNATURE_VERSIONS}
            ).fetchall()
            
            for old in old_versions:
                try:
                    old_path = old.signature_path
                    if old_path and os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    pass
                db.execute(text("DELETE FROM user_signatures WHERE id = :id"), {"id": old.id})

        logger.info(f"user_signature_saved: {user_id} v{next_version}")
        return {"status": "ok", "message": "firma_guardada"}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("save_signature_error")
        raise HTTPException(500, "error_al_guardar_firma")


@router.post("/user/upload-sign")
async def upload_and_sign_document(
    file: UploadFile = File(...),
    section: str = Form(...),
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Upload a PDF, sign it with the employee's stored signature, and save it in the selected section."""
    if user.get("role") != "employee":
        raise HTTPException(403, "accesso_denegado")

    section_code = (section or "").strip().upper()
    valid_sections = {"PAYROLL", "UNEMPLOYMENT", "MISC"}
    if section_code not in valid_sections:
        raise HTTPException(400, "seccion_invalida")

    filename = file.filename or "documento.pdf"
    if not filename.lower().endswith(".pdf") and file.content_type != "application/pdf":
        raise HTTPException(400, "solo_se_permiten_pdfs")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "archivo_vacio")

    signature_path = _resolve_active_signature_path(user["id"], db)
    if not signature_path:
        raise HTTPException(400, "firma_no_encontrada")

    signature_bytes = signature_path.read_bytes()

    employee_dni = user.get("dni")
    employee_cuil = user.get("cuil")
    if not employee_dni and not employee_cuil and user.get("employee_id"):
        emp_row = db.execute(
            text("SELECT dni, cuil FROM employees WHERE id = :eid"),
            {"eid": user["employee_id"]}
        ).fetchone()
        if emp_row:
            employee_dni = employee_dni or emp_row.dni
            employee_cuil = employee_cuil or emp_row.cuil

    full_name = user.get("full_name") or user.get("email") or "Empleado"
    upload_dir = STORAGE_BASE / "uploads" / str(user["organization_id"]) / user["id"]
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Use only a sanitized filename to avoid injection and traversal issues.
    clean_filename = re.sub(r'[^a-zA-Z0-9_\-\.]+', '_', filename)
    temp_input_path = upload_dir / f"{uuid.uuid4().hex}_{clean_filename}"

    try:
        with open(temp_input_path, "wb") as tmp_file:
            tmp_file.write(file_bytes)

        ctx = {
            "receipt_id": str(uuid.uuid4()),
            "organization_id": str(user["organization_id"]),
            "role": "employee",
            "receipt_pdf_path": str(temp_input_path.relative_to(STORAGE_BASE)),
            "next_status": "signed",
            "full_name": full_name,
            "cuil": employee_cuil,
            "dni": employee_dni,
            "email": user.get("email"),
            "user": user,
            "source": "custom_document",
            "original_filename": filename,
            "doc_type": section_code,
        }

        import asyncio
        loop = asyncio.get_running_loop()
        _safe_log_info(
            "custom_document.signing_start",
            extra={
                "section": section_code,
                "user_id": user.get("id"),
                "original_filename": filename,
                "source": ctx.get("source"),
                "role": ctx.get("role"),
            },
        )
        try:
            # Verification log: record which signature bytes we're about to use
            try:
                sig_hash = _compute_sha256(signature_bytes)
            except Exception:
                sig_hash = None
            _safe_log_info(
                "custom_document.signature_used",
                extra={
                    "user_id": user.get("id"),
                    "signature_sha256": sig_hash,
                    "signature_size": len(signature_bytes) if signature_bytes else 0,
                },
            )
            pdf_result = await loop.run_in_executor(
                _pdf_executor,
                DigitalSignatureEngine.process_pdf,
                ctx,
                signature_bytes,
            )
            _safe_log_info(
                "custom_document.signing_completed",
                extra={
                    "section": section_code,
                    "user_id": user.get("id"),
                    "fingerprint": pdf_result.get("fingerprint"),
                    "signature_version": pdf_result.get("signature_version"),
                    "signed_pdf_path": pdf_result.get("signed_pdf_path"),
                },
            )
        except Exception as exc:
            _safe_log_exception("document_signing_failed", extra={"section": section_code, "user_id": user.get("id"), "original_filename": filename})
            raise HTTPException(500, "error_al_firmar_documento")

        signed_path = pdf_result.get("signed_pdf_path")
        if not signed_path or not Path(signed_path).exists():
            raise HTTPException(500, "error_al_firmar_documento")

        signed_bytes = Path(signed_path).read_bytes()

        doc_status = "FIRMADO" if section_code == "UNEMPLOYMENT" else "ACTIVE"
        saved_doc = DocumentService.save_document(
            db,
            str(user["organization_id"]),
            section_code,
            signed_bytes,
            filename,
            {"id": user["id"], "email": user.get("email"), "role": user.get("role")},
            custom_metadata={
                "signed_by_employee": True,
                "signed_by_employee_at": datetime.now(timezone.utc).isoformat(),
                "signature_source": "stored_user_signature",
                "signature_hash": _compute_sha256(signature_bytes),
                "original_filename": filename,
            },
            status=doc_status,
        )

        return {
            "status": "signed",
            "document_id": saved_doc["id"],
            "doc_type": section_code,
            "signed_file_name": filename,
        }

    finally:
        try:
            if temp_input_path.exists():
                temp_input_path.unlink()
            if upload_dir.exists() and not any(upload_dir.iterdir()):
                upload_dir.rmdir()
        except Exception:
            pass


@router.get("/user/image")
async def get_user_signature_image(
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """Serve the active stored signature image for the current user."""
    user_id = user["id"]

    row = db.execute(
        text("SELECT signature_path FROM user_signatures WHERE user_id = :id AND is_active = true ORDER BY created_at DESC LIMIT 1"),
        {"id": user_id}
    ).fetchone()

    if not row or not row.signature_path:
        raise HTTPException(404, "firma_no_encontrada")

    sig_file = None
    try:
        resolved = resolve_storage_path(row.signature_path)
        sig_file = Path(resolved)
        if not sig_file.exists():
            sig_file = _resolve_signature_with_fallback(row.signature_path)
    except Exception:
        sig_file = _resolve_signature_with_fallback(row.signature_path)

    if not sig_file or not sig_file.exists():
        with safe_transaction(db):
            db.execute(
                text("UPDATE user_signatures SET is_active = false WHERE user_id = :id"),
                {"id": user_id}
            )
        raise HTTPException(404, "archivo_firma_no_encontrado")

    media_type = (
        "image/jpeg"
        if sig_file.suffix.lower() in {".jpg", ".jpeg"}
        else "image/png"
    )

    return FileResponse(
        path=str(sig_file),
        media_type=media_type,
        filename=sig_file.name,
        content_disposition_type="inline",
    )


@router.get("/receipt/{receipt_id}/image")
async def get_receipt_signature_image(
    receipt_id: str,
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    V4.1 AUDIT ENDPOINT: Serves the holographic/manuscript signature image for a specific receipt.
    Logic:
    1. Check organization access.
    2. Try binary snapshot from DB (highest integrity).
    3. Fallback to physical storage (legacy support).
    """
    # 1. Fetch metadata and check access
    from fastapi import Response
    
    # We use a broad join to ensure org and ownership
    receipt = db.execute(text("""
        SELECT r.company_id, r.user_id, r.signature_snapshot, r.file_path, r.status
        FROM receipts r
        WHERE r.id = :id AND r.is_deleted = false
    """), {"id": receipt_id}).fetchone()

    if not receipt:
        # Fallback to legacy payroll_receipts table
        receipt = db.execute(text("""
            SELECT organization_id as company_id, employee_id as user_id, NULL as signature_snapshot, receipt_pdf_path as file_path, status
            FROM payroll_receipts
            WHERE id = :id AND is_deleted = false
        """), {"id": receipt_id}).fetchone()

    if not receipt:
        raise HTTPException(404, "recibo_no_encontrado")

    # Access Control: Admins of the same org OR the employee who owns the receipt
    is_admin = user["role"] == "admin" and str(user.get("organization_id")) == str(receipt.company_id)
    is_owner = str(user["id"]) == str(receipt.user_id)
    
    if not (is_admin or is_owner):
        raise HTTPException(403, "acceso_denegado_a_evidencia_de_firma")

    # 2. FALLBACK LEVEL 1: Database Snapshot (JSONB/Binary)
    if receipt.signature_snapshot:
        logger.info(f"signature.serve_from_db_snapshot: {receipt_id}")
        return Response(
            content=receipt.signature_snapshot, 
            media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename=firma_{receipt_id}.png"}
        )

    # Phase 2 Fix: Removed fallback to user's current signature to prevent forensic desynchronization.
    # We only serve the snapshot taken at the exact moment of signing.
    logger.error(f"signature.evidence_lost: {receipt_id}")
    raise HTTPException(410, "evidencia_firma_perdida")
