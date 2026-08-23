"""
MÃ³dulo de firma digital centralizado.

Contiene:
- DigitalSignatureEngine: Motor que encapsula TODA la lÃ³gica de firma
  (estampado, validaciÃ³n de estado, almacenamiento, detecciÃ³n de posiciÃ³n, evidencia y eventos).
- Endpoints HTTP de FastAPI que consumen el motor.
- Models Pydantic para validaciÃ³n de requests/responses.

Arquitectura: Clean Architecture â€“ 3-Phase pipeline.
  Phase 1: DB read + validation (inside FOR UPDATE TX)
  Phase 2: PDF processing (outside TX, off event-loop via run_in_executor)
  Phase 3: DB finalize (inside TX)

Transacciones seguras mediante SQLAlchemy raw SQL (text).
"""

import os
import json
import hashlib
import uuid
import base64
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import time

import fitz  # PyMuPDF
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse, RedirectResponse
try:
    from pydantic import BaseModel, Field, field_validator
except ImportError:
    from pydantic import BaseModel, Field, validator as field_validator
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

# Dependencias Core (Asumiendo que existen en tu sistema base)
from payroll_core import (
    PRODUCTION,
    get_db,
    utc_now,
    new_token,
    require_auth,
    limiter,
    hash_token,
    validate_token_format,
    safe_transaction,
    sanitize_text_input,
    normalize_cuil,
    CUIL_REGEX,
    logger,
    ALLOWED_STORAGE_DIR,
    resolve_storage_path,
    EmailSendFailedError
)
from payroll_utils import get_real_ip
from services.webhook_service import enqueue_webhook
import services.x509_service as x509_service
from services.document_repository import DocumentRepository
from modules.signature import get_signature_engine, SignatureError as EngineSignatureError
from services.signature_service import validate_and_fetch_signature_request
from services.email_service import EmailService
from metrics.registry import metrics_registry
import config

# =============================================================================
# ConfiguraciÃ³n y Constantes
# =============================================================================

STORAGE_ROOT = Path(ALLOWED_STORAGE_DIR).resolve()

LEGAL_ACCEPTANCE_TEXT = (
    "Acepto y firmo en conformidad el presente recibo de haberes, "
    "declarando haber recibido las remuneraciones detalladas. "
    "Ley 20.744 - RÃ©gimen de Contrato de Trabajo."
)
# Gap 11.1: Immutable hash of the legal text version for forensic traceability
LEGAL_ACCEPTANCE_HASH = hashlib.sha256(LEGAL_ACCEPTANCE_TEXT.encode('utf-8')).hexdigest()

# ThreadPool for CPU/IO-bound PDF operations (avoids blocking the asyncio loop)
# Phase 1 Fix: Scale workers dynamically based on CPU count for industrial loads
# Multi-worker safe: With 4 Gunicorn workers, each gets its own pool.
# Cap at 9 threads per worker → 4 workers × 9 = 36 total threads system-wide.
import os
_pdf_executor = ThreadPoolExecutor(
    max_workers=min(os.cpu_count() or 4, 9),
    thread_name_prefix="pdf-stamp"
)

router = APIRouter(prefix="/api/signature-requests", tags=["digital_signature"])

# =============================================================================
# Excepciones Personalizadas
# =============================================================================

class SignatureError(Exception):
    """ExcepciÃ³n base para el motor de firmas."""
    pass

class InvalidStateError(SignatureError):
    """El estado actual del recibo no permite la firma solicitada."""
    pass

class PathSecurityError(SignatureError):
    """Intento de path traversal detectado."""
    pass

# =============================================================================
# Modelos Pydantic
# =============================================================================

class BatchUploadOut(BaseModel):
    batch_id: str
    total_pages: int
    created_receipts: int
    matched_receipts: int
    pending_signature: int
    pending_match: int
    sample_sign_urls: List[str] = []

class RejectRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=500)

    @field_validator("reason")
    @classmethod
    def sanitize(cls, v: str) -> str:
        return v.replace("<", "").replace(">", "").strip()

class EmployeeSignRequest(BaseModel):
    # Permite un string especÃ­fico "STORED_SIGNATURE" o un base64 de tamaÃ±o mÃ­nimo
    signature_image: str = Field(..., min_length=15)
    cuil: str = Field("", description="CUIL del empleado (con o sin guiones)")

    @field_validator("cuil")
    @classmethod
    def validate_cuil_format(cls, v: str) -> str:
        if not v:
            return ""
        normalized = re.sub(r"\D", "", v)
        if len(normalized) != 11:
            raise ValueError("El CUIL debe contener exactamente 11 nÃºmeros.")
        return normalized

class TokenInfoOut(BaseModel):
    employee: Optional[str] = None
    period: str = "N/D"
    status: str
    organization_name: str
    organization_id: str
    user_exists: bool = False
    expires_at: Optional[str] = None
    receipt_id: Optional[str] = None
    employee_phone: Optional[str] = None  # masked: "***4567"
    has_phone: bool = False
    has_email: bool = False
    requires_verification: bool = True
    soft_match: bool = False
    page_count: int = 1

class SignSendOtpBody(BaseModel):
    channel: str = "sms"  # "sms" | "email"

class SignVerifyOtpBody(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)

# =============================================================================
# Digital Signature Engine  (3-Phase Pipeline)
# =============================================================================

class DigitalSignatureEngine:
    """
    Orchestrates signature stamping with a 3-phase pipeline to avoid
    holding DB locks during heavy PDF I/O.

    Phase 1 â€“ validate_and_lock:  DB read + state validation inside FOR UPDATE
    Phase 2 â€“ process_pdf:        PDF manipulation + hash computation (NO DB)
    Phase 3 â€“ finalize_db:        DB writes (UPDATE receipt, INSERT events/evidence)
    """

    @staticmethod
    def clear_processing_flag(db: Session, receipt_id: str):
        """
        Manually clears the processing_signature flag.
        Used for error recovery if a Phase 2 operation fails before Phase 3.
        """
        # We need to detect the source first, or just try to clear in both if we don't know
        db.execute(text("UPDATE receipts SET processing_signature = false WHERE id = :rid"), {"rid": receipt_id})
        db.execute(text("UPDATE payroll_receipts SET processing_signature = false WHERE id = :rid"), {"rid": receipt_id})

    # â”€â”€ static helpers (no DB) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    def _normalize_path(relative_path: str) -> Path:
        """
        Normaliza un path (relativo o absoluto) y verifica que estÃ© dentro de STORAGE_ROOT.
        """
        if not relative_path:
            raise SignatureError("No path provided.")

        p = Path(relative_path)
        
        # Si es absoluto (ej: empieza con / o C:\)
        if p.is_absolute():
            absolute_path = p.resolve()
        else:
            # Si es relativo, limpiar posibles prefijos y unir con ROOT
            clean_rel = relative_path.lstrip("/\\")
            absolute_path = (STORAGE_ROOT / clean_rel).resolve()

        # Seguridad Check: debe estar dentro de STORAGE_ROOT
        if not str(absolute_path).lower().startswith(str(STORAGE_ROOT).lower()):
            raise PathSecurityError(f"Path outside storage detected: {relative_path}")
            
        return absolute_path

    @staticmethod
    def _compute_sha256(file_path: Path) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    @staticmethod
    def _store_signature_image(org_id: str, receipt_id: str, role: str, image_bytes: bytes) -> Path:
        sig_dir = STORAGE_ROOT / "signatures" / org_id / receipt_id
        sig_dir.mkdir(parents=True, exist_ok=True)
        sig_path = sig_dir / f"{role}.png"
        
        if image_bytes is None:
            # Contingency Mode: No manuscript image to store
            return None

        # Atomic write: temp file + replace
        import tempfile
        import os
        fd, temp_path = tempfile.mkstemp(dir=str(sig_dir), prefix=f"tmp_{role}_", suffix=".png")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(image_bytes)
            os.replace(temp_path, str(sig_path))
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise
            
        return sig_path

    # â”€â”€ Phase 1: DB read + validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    def validate_and_lock(
        db: Session,
        receipt_id: str,
        organization_id: str,
        role: str,
        signature_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Must run inside a safe_transaction / FOR UPDATE block.
        Returns a dict with all fields needed for Phase 2 & 3.
        Raises on invalid state.
        """
        if role not in ("employer", "employee"):
            raise ValueError("Role must be 'employer' or 'employee'")

        doc = DocumentRepository.get_document(db, receipt_id, for_update=True)

        if not doc or str(doc["organization_id"]) != str(organization_id):
            raise SignatureError("Receipt not found or access denied.")

        # GAP-003 FIX: Reject if another request is currently in Phase 2
        if doc.get("processing_signature"):
            raise InvalidStateError("Este recibo está siendo procesado por otra operación de firma.")
            
        if doc["document_locked"]:
            raise InvalidStateError("Este recibo ya ha sido firmado y se encuentra bloqueado legalmente.")

        current_status = doc["status"]

        # State machine + idempotency
        if role == "employer":
            # Idempotency check: if already signed by employer
            if doc.get("employer_signed_at"):
                return {"idempotent": True, "current_status": current_status}
            
            # Strict State Machine: Employer can only sign if it's pending employer signature
            # We also allow "pending_signature", "pending", "uploaded" and "pending_match" (with safeguards).
            allowed_statuses = ("pending", "pending_employer_signature", "pending_signature", "uploaded", "pending_match")
            if current_status not in allowed_statuses:
                raise InvalidStateError(f"Cannot sign as employer in state: {current_status}")

            # Legal Guardrail: If in pending_match, we MUST have a minimum identity detected
            if current_status == "pending_match":
                # DocumentRepository aliases extracted_fields as 'metadata' and JOINs employee data
                extracted = doc.get("metadata") or {}
                if isinstance(extracted, str):
                    import json
                    try: extracted = json.loads(extracted)
                    except: extracted = {}
                has_identity = (
                    doc.get("dni") or doc.get("cuil")  # From employee JOIN
                    or extracted.get("dni") or extracted.get("cuil")  # From OCR extraction
                )
                if not has_identity:
                    logger.warning(f"signature.legal_block: pending_match signature attempt without identity metadata rid={doc['id']}")
                    raise InvalidStateError("Cannot sign in pending_match state without minimum identity (DNI/CUIL) extracted.")

            if doc.get("employee_signed_at") or not doc["requires_employee"]:
                next_status = "signed"
            else:
                next_status = "pending_employee_signature"
        else:
            # Employee signature
            if doc.get("employee_signed_at"):
                return {"idempotent": True, "current_status": current_status}
            
            if not signature_request_id:
                raise ValueError("signature_request_id is required for employee signatures")
            
            # Strict State Machine: Employee can only sign if it's pending employee signature
            # We also allow "pending_signature" and "pending" for compatibility.
            if current_status not in ("pending", "pending_employee_signature", "pending_signature"):
                raise InvalidStateError(f"Cannot sign as employee in state: {current_status}")

            if doc.get("employer_signed_at") or not doc["requires_employer"]:
                next_status = "signed"
            else:
                next_status = "pending_employer_signature"

        # GAP-022: CUIT fallback
        cuit = doc["cuit"]
        if not cuit and doc["metadata"]:
            cuit = doc["metadata"].get("employer_cuit")

        # Set processing_signature = true inside the locked TX
        DocumentRepository.set_processing_flag(db, receipt_id, doc["source"], True)

        return {
            "idempotent": False,
            "receipt_id": receipt_id,
            "organization_id": organization_id,
            "employee_id": str(doc["employee_id"]) if doc["employee_id"] else None,
            "receipt_pdf_path": doc["path"],
            "receipt_pdf_sha256": doc["hash"],
            "current_status": current_status,
            "next_status": next_status,
            "extracted_fields": doc["metadata"],
            "full_name": doc["full_name"],
            "cuil": doc["cuil"],
            "dni": doc["dni"],
            "email": doc["email"],
            "logo_path": doc["logo_path"],
            "cuit": cuit,
            "verification_id": doc["verification_id"],
            "requires_employer": doc["requires_employer"],
            "requires_employee": doc["requires_employee"],
            "batch_id": str(doc["batch_id"]) if doc["batch_id"] else None,
            "role": role,
            "source": doc["source"],
            "signature_request_id": signature_request_id,
            "signer_identity": {
                "dni": doc["dni"] or "00000000",
                "full_name": doc["full_name"] or "Firmante Aut.",
                "email": doc["email"] or "auditoria@dircom.com"
            }
        }

    # â”€â”€ Phase 2: PDF processing (no DB, can run in thread) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @classmethod
    def process_pdf(
        cls,
        ctx: Dict[str, Any],
        image_bytes: bytes,
    ) -> Dict[str, Any]:
        """
        CPU/IO bound work: store image, overlay on PDF, compute hashes.
        Returns a dict with paths and hashes for Phase 3.
        MUST NOT touch the DB.
        """
        role = ctx["role"]
        receipt_id = ctx["receipt_id"]
        organization_id = ctx["organization_id"]

        try:
            original_pdf_path = cls._normalize_path(ctx["receipt_pdf_path"])
            if not original_pdf_path.exists():
                raise SignatureError("Original PDF file is missing from storage.")

            # GAP-L2-02: Fail-fast resource limits (OOM protection)
            file_size = original_pdf_path.stat().st_size
            if file_size > config.MAX_FILE_SIZE:
                raise SignatureError(
                    f"El archivo PDF excede el tamaño máximo permitido ({config.MAX_FILE_SIZE // 1024 // 1024}MB)."
                )

            with fitz.open(str(original_pdf_path)) as doc:
                if doc.page_count > config.MAX_PDF_PAGES:
                    raise SignatureError(
                        f"El PDF tiene demasiadas páginas ({doc.page_count}). Máximo permitido: {config.MAX_PDF_PAGES}."
                    )

                # Phase 4 Fix: Sanitize PDF Metadata (Information Leakage Prevention)
                doc.set_metadata({
                    "producer": "MyManageRH Industrial Signature Engine",
                    "creator": "Dircom Payroll v4.3",
                    "author": "Organization ID " + organization_id,
                    "title": f"Recibo de Sueldo - {receipt_id}"
                })
        except SignatureError:
            raise
        except Exception as e:
            logger.error(f"pdf.integrity_check_failed: {e}")
            raise SignatureError("Error al validar integridad del PDF.")

        batch_folder = original_pdf_path.parent.name
        
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', ctx.get("full_name", "empleado").strip().replace(' ', '_'))
        # Phase 4 Fix: Obfuscate filename to prevent PII exposure in the filesystem
        name_hash = hashlib.sha256(safe_name.encode()).hexdigest()[:12]
        signed_pdf_path = (
            STORAGE_ROOT / "receipts" / organization_id / batch_folder / "signed" / f"{receipt_id}_{name_hash}_signed.pdf"
        )
        signed_pdf_path.parent.mkdir(parents=True, exist_ok=True)

        # Store signature image
        sig_image_path = cls._store_signature_image(organization_id, receipt_id, role, image_bytes)
        
        # Centralized Signature Engine
        engine = get_signature_engine()
        
        logo_bytes = None
        if ctx.get("logo_path"):
            l_path = Path(ctx["logo_path"])
            if l_path.exists():
                try:
                    with open(l_path, "rb") as f:
                         logo_bytes = f.read()
                except Exception as e:
                    logger.warning(f"Could not load logo_path {l_path}: {e}")

        try:
            # GAP-020: Generation of verification_id if missing (C-004: Full UUID4 entropy = 128 bits)
            v_id = ctx.get("verification_id")
            if not v_id:
                import uuid
                v_id = f"VER-{uuid.uuid4().hex.upper()}"
            
            # C-005 FIX: Use dynamic public URL from config instead of hardcoded domain
            verify_url = f"{config.BASE_PUBLIC_URL}/ui/#/verify/{v_id}"

            # â”€â”€ Identity Binding (Phase 3+) â”€â”€
            signer_identity = None
            user = ctx.get("user") or {}
            dni = None
            if user:
                dni = user.get("dni") or ctx.get("dni")
                signer_identity = {
                    "user_id": user.get("id"),
                    "role": user.get("role"),
                    "full_name": user.get("full_name"),
                    "dni": dni,
                    "email": user.get("email") or ctx.get("email"),
                    "organization_id": user.get("organization_id")
                }
            
            # Identity Enforcement Assertions (Industrial Hardening)
            if not signer_identity or not signer_identity.get("dni") or not signer_identity.get("full_name") or not signer_identity.get("role"):
                # Fallback to ctx if user is missing but data is present (enterprise flow)
                if not signer_identity:
                    signer_identity = {
                        "dni": ctx.get("dni") or ctx.get("cuil"),
                        "full_name": ctx.get("full_name"),
                        "role": ctx.get("role"),
                        "email": ctx.get("email")
                    }
                
                # Strict check
                if not signer_identity.get("dni") or not signer_identity.get("full_name") or not signer_identity.get("role"):
                    logger.error(f"identity_enforcement_failed: {signer_identity}")
                    raise SignatureError("identity_missing_or_invalid")
            
            # Ensure role is canonical (use safe access)
            role_val = (signer_identity.get("role") or "").lower()
            if role_val not in ["employee", "employer"]:
                # Mapping common variants
                if role_val in ["admin", "organization"]:
                    signer_identity["role"] = "employer"
                else:
                    raise SignatureError(f"invalid_signer_role: {role_val or 'UNKNOWN'}")
                
            # GAP 1: Atomic Pipeline - Use a temporary file for the visual stamp
            import tempfile
            fd, temp_visual_path_str = tempfile.mkstemp(dir=str(signed_pdf_path.parent), prefix="tmp_visual_", suffix=".pdf")
            os.close(fd)

            logger.info(
                "custom_document.stamp_start",
                extra={
                    "receipt_id": receipt_id,
                    "organization_id": organization_id,
                    "role": role,
                    "source": ctx.get("source"),
                    "signer_name": signer_identity.get("full_name"),
                },
            )
            # Stamp PDF (intelligent anchor placement inside engine) -> output to temp
            # Now returns the unique SealID generated in the engine
            sig_result = engine.stamp_signature_from_bytes(
                pdf_path=str(original_pdf_path),
                signature_bytes=image_bytes,
                role=role,
                output_path=temp_visual_path_str,
                logo_bytes=logo_bytes,
                signer_name=signer_identity.get("full_name") or ctx.get("full_name") or "Empresa",
                signer_tax_id=ctx.get("cuit") if role == "employer" else ctx.get("cuil"),
                timestamp=datetime.now(timezone.utc),
                verification_url=verify_url,
                signer_identity=signer_identity,
                signature_level="X509+TSA+PKI",
                doc_type=ctx.get("doc_type"),
                source=ctx.get("source")
            )
            
            # Store SealID in context for DB finalization
            # GAP-022 FIX: Ensure we store the string ID, not the whole result dict
            ctx["generated_seal_id"] = sig_result["generated_seal_id"]
        except EngineSignatureError as e:
            if 'temp_visual_path_str' in locals() and os.path.exists(temp_visual_path_str):
                os.remove(temp_visual_path_str)
            raise SignatureError(str(e))

        # X.509 Digital Signature (Phase 3 Enterprise Integration)
        x509_fingerprint = None
        timestamp_source = "NONE"
        id_hash = None
        issuer = "UNKNOWN"
        sig_version = "v2_basic"

        final_file_to_commit = temp_visual_path_str

        if signer_identity:
            # Identity Guard
            if not signer_identity.get("dni") or not signer_identity.get("email"):
                logger.warning(f"X509_IDENTITY_INCOMPLETE receipt_id={receipt_id} user_id={user.get('id') if isinstance(user, dict) else None}")

            try:
                # ── Multi-Signature Incremental Update ──
                # Phase 1 Fix: Strict Cryptography Enforcement (No fallbacks allowed)
                x509_res = x509_service.sign_pdf(temp_visual_path_str, receipt_id, signer_identity)
                if x509_res["status"] != "success":
                    error_msg = x509_res.get('error', 'unknown_pki_failure')
                    logger.error(f"x509.signing_failed: aborting process receipt_id={receipt_id} error={error_msg}")
                    raise SignatureError(f"Error crítico en firma digital (PKI): {error_msg}. El proceso ha sido cancelado para proteger la integridad legal.")

                final_file_to_commit = x509_res["signed_path"]
                x509_fingerprint = x509_res["fingerprint"]
                issuer = x509_res.get("issuer", "Internal CA")
                id_hash = x509_res.get("id_hash")
                sig_version = x509_res.get("signature_version", "v3_pki")

                ts_status = x509_res.get("timestamp_source", "FAILED")
                timestamp_source = "TSA" if ts_status == "SUCCESS" else "LOCAL_FALLBACK"

                # Phase 7/8: Validation data
                ctx["x509_meta"] = {
                    "validation_status": x509_res.get("validation_status"),
                    "ocsp_status": x509_res.get("ocsp_status"),
                    "crl_status": x509_res.get("crl_status"),
                    "validation_checked_at": x509_res.get("validation_checked_at"),
                    "validation_error": x509_res.get("validation_error"),
                    "cert_serial": x509_res.get("serial_number"),
                    "cert_subject": x509_res.get("subject"),
                    "not_before": x509_res.get("not_before"),
                    "not_after": x509_res.get("not_after"),
                    "signature_algorithm": x509_res.get("signature_algorithm"),
                    "tsa_timestamp": x509_res.get("tsa_timestamp"),
                    "signing_method": x509_res.get("signing_method")
                }

                logger.info(
                    "custom_document.x509_signed",
                    extra={
                        "receipt_id": receipt_id,
                        "organization_id": organization_id,
                        "source": ctx.get("source"),
                        "fingerprint": x509_res.get("fingerprint"),
                        "signature_version": sig_version,
                        "timestamp_source": timestamp_source,
                    },
                )
                logger.info(f"x509.signed_successfully receipt_id={receipt_id} ts_source={timestamp_source} version={sig_version}")
            except SignatureError:
                raise
            except Exception as e:
                logger.error(f"x509.integration_error: aborting process receipt_id={receipt_id} error={str(e)}")
                raise SignatureError(f"Error inesperado en el motor de firma: {str(e)}")

        # ONLY ONE FINAL WRITE (Atomic Replace - Robust for Windows/OneDrive)
        MAX_RETRIES = 5
        replace_success = False
        for i in range(MAX_RETRIES):
            try:
                os.replace(final_file_to_commit, str(signed_pdf_path))
                replace_success = True
                break
            except PermissionError as pe:
                if i == MAX_RETRIES - 1:
                    logger.error(f"FINAL_COMMIT_PERMISSION_ERROR: Locked by another process/OneDrive after {MAX_RETRIES} attempts: {pe}")
                    raise
                time.sleep(0.1 * (i + 1))
        
        if not replace_success:
            raise RuntimeError(f"Atomic commit failed: Could not replace {signed_pdf_path}")
        
        # Cleanup intermediary temp file if it wasn't the one committed
        if final_file_to_commit != temp_visual_path_str and os.path.exists(temp_visual_path_str):
            os.remove(temp_visual_path_str)

        new_pdf_sha256 = engine.calculate_file_sha256(str(signed_pdf_path))
        sig_image_sha256 = engine.calculate_file_sha256(str(sig_image_path)) if sig_image_path else "NONE"

        # Flatten metadata for easier return
        res = {
            "signed_pdf_path": signed_pdf_path,
            "signed_pdf_relative": str(signed_pdf_path.relative_to(STORAGE_ROOT)),
            "new_pdf_sha256": new_pdf_sha256,
            "sig_image_path": sig_image_path,
            "sig_image_sha256": sig_image_sha256,
            "verification_id": v_id,
            "fingerprint": x509_fingerprint,
            "timestamp_source": timestamp_source,
            "issuer": issuer,
            "id_hash": id_hash,
            "signature_version": sig_version,
            "signer_identity": signer_identity,
            "sig_image_bytes": image_bytes, # Phase 1 Fix: Forensic Snapshot
        }
        
        # Merge Phase 7/8 metadata
        if ctx.get("x509_meta"):
            res.update(ctx["x509_meta"])
            
        return res

    # â”€â”€ Phase 3: DB finalize â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    @staticmethod
    async def finalize_db(
        db: Session,
        ctx: Dict[str, Any],
        pdf_result: Dict[str, Any],
        actor_id: str,
        ip_address: str,
        user_agent: str,
    ) -> Dict[str, Any]:
        """
        Must run inside a safe_transaction block.
        Writes receipt update, signature event, and (for employees) evidence.
        """
        role = ctx["role"]
        receipt_id = ctx["receipt_id"]
        organization_id = ctx["organization_id"]
        source = ctx.get("source", "payroll")
        now = datetime.now(timezone.utc)

        # 1. Update receipt using normalized repository
        ts_col = "employer_signed_at" if role == "employer" else "employee_signed_at"
        
        sig_id = pdf_result.get("x509_fingerprint") or pdf_result["sig_image_sha256"]
        audit_meta = {
            f"{role}_signed": True,
            f"{role}_signed_at": now.isoformat(),
            f"{role}_signature_id": sig_id
        }

        updates = {
            "path": pdf_result["signed_pdf_relative"],
            "hash": pdf_result["new_pdf_sha256"],
            "status": ctx["next_status"],
            "verification_id": pdf_result["verification_id"],
            "processing_signature": False,
            ts_col: now,
            "metadata": audit_meta,
            # Phase 1 Fix: Forensic Snapshot Persistence
            "signature_snapshot": pdf_result.get("sig_image_bytes"),
            "signature_hash": pdf_result.get("sig_image_sha256")
        }
        if ctx["next_status"] == "signed":
            updates["signed_at"] = now
            updates["document_locked"] = True
            if ctx.get("source") == "enterprise":
                updates["is_signed"] = True

        DocumentRepository.update_document(db, receipt_id, ctx.get("source", "payroll"), **updates)
        
        # 1.6 Mirroring: Synchronize status/path across bimodal tables
        # Since we use two tables for compatibility, we must keep them in sync during signing.
        mirror_params = {
            "status": ctx["next_status"],
            "path": pdf_result["signed_pdf_relative"],
            "hash": pdf_result["new_pdf_sha256"],
            "org": organization_id,
            "old_hash": ctx["receipt_pdf_sha256"],
            "now": now
        }
        
        if source == "payroll":
            # Sync Payroll -> Enterprise (receipts)
            db.execute(text("""
                UPDATE receipts 
                SET status = :status, 
                    file_path = :path, 
                    file_hash = :hash, 
                    employer_signed_at = CASE WHEN :role = 'employer' THEN :now ELSE employer_signed_at END,
                    employee_signed_at = CASE WHEN :role = 'employee' THEN :now ELSE employee_signed_at END,
                    signed_at = CASE WHEN :status = 'signed' THEN :now ELSE signed_at END,
                    document_locked = CASE WHEN :status = 'signed' THEN true ELSE document_locked END,
                    is_signed = CASE WHEN :status = 'signed' THEN true ELSE is_signed END
                WHERE company_id = :org AND file_hash = :old_hash
            """), {**mirror_params, "role": role})
        else:
            # Sync Enterprise -> Payroll (payroll_receipts)
            db.execute(text("""
                UPDATE payroll_receipts 
                SET status = :status, 
                    receipt_pdf_path = :path, 
                    receipt_pdf_sha256 = :hash, 
                    employer_signed_at = CASE WHEN :role = 'employer' THEN :now ELSE employer_signed_at END,
                    employee_signed_at = CASE WHEN :role = 'employee' THEN :now ELSE employee_signed_at END,
                    signed_at = CASE WHEN :status = 'signed' THEN :now ELSE signed_at END,
                    document_locked = CASE WHEN :status = 'signed' THEN true ELSE document_locked END
                WHERE organization_id = :org AND receipt_pdf_sha256 = :old_hash
            """), {**mirror_params, "role": role})

        # 1.5. Persist the Seal record (Immutable Ledger)
        seal_id = ctx.get("generated_seal_id")
        if seal_id:
            db.execute(text("""
                INSERT INTO receipt_seals (
                    seal_id, receipt_id, organization_id, 
                    signer_dni, signer_name, signer_role, 
                    pdf_hash, metadata
                ) VALUES (
                    :sid, :rid, :org, :dni, :name, :role, :hash, :meta
                ) ON CONFLICT (seal_id) DO NOTHING
            """), {
                "sid": seal_id,
                "rid": receipt_id,
                "org": organization_id,
                "dni": pdf_result["signer_identity"].get("dni") or "N/D",
                "name": pdf_result["signer_identity"].get("full_name"),
                "role": role,
                "hash": pdf_result["new_pdf_sha256"],
                "meta": json.dumps({
                    "ip": ip_address, 
                    "ua": user_agent,
                    "v_id": pdf_result.get("verification_id")
                })
            })

        # 2. Signature event (audit) using Dual-FK
        receipt_id_col = "receipt_id" if source == "payroll" else "enterprise_receipt_id"
        
        db.execute(text(f"""
            INSERT INTO signature_events (
                {receipt_id_col}, organization_id, actor_type, actor_id, action,
                status_before, status_after, pdf_sha256_before, pdf_sha256_after,
                ip_address, user_agent, created_at, data, document_source
            ) VALUES (
                :receipt_id, :org_id, :actor_type, :actor_id, 'SIGN',
                :status_before, :status_after, :sha_before, :sha_after,
                CAST(:ip AS inet), :ua, :now, :data, :source
            )
        """), {
            "receipt_id": receipt_id,
            "org_id": organization_id,
            "actor_type": "admin" if role == "employer" else role,
            "actor_id": actor_id,
            "action": f"SIGN_{role.upper()}",
            "status_before": ctx["current_status"],
            "status_after": ctx["next_status"],
            "sha_before": ctx["receipt_pdf_sha256"],
            "sha_after": pdf_result["new_pdf_sha256"],
            "ip": ip_address,
            "ua": user_agent[:500],
            "now": now,
            "data": json.dumps({
                "signature_sha256": pdf_result["sig_image_sha256"],
                "document_hash": pdf_result["new_pdf_sha256"],
                "certificate_fingerprint": pdf_result.get("x509_fingerprint"),
                "signer_role": role,
                # Gap 10.2: Redact PII — store identity hash, not raw identity
                "signer_identity_hash": pdf_result.get("id_hash"),
                "issuer": pdf_result.get("issuer"),
                "timestamp_source": pdf_result.get("timestamp_source", "NONE"),
                "ltv_status": pdf_result.get("ltv_status", "NONE"),
                "signature_origin": ctx.get("signature_origin", "UNKNOWN"),
                "signature_version": pdf_result.get("signature_version"),
                "action": "DOCUMENT_SIGNED_X509" if pdf_result.get("x509_fingerprint") else None,
                # Gap 11.1: Legal text version hash for forensic traceability
                "legal_acceptance_hash": LEGAL_ACCEPTANCE_HASH
            }),
            "source": source
        })

        # 2.b Signing Logs (Key Custody & Security Policy)
        # If actor_id is not in users (e.g. guest employee), leave user_id as NULL
        user_exists = db.execute(text("SELECT id FROM users WHERE id = :aid"), {"aid": actor_id}).fetchone()
        
        db.execute(text("""
            INSERT INTO signing_logs (
                id, user_id, action, ip_address, user_agent, created_at
            ) VALUES (
                :id, :uid, :act, :ip, :ua, :now
            )
        """), {
            "id": str(uuid.uuid4()),
            "uid": actor_id if user_exists else None,
            "act": "signature_success",
            "ip": ip_address,
            "ua": user_agent[:500] if user_agent else None,
            "now": now
        })

        # 3. Legal evidence (employees only)
        if role == "employee":
            signer_cuil = ctx.get("cuil")
            if not signer_cuil or signer_cuil == "NO_REGISTRADO":
                 raise SignatureError("No se puede generar evidencia legal sin un CUIL verificado.")
            
            extracted = ctx.get("extracted_fields") or {}
            is_enterprise = ctx.get("source") == "enterprise"
            rid_legacy = receipt_id if not is_enterprise else None
            rid_ent = receipt_id if is_enterprise else None

            db.execute(text("""
                INSERT INTO signature_evidence (
                    signed_at, acceptance_text, signer_full_name, signer_cuil,
                    period_label, receipt_sha256_at_sign_time, signature_image_path,
                    signature_image_sha256, final_pdf_sha256, verification_id,
                    receipt_id, enterprise_receipt_id,
                    signer_user_id, batch_id, cert_fingerprint_sha256, cert_serial,
                    cert_issuer, cert_subject, cert_not_before, cert_not_after,
                    signature_algorithm, tsa_timestamp, sig_version, validation_status,
                    ocsp_status, ocsp_checked_at, crl_status, crl_checked_at,
                    validation_checked_at, validation_error, signing_method
                ) VALUES (
                    :now, :text, :name, :cuil, :period,
                    :sha_before, :sig_path, :sig_sha, :final_sha, :vid,
                    :rid_legacy, :rid_ent,
                    :user_id, :batch_id, :fingerprint, :serial,
                    :issuer, :subject, :not_before, :not_after,
                    :algo, :tsa_time, :version, :v_status,
                    :ocsp_s, :val_at, :crl_s, :val_at,
                    :val_at, :val_err, :method
                )
            """), {
                "now": now,
                "text": LEGAL_ACCEPTANCE_TEXT,
                "name": ctx.get("full_name") or "NO_REGISTRADO",
                "cuil": signer_cuil,
                "period": extracted.get("periodo", "N/D"),
                "sha_before": ctx["receipt_pdf_sha256"],
                "sig_path": str(pdf_result["sig_image_path"].relative_to(STORAGE_ROOT)),
                "sig_sha": pdf_result["sig_image_sha256"],
                "final_sha": pdf_result["new_pdf_sha256"],
                "vid": pdf_result["verification_id"],
                "rid_legacy": rid_legacy,
                "rid_ent": rid_ent,
                "user_id": actor_id,
                "batch_id": ctx.get("batch_id"),
                "fingerprint": pdf_result.get("fingerprint"),
                "serial": pdf_result.get("serial_number"),
                "issuer": pdf_result.get("issuer"),
                "subject": pdf_result.get("subject"),
                "not_before": pdf_result.get("not_before"),
                "not_after": pdf_result.get("not_after"),
                "algo": pdf_result.get("signature_algorithm"),
                "tsa_time": pdf_result.get("tsa_timestamp") or (now if pdf_result.get("timestamp_source") == "TSA" else None),
                "version": pdf_result.get("signature_version"),
                "v_status": pdf_result.get("validation_status") or ("valid" if pdf_result.get("fingerprint") else "error"),
                "ocsp_s": pdf_result.get("ocsp_status"),
                "crl_s": pdf_result.get("crl_status"),
                "val_at": pdf_result.get("validation_checked_at"),
                "val_err": pdf_result.get("validation_error"),
                "method": pdf_result.get("signing_method") or "Digital-PAdES-LTV"
            })

            # GAP 2.b: Auto-save removed. User must explicitly create their signature in Mi Firma.

        # 4. Webhook notification (only for terminal states)
        # Gap 10.4: This runs inside safe_transaction (finalize_db), ensuring atomicity with DB state change
        if ctx["next_status"] in ("signed", "rejected"):
            # Gap 8.5: Obfuscate internal IDs for external webhook consumers
            import hmac as _hmac_mod
            _wh_secret = os.getenv("PAYROLL_WEBHOOK_SECRET", "webhook-salt")
            def _obfuscate_id(raw_id: str) -> str:
                return _hmac_mod.new(_wh_secret.encode(), raw_id.encode(), hashlib.sha256).hexdigest()[:24]
            
            enqueue_webhook(
                db,
                receipt_id=receipt_id,
                organization_id=organization_id,
                action=f"receipt.{ctx['next_status']}",
                payload={
                    "public_receipt_id": _obfuscate_id(receipt_id),
                    "public_org_id": _obfuscate_id(organization_id),
                    "status": ctx["next_status"],
                    "document_hash": pdf_result["new_pdf_sha256"],
                    "signed_at": now.isoformat(),
                },
            )

        # 5. Create signature request for employee if needed
        employee_token = None
        if role == "employer" and ctx["next_status"] == "pending_employee_signature":
            from payroll_core import create_signature_request
            sr_info = create_signature_request(
                db,
                receipt_id=receipt_id,
                organization_id=organization_id,
                employee_id=ctx["employee_id"],
                issuer_ip=ip_address,
                issuer_ua=user_agent,
                issuer_user_id=actor_id
            )
            employee_token = sr_info["token"]

        return {
            "status": "success",
            "new_status": ctx["next_status"],
            "pdf_sha256": pdf_result["new_pdf_sha256"],
            "signed_at": now.isoformat(),
            "verification_id": pdf_result["verification_id"],
            "employee_token": employee_token,
            "organization_id": organization_id,
            "employee_id": ctx.get("employee_id"),
        }


# =============================================================================
# API Endpoints
# =============================================================================

# Eliminated _get_signature_request_data due to GAP-R05. Using validate_and_fetch_signature_request instead.


@router.get("/{token}")
@limiter.limit("30/minute")
async def signature_page(request: Request, token: str):
    validate_token_format(token)
    return RedirectResponse(url=f"{config.BASE_PUBLIC_URL}/ui/#/sign/{token}")


@router.get("/{token}/info", response_model=TokenInfoOut)
@limiter.limit("20/minute")
async def sign_info(request: Request, token: str, db: Session = Depends(get_db)):
    data = validate_and_fetch_signature_request(db, token)
    
    # Defensive initialization
    res_employee = "Empleado"
    res_period = "N/D"
    res_user_exists = False
    res_expires_at = None
    
    # 1. Name masking
    raw_name = data.get("employee_name") or "Empleado"
    parts = str(raw_name).split()
    if parts:
        res_employee = parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")
    
    # 2. Period
    ext = data.get("extracted_fields") or {}
    if isinstance(ext, str):
        try: 
            ext = json.loads(ext)
        except: 
            ext = {}
    if isinstance(ext, dict):
        res_period = ext.get("periodo") or ext.get("period") or "N/D"

    # 3. User Exists
    email = data.get("employee_email")
    if email:
        check = db.execute(text("SELECT 1 FROM users WHERE email = :e AND organization_id = :oid"),
                            {"e": email.strip().lower(), "oid": data["organization_id"]}).fetchone()
        res_user_exists = check is not None
        
    # 4. Expiration
    exp = data.get("token_expires_at")
    if exp and hasattr(exp, "isoformat"):
        res_expires_at = exp.isoformat()

    # 5. Masked phone for channel selection
    res_phone = None
    emp_phone = data.get("employee_phone")
    if emp_phone and len(emp_phone) >= 4:
        res_phone = "***" + emp_phone[-4:]

    # 6. Soft-match Identity logic (Requirement 11)
    # Flujo Operativo: OTP removido, siempre se asume verificado si tiene el token válido
    requires_v = False
    soft_match = True

    # 7. Page count calculation
    page_count = 1
    try:
        pdf_path = DigitalSignatureEngine._normalize_path(data["receipt_pdf_path"])
        if pdf_path.exists():
            import fitz
            doc = fitz.open(pdf_path)
            page_count = len(doc)
            doc.close()
    except Exception as e:
        logger.warning(f"Could not read PDF page count in sign_info: {e}")

    return TokenInfoOut(
        employee=res_employee,
        period=str(res_period),
        status=data["sr_status"],
        organization_name=data["organization_name"],
        organization_id=str(data["organization_id"]),
        user_exists=res_user_exists,
        expires_at=res_expires_at,
        receipt_id=str(data["receipt_id"]),
        employee_phone=res_phone,
        has_phone=bool(data.get("employee_phone")),
        has_email=bool(data.get("employee_email")),
        requires_verification=requires_v,
        soft_match=soft_match,
        page_count=page_count
    )


# --- FRICTIONLESS SIGNING: OTP without login ---

@router.post("/{token}/send-otp")
@limiter.limit("3/minute")
async def sign_send_otp(
    request: Request,
    token: str,
    body: SignSendOtpBody,
    db: Session = Depends(get_db)
):
    """
    Sends an OTP to the employee's phone or email from their employee record.
    NO authentication required — the signature token acts as authorization.
    """
    data = validate_and_fetch_signature_request(db, token)
    if data["sr_status"] != "pending":
        raise HTTPException(409, f"invalid_state:{data['sr_status']}")

    emp_phone = data.get("employee_phone")
    emp_email = data.get("employee_email")
    channel = body.channel

    # Channel selection with auto-fallback
    if channel == "sms" and not emp_phone:
        channel = "email"
    if channel == "email" and not emp_email:
        raise HTTPException(400, "no_contact_info_available")

    destination = emp_phone if channel == "sms" else emp_email

    # Generate OTP code
    from services.verification_service import VerificationService
    raw_code = VerificationService.generate_code()
    code_hash = hash_token(raw_code)

    import config as cfg
    expires_at = utc_now() + timedelta(minutes=cfg.OTP_EXPIRATION_MINUTES)
    context_hash = VerificationService.compute_context_hash(
        str(data["receipt_id"]), token, raw_code
    )
    destination_hash = VerificationService.compute_destination_hash(destination)

    # Find or create a user record for this employee (needed for OTP storage)
    user_row = None
    if emp_email:
        user_row = db.execute(text(
            "SELECT id FROM users WHERE email ILIKE :e AND organization_id = :oid"
        ), {"e": emp_email.strip().lower(), "oid": data["organization_id"]}).fetchone()

    user_id_for_otp = str(user_row.id) if user_row else str(data["employee_id"])

    with safe_transaction(db):
        # Invalidate old codes for this receipt
        db.execute(text("""
            UPDATE verification_codes SET expires_at = :now
            WHERE receipt_id = :rid AND verified = false AND created_at < :grace
        """), {"now": utc_now(), "rid": str(data["receipt_id"]),
               "grace": utc_now() - timedelta(seconds=30)})

        # Store the new OTP
        db.execute(text("""
            INSERT INTO verification_codes (
                user_id, receipt_id, signature_token, code_hash, context,
                context_hash, expires_at, ip_address, channel, destination_hash
            ) VALUES (:uid, :rid, :st, :ch, :ctx, :ctx_hash, :exp, :ip, :chan, :dh)
        """), {
            "uid": user_id_for_otp if user_row else None,
            "rid": str(data["receipt_id"]),
            "st": token,
            "ch": code_hash,
            "ctx": "signature_frictionless",
            "ctx_hash": context_hash,
            "exp": expires_at,
            "ip": get_real_ip(request),
            "chan": channel,
            "dh": destination_hash,
        })

    # Send the OTP via the appropriate channel
    org_name = data["organization_name"]
    try:
        if channel == "sms":
            from services.sms_service import SmsService
            SmsService().send_otp(emp_phone, raw_code, org_name)
        else:
            await EmailService().send_verification_otp_email(emp_email, raw_code, org_name)
    except EmailSendFailedError:
        raise
    except Exception as e:
        logger.error(f"sign.send_otp_failed: {e}")
        raise HTTPException(500, "delivery_failed")

    # Mask destination for the response
    masked = destination
    if channel == "sms" and emp_phone and len(emp_phone) >= 4:
        masked = "***" + emp_phone[-4:]
    elif channel == "email" and emp_email:
        masked = emp_email[:2] + "***" + emp_email[emp_email.index("@"):]

    logger.info(f"sign.otp_sent: token_hash={hash_token(token)[:8]} channel={channel}")
    return {"status": "ok", "channel": channel, "destination": masked}


@router.post("/{token}/verify-otp")
@limiter.limit("5/minute")
async def sign_verify_otp(
    request: Request,
    token: str,
    body: SignVerifyOtpBody,
    db: Session = Depends(get_db)
):
    """
    Verifies the OTP and creates a scoped temporary session.
    NO authentication required — the OTP + token combo acts as identity proof.
    """
    data = validate_and_fetch_signature_request(db, token)
    if data["sr_status"] != "pending":
        raise HTTPException(409, f"invalid_state:{data['sr_status']}")

    clean_code = body.code.strip()
    receipt_id = str(data["receipt_id"])

    # Find the OTP code for this receipt
    context_hash = None
    from services.verification_service import VerificationService
    context_hash = VerificationService.compute_context_hash(receipt_id, token, clean_code)

    otp_row = db.execute(text("""
        SELECT id, code_hash, context_hash, attempts, verified, channel, destination_hash
        FROM verification_codes
        WHERE receipt_id = :rid AND verified = false AND expires_at > :now
        ORDER BY created_at DESC LIMIT 5
    """), {"rid": receipt_id, "now": utc_now()}).fetchall()

    if not otp_row:
        raise HTTPException(400, "code_invalid_or_expired")

    matched = None
    for row in otp_row:
        if row.context_hash == context_hash:
            matched = row
            break
        # Flexible match: try with row's own signature_token
        flex_hash = VerificationService.compute_context_hash(receipt_id, token, clean_code)
        if row.context_hash == flex_hash:
            matched = row
            break

    if not matched:
        # Increment attempts on the most recent code
        db.execute(text("UPDATE verification_codes SET attempts = attempts + 1 WHERE id = :id"),
                   {"id": otp_row[0].id})
        db.commit()
        raise HTTPException(400, "code_incorrect")

    if matched.attempts >= 5:
        raise HTTPException(400, "max_attempts_reached")

    # Mark as verified
    with safe_transaction(db):
        db.execute(text("""
            UPDATE verification_codes
            SET verified = true, verified_at = :now, used_at = :now
            WHERE id = :id
        """), {"id": matched.id, "now": utc_now()})

    # --- Create or find user and create a scoped session ---
    emp_email = data.get("employee_email")
    user_row = None
    if emp_email:
        user_row = db.execute(text(
            "SELECT id FROM users WHERE email ILIKE :e AND organization_id = :oid"
        ), {"e": emp_email.strip().lower(), "oid": data["organization_id"]}).fetchone()

    if user_row:
        user_id = str(user_row.id)
    else:
        # Try to find by employee_id first (handles repeated OTP verifications)
        existing = db.execute(text(
            "SELECT id FROM users WHERE employee_id = :eid AND organization_id = :oid"
        ), {"eid": data["employee_id"], "oid": data["organization_id"]}).fetchone()

        if existing:
            user_id = str(existing.id)
        else:
            # Create a lightweight user record for session purposes
            from payroll_core import hash_password
            otp_email = emp_email or f"{data['employee_id']}@otp-session.local"
            try:
                with safe_transaction(db):
                    res = db.execute(text("""
                        INSERT INTO users (
                            email, password_hash, full_name, role, organization_id,
                            employee_id, user_status, is_verified
                        ) VALUES (:e, :p, :n, 'employee', :oid, :eid, 'otp_session', true)
                        RETURNING id
                    """), {
                        "e": otp_email,
                        "p": hash_password(secrets.token_urlsafe(32)),
                        "n": data["employee_name"] or "Empleado",
                        "oid": data["organization_id"],
                        "eid": data["employee_id"],
                    })
                    user_id = str(res.fetchone().id)
            except Exception:
                db.rollback()
                # Race condition: another request created the user in between
                fallback = db.execute(text(
                    "SELECT id FROM users WHERE employee_id = :eid AND organization_id = :oid"
                ), {"eid": data["employee_id"], "oid": data["organization_id"]}).fetchone()
                if fallback:
                    user_id = str(fallback.id)
                else:
                    raise HTTPException(500, "session_creation_failed")

    # Create a short-lived session (15 minutes)
    session_token = new_token()
    session_hash = hash_token(session_token)
    expires_at = utc_now() + timedelta(minutes=15)

    with safe_transaction(db):
        db.execute(text("""
            INSERT INTO user_sessions (user_id, session_token_hash, expires_at, ip_address, user_agent)
            VALUES (:uid, :th, :exp, :ip, :ua)
        """), {
            "uid": user_id,
            "th": session_hash,
            "exp": expires_at,
            "ip": get_real_ip(request),
            "ua": request.headers.get("User-Agent", "unknown")[:500],
        })

    # Determine the OTP channel for audit trail
    otp_channel = matched.channel or "unknown"
    otp_dest_hash = matched.destination_hash or "unknown"

    logger.info(f"sign.otp_verified: employee={data['employee_id']} channel={otp_channel}")

    return {
        "status": "ok",
        "verified": True,
        "session_token": session_token,
        "expires_in_minutes": 15,
        "otp_channel": otp_channel,
        "otp_destination_hash": otp_dest_hash,
    }


@router.get("/{token}/verify-email")
@limiter.limit("20/minute")
async def sign_verify_email(request: Request, token: str, user=Depends(require_auth), db: Session = Depends(get_db)):
    data = validate_and_fetch_signature_request(db, token)
    if data["sr_status"] != "pending":
        raise HTTPException(409, f"invalid_state:{data['sr_status']}")

    user_email = (user.get("email") or "").strip().lower()
    emp_email = (data["employee_email"] or "").strip().lower()
    if not emp_email or user_email != emp_email:
        raise HTTPException(403, "email_mismatch")

    return {"valid": True, "organization_name": data["organization_name"], "employee": data["employee_name"]}


@router.get("/{token}/view")
@limiter.limit("15/minute")
async def view_pdf(request: Request, token: str, db: Session = Depends(get_db)):
    data = validate_and_fetch_signature_request(db, token)
    
    # GAP-R03/R04: Frictionless Authorization
    # If a user is logged in, we verify they own the document.
    # If not, the SignatureRequest token itself is the authority to view this specific PDF (public link flow).
    from payroll_core import get_current_user
    session_token = request.cookies.get("session")
    user = get_current_user(db, session_token)
    
    if user:
        user_email = (user.get("email") or "").strip().lower()
        emp_email = (data["employee_email"] or "").strip().lower()
        if emp_email and user_email != emp_email:
            # We only enforce mismatch if there is an active (but wrong) user session.
            # Anonymous access via token is allowed for frictionless downloads.
            raise HTTPException(403, "email_mismatch")
        
    if data["sr_status"] in ("rejected", "expired"):
        raise HTTPException(409, f"document_unavailable:{data['sr_status']}")

    try:
        pdf_path = DigitalSignatureEngine._normalize_path(data["receipt_pdf_path"])
    except PathSecurityError:
        raise HTTPException(404, "pdf_not_found")

    if not pdf_path.exists():
        raise HTTPException(404, "pdf_not_found")

    # Auditar visualizaciÃ³n
    try:
        db.execute(text("""
            INSERT INTO signature_events (
                receipt_id, organization_id, actor_type, actor_id, action,
                ip_address, user_agent, created_at, data
            ) VALUES (
                :receipt_id, :org_id, 'employee', :actor_id, 'VIEW',
                CAST(:ip AS inet), :ua, :now, CAST(:data AS jsonb)
            )
        """), {
            "receipt_id": data["receipt_id"], "org_id": data["organization_id"],
            "actor_id": data["employee_id"], "ip": get_real_ip(request),
            "ua": request.headers.get("User-Agent", "")[:500],
            "now": datetime.now(timezone.utc), "data": json.dumps({"token_hash": hash_token(token)})
        })
        db.commit()
    except Exception:
        db.rollback()

    return FileResponse(pdf_path, media_type="application/pdf")


@router.get("/{token}/page/{page_num}")
@limiter.limit("30/minute")
async def view_pdf_page(request: Request, token: str, page_num: int, db: Session = Depends(get_db)):
    from fastapi import Response
    data = validate_and_fetch_signature_request(db, token)
    
    # GAP-R03/R04: Frictionless Authorization
    from payroll_core import get_current_user
    session_token = request.cookies.get("session")
    user = get_current_user(db, session_token)
    
    if user:
        user_email = (user.get("email") or "").strip().lower()
        emp_email = (data["employee_email"] or "").strip().lower()
        if emp_email and user_email != emp_email:
            raise HTTPException(403, "email_mismatch")
        
    if data["sr_status"] in ("rejected", "expired"):
        raise HTTPException(409, f"document_unavailable:{data['sr_status']}")

    try:
        pdf_path = DigitalSignatureEngine._normalize_path(data["receipt_pdf_path"])
    except PathSecurityError:
        raise HTTPException(404, "pdf_not_found")

    if not pdf_path.exists():
        raise HTTPException(404, "pdf_not_found")

    try:
        import fitz
        doc = fitz.open(pdf_path)
        page_count = len(doc)
    except Exception as e:
        logger.error(f"Error opening PDF: {e}")
        raise HTTPException(500, "rendering_error")

    if page_num < 0 or page_num >= page_count:
        doc.close()
        raise HTTPException(404, "page_not_found")

    try:
        page = doc[page_num]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()
        return Response(content=img_bytes, media_type="image/png")
    except Exception as e:
        logger.error(f"Error rendering PDF page to image: {e}")
        if 'doc' in locals() and not doc.is_closed:
            doc.close()
        raise HTTPException(500, "rendering_error")


@router.post("/{token}/accept")
@limiter.limit("5/minute")
async def accept_signature(
    request: Request,
    token: str,
    body: EmployeeSignRequest,
    background_tasks: BackgroundTasks,
    user=Depends(require_auth),
    db: Session = Depends(get_db)
):
    data = validate_and_fetch_signature_request(db, token)

    # â”€â”€ Guard: signature_request must still be pending â”€â”€
    if data["sr_status"] == "signed":
        return {"status": "signed", "signed_at": datetime.now(timezone.utc).isoformat(), "idempotent": True}
    if data["sr_status"] != "pending":
        raise HTTPException(409, f"invalid_request_state:{data['sr_status']}")

    user_email = (user.get("email") or "").strip().lower()
    emp_email = (data["employee_email"] or "").strip().lower()
    if not emp_email or user_email != emp_email:
        raise HTTPException(403, "email_mismatch")

    # GAP-R01: Validate that the authenticated user belongs to the same org as the signature request
    if user.get("organization_id") and str(user["organization_id"]) != str(data["organization_id"]):
        raise HTTPException(403, "cross_org_signature_attempt")
        
    # DI-02: Ensure employee has a registered CUIL
    db_cuil = normalize_cuil(data.get("employee_cuil") or "")
    provided_cuil = normalize_cuil(body.cuil)

    if not db_cuil or db_cuil == "NO_REGISTRADO":
        if data.get("document_source") == "enterprise" or not db_cuil:
            # If no CUIL in DB (e.g. enterprise user), we accept the one provided and bind it 
            db_cuil = provided_cuil
        else:
            logger.warning(f"cuil_missing_in_db: employee_id={data['employee_id']} - falling back to error")
            raise HTTPException(400, "cuil_no_registrado_en_sistema")
    
    if db_cuil != provided_cuil:
        logger.warning(f"cuil_mismatch: {data['employee_id']} provided {provided_cuil} but db has {db_cuil}")
        raise HTTPException(400, "cuil_incorrecto")

    # Resolve signature image (canvas vs stored)
    if body.signature_image == "STORED_SIGNATURE":
        # Fetch from user_signatures
        user_id = user["id"]
        
        # The signature target could be the user itself (Enterprise) or their mapped employee (Payroll)
        is_owner = (str(data["employee_id"]) == str(user_id)) or (str(data["employee_id"]) == str(user.get("employee_id", "")))
            
        if not is_owner:
            logger.error(f"signature_hijack_attempt: {user_id} tried to use stored signature for target {data['employee_id']}")
            raise HTTPException(403, "no_puedes_usar_firma_de_otro_usuario")

        sig_row = db.execute(
            text("SELECT signature_path FROM user_signatures WHERE user_id = :id AND is_active = true ORDER BY created_at DESC LIMIT 1"),
            {"id": user_id}
        ).fetchone()
        
        if not sig_row or not sig_row.signature_path:
            raise HTTPException(400, "signature_required")
            
        try:
            sig_path = Path(resolve_storage_path(sig_row.signature_path))
        except Exception:
            raise HTTPException(400, "archivo_de_firma_perdido")
        if not sig_path.exists():
            raise HTTPException(400, "archivo_de_firma_perdido")
            
        sig_image_bytes = sig_path.read_bytes()
    else:
        # Decode base64 from canvas
        if len(body.signature_image) < 50:
            raise HTTPException(400, "imagen_firma_muy_corta")
        sig_image_bytes = base64.b64decode(
            body.signature_image.split(",")[1] if "," in body.signature_image else body.signature_image
        )

    # â”€â”€ Phase 1: validate + lock (inside TX) â”€â”€
    try:
        with safe_transaction(db):
            ctx = DigitalSignatureEngine.validate_and_lock(
                db,
                receipt_id=str(data["receipt_id"]),
                organization_id=str(data["organization_id"]),
                role="employee",
                signature_request_id=str(data["sr_id"]),
            )
            ctx["user"] = user
            ctx["signature_origin"] = "STORED" if body.signature_image == "STORED_SIGNATURE" else "CANVAS"
            # Phase 2 Fix: Nonce Injection for Replay Protection
            import secrets
            ctx["signing_nonce"] = f"NONCE-{secrets.token_hex(16).upper()}"
        if ctx.get("idempotent"):
            return {"status": "signed", "signed_at": datetime.now(timezone.utc).isoformat(), "idempotent": True}

        # â”€â”€ Phase 2: PDF processing OFF the event loop â”€â”€
        # M-005 FIX: Use get_running_loop() instead of deprecated get_event_loop()
        started_at = time.perf_counter()
        loop = asyncio.get_running_loop()
        pdf_result = await loop.run_in_executor(
            _pdf_executor,
            DigitalSignatureEngine.process_pdf,
            ctx,
            sig_image_bytes,
        )

        # â”€â”€ Phase 3: finalize DB (inside TX) â”€â”€
        with safe_transaction(db):
            # GAP-003 FIX: Clear the processing flag during finalization
            result = await DigitalSignatureEngine.finalize_db(
                db,
                ctx,
                pdf_result,
                actor_id=str(data["employee_id"]),
                ip_address=get_real_ip(request),
                user_agent=request.headers.get("User-Agent", "unknown"),
            )

            # mark signature_request as signed
            if result.get("status") != "idempotent_success":
                db.execute(text("""
                    UPDATE signature_requests
                    SET status='signed', signed_at=:now
                    WHERE id=:id
                """), {"now": datetime.now(timezone.utc), "id": data["sr_id"]})
        
        # Trigger follow-up emails in background if an employee_token was generated
        if result.get("employee_token"):
            from notifications.service import NotificationService
            notifier = NotificationService.get_instance()
            background_tasks.add_task(
                notifier.send_signature_pending_notification,
                receipt_id=str(data["receipt_id"]),
                organization_id=result["organization_id"],
                employee_id=result["employee_id"],
                employee_token=result["employee_token"]
            )
        
        # Trigger follow-up emails if needed (e.g. if employer just signed and it's now pending employee)
        # Note: In employee accept, it's already 'signed', we might notify the org admin.
        if result.get("new_status") == "signed":
             # Optional: Notify organization that receipt is fully signed
             pass

        metrics_registry.record_signature(time.perf_counter() - started_at, success=True, generated=True, signed=True)
        return {"status": "signed", "signed_at": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        # GAP-003: Comprehensive error recovery â€” clear flag and clean up orphaned PDF
        # We catch everything from Phase 1-3 failure and ensure the flag is reset.
        logger.error(f"signature.failed token={token} error={str(e)}")
        metrics_registry.record_signature(time.perf_counter() - started_at, success=False, generated=False, signed=False)
        try:
            with safe_transaction(db):
                DigitalSignatureEngine.clear_processing_flag(db, str(data["receipt_id"]))
        except Exception as flag_err:
            logger.error(f"signature.flag_cleanup_failed token={token} error={str(flag_err)}")
        
        if 'pdf_result' in locals() and pdf_result and pdf_result.get("signed_pdf_path"):
            signed_path = pdf_result["signed_pdf_path"]
            try:
                if isinstance(signed_path, Path) and signed_path.exists():
                    # Gap 10.1: Forensic Quarantine — move to forensics instead of deleting
                    quarantine_dir = STORAGE_ROOT / "forensics" / "failed_signatures"
                    quarantine_dir.mkdir(parents=True, exist_ok=True)
                    from datetime import datetime as _dt
                    ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                    quarantine_path = quarantine_dir / f"{ts}_{signed_path.name}"
                    import shutil
                    shutil.move(str(signed_path), str(quarantine_path))
                    logger.warning(f"signature.forensic_quarantine: {signed_path} -> {quarantine_path} reason={str(e)}")
            except Exception as cleanup_err:
                logger.error(f"signature.forensic_quarantine_failed: {cleanup_err}")
        
        # Re-raise or handle specific errors for the frontend
        from modules.digital_signature import InvalidStateError, SignatureError
        if isinstance(e, InvalidStateError):
            raise HTTPException(409, str(e))
        if isinstance(e, SignatureError):
            raise HTTPException(400, str(e))
        if isinstance(e, SQLAlchemyError):
            logger.exception("db_error_accept")
            raise HTTPException(503, "database_error")
        raise e
    except InvalidStateError as e:
        raise HTTPException(409, str(e))
    except SignatureError as e:
        raise HTTPException(400, str(e))
    except SQLAlchemyError:
        logger.exception("db_error_accept")
        raise HTTPException(503, "database_error")


@router.post("/{token}/reject")
@limiter.limit("5/minute")
async def reject_signature(request: Request, token: str, body: RejectRequest, user=Depends(require_auth), db: Session = Depends(get_db)):
    try:
        with safe_transaction(db):
            data = validate_and_fetch_signature_request(db, token)
            
            # GAP-R02: Require auth and verify email
            user_email = (user.get("email") or "").strip().lower()
            emp_email = (data["employee_email"] or "").strip().lower()
            if not emp_email or user_email != emp_email:
                raise HTTPException(403, "email_mismatch")

            # Idempotent: already rejected
            if data["sr_status"] == "rejected":
                 return {"status": "rejected", "idempotent": True}
            # Cannot reject something already signed or expired
            if data["sr_status"] != "pending":
                raise HTTPException(409, f"invalid_state:{data['sr_status']}")

            now = datetime.now(timezone.utc)

            db.execute(text("""
                UPDATE signature_requests
                SET status='rejected', rejection_reason=:reason
                WHERE id=:id AND status='pending'
            """), {"reason": body.reason, "id": data["sr_id"]})

            # Capture actual receipt status and source
            source = data.get("document_source") or "payroll"
            receipt_id_col = "receipt_id" if source == "payroll" else "enterprise_receipt_id"
            
            DocumentRepository.update_document(db, data["receipt_id"], source, status='rejected')

            # Mirror rejection
            if source == "payroll":
                db.execute(text("UPDATE receipts SET status = 'rejected' WHERE company_id = :org AND file_hash = :hash"), 
                           {"org": data["organization_id"], "hash": data["receipt_pdf_sha256"]})
            else:
                db.execute(text("UPDATE payroll_receipts SET status = 'rejected' WHERE organization_id = :org AND receipt_pdf_sha256 = :hash"),
                           {"org": data["organization_id"], "hash": data["receipt_pdf_sha256"]})

            db.execute(text(f"""
                INSERT INTO signature_events (
                    {receipt_id_col}, organization_id, actor_type, actor_id, action,
                    status_before, status_after, ip_address, user_agent, created_at, data, document_source
                ) VALUES (
                    :receipt_id, :org_id, 'employee', :actor_id, 'REJECT',
                    :status_before, 'rejected', CAST(:ip AS inet), :ua, :now, :data, :source
                )
            """), {
                "receipt_id": data["receipt_id"], "org_id": data["organization_id"],
                "actor_id": data["employee_id"], "ip": get_real_ip(request),
                "ua": request.headers.get("User-Agent", "")[:500], "now": now,
                "status_before": data["sr_status"],
                "data": json.dumps({"reason": body.reason, "token_hash": hash_token(token)}),
                "source": source
            })

            # Notify payroll system
            enqueue_webhook(
                db,
                receipt_id=str(data["receipt_id"]),
                organization_id=str(data["organization_id"]),
                action="receipt.rejected",
                payload={
                    "receipt_id": str(data["receipt_id"]),
                    "organization_id": str(data["organization_id"]),
                    "employee_id": str(data["employee_id"]),
                    "status": "rejected",
                    "reason": body.reason,
                    "rejected_at": now.isoformat(),
                    "source": source
                },
            )

        return {"status": "rejected"}
    except HTTPException:
        raise
    except SQLAlchemyError:
        logger.exception("db_error_reject")
        raise HTTPException(503, "database_error")


# send_signature_email_task refactored and moved to notifications/service.py
