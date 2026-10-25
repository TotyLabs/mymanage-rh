import hashlib
import html
import json
import os
import re
import secrets
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

import config
from payroll_core import (
    ALLOWED_STORAGE_DIR,
    get_db,
    get_real_ip,
    hash_token,
    audit,
    logger,
    normalize_cuil,
    require_admin,
    require_auth,
    safe_transaction,
    validate_email_format,
)
from services.encryption_service import (
    EncryptionService,
    get_encryption_service,
)
from services.email_service import EmailService

router = APIRouter(prefix="/api/employee-legajos", tags=["employee-legajo-signatures"])
STORAGE_ROOT = Path(ALLOWED_STORAGE_DIR).resolve()
TOKEN_TTL = timedelta(days=7)


class EmployeeLegajoSignatureBody(BaseModel):
    cuil: str = Field(min_length=1, max_length=32)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_storage_path(raw_path: str) -> Path:
    path = Path(raw_path).resolve()
    try:
        path.relative_to(STORAGE_ROOT)
    except ValueError as exc:
        raise HTTPException(404, "documento_no_encontrado") from exc
    return path


def _lookup_legajo(db: Session, identifier: str):
    token_hash = hash_token(identifier)
    return db.execute(
        text("""
            SELECT
                s.*,
                o.name AS organization_name
            FROM employee_legajo_signatures s
            JOIN organizations o ON o.id = s.organization_id
            WHERE s.id::text = :identifier OR s.token_hash = :token_hash
            LIMIT 1
        """),
        {"identifier": identifier, "token_hash": token_hash},
    ).mappings().first()


def _require_employee_request(row, user: Dict):
    if (
        user.get("role") != "employee"
        or str(user.get("employee_id") or "") != str(row["employee_id"])
        or str(user.get("organization_id") or "") != str(row["organization_id"])
    ):
        raise HTTPException(404, "legajo_no_encontrado")


def _decrypt_file(
    db: Session,
    raw_path: str,
    organization_id: str,
    actor_id: str,
    actor_type: str,
    purpose: str,
    expected_hash: str,
) -> Path:
    path = _safe_storage_path(raw_path)
    try:
        return get_encryption_service().decrypt_file_to_temp(
            db,
            path,
            organization_id=organization_id,
            actor_id=actor_id,
            actor_type=actor_type,
            purpose=purpose,
            expected_plaintext_sha256=expected_hash,
            suffix=".pdf",
        )
    except Exception:
        logger.exception("employee_legajo.decrypt_failed")
        raise HTTPException(500, "error_al_abrir_legajo")


@router.post("/{employee_id}/send")
async def send_employee_legajo_for_signature(
    employee_id: str,
    request: Request,
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    organization_id = str(user["organization_id"])
    employee = db.execute(
        text("""
            SELECT id, first_name, last_name, email, cuil, is_deleted
            FROM employees
            WHERE id = :employee_id AND organization_id = :organization_id
        """),
        {"employee_id": employee_id, "organization_id": organization_id},
    ).mappings().first()
    if not employee or employee["is_deleted"]:
        raise HTTPException(404, "empleado_no_encontrado")
    if not employee["email"]:
        raise HTTPException(400, "empleado_sin_email")
    if not validate_email_format(employee["email"]):
        raise HTTPException(400, "email_empleado_invalido")
    cuil = normalize_cuil(employee["cuil"] or "")
    from services.legajo.cuil_validator import validate_cuil

    if not cuil or not validate_cuil(cuil)[0]:
        raise HTTPException(400, "empleado_sin_cuil_valido")

    now = datetime.now(timezone.utc)
    with safe_transaction(db):
        db.execute(
            text("""
                UPDATE employee_legajo_signatures
                SET status = 'expired'
                WHERE organization_id = :organization_id
                  AND employee_id = :employee_id
                  AND status = 'pending'
                  AND token_expires_at <= :now
            """),
            {"organization_id": organization_id, "employee_id": employee_id, "now": now},
        )
        pending = db.execute(
            text("""
                SELECT id FROM employee_legajo_signatures
                WHERE organization_id = :organization_id
                  AND employee_id = :employee_id
                  AND status = 'pending'
                LIMIT 1
            """),
            {"organization_id": organization_id, "employee_id": employee_id},
        ).first()
    if pending:
        raise HTTPException(409, "ya_existe_legajo_pendiente")

    from services.employee_pdf_service import EmployeePDFService

    employee_name = " ".join(
        part for part in (employee["first_name"], employee["last_name"]) if part
    ).strip() or "Empleado"
    try:
        pdf_bytes = EmployeePDFService(db).generate_record_pdf(employee_id, organization_id)
    except ValueError as exc:
        if str(exc) == "employee_not_found":
            raise HTTPException(404, "empleado_no_encontrado") from exc
        raise HTTPException(400, "error_generando_legajo") from exc
    except Exception as exc:
        logger.exception("employee_legajo.pdf_generation_failed")
        raise HTTPException(500, "error_generando_legajo") from exc

    if not pdf_bytes or len(pdf_bytes) > config.MAX_FILE_SIZE:
        raise HTTPException(400, "legajo_pdf_invalido")
    try:
        import fitz

        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            if not document.page_count or document.page_count > config.MAX_PDF_PAGES:
                raise HTTPException(400, "cantidad_paginas_legajo_invalida")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "legajo_pdf_invalido") from exc

    signature_id = str(uuid.uuid4())
    raw_token = secrets.token_urlsafe(32)
    token_digest = hash_token(raw_token)
    base_dir = STORAGE_ROOT / "employee_legajo_signatures" / organization_id / signature_id
    base_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    source_path = base_dir / "source.pdf"
    source_hash = _sha256(pdf_bytes)

    try:
        with open(source_path, "xb") as file:
            os.chmod(source_path, 0o600)
            file.write(pdf_bytes)
            file.flush()
            os.fsync(file.fileno())

        encryption_service = get_encryption_service()
        source_encryption = encryption_service.encrypt_file_in_place(
            source_path,
            organization_id=organization_id,
            purpose="employee_legajo_signature_source",
            file_id=signature_id,
            plaintext_sha256=source_hash,
        )
        with safe_transaction(db):
            encryption_service.persist_metadata_and_audit(
                db,
                source_encryption,
                actor_id=str(user["id"]),
                actor_type="admin",
            )
            db.execute(
                text("""
                    INSERT INTO employee_legajo_signatures (
                        id, organization_id, employee_id, created_by_user_id,
                        employee_cuil, employee_email, employee_name,
                        source_pdf_path, source_pdf_sha256, token_hash,
                        token_expires_at, issuer_ip, issuer_ua, status
                    ) VALUES (
                        :id, :organization_id, :employee_id, :created_by_user_id,
                        :employee_cuil, :employee_email, :employee_name,
                        :source_pdf_path, :source_pdf_sha256, :token_hash,
                        :token_expires_at, :issuer_ip, :issuer_ua, 'pending'
                    )
                """),
                {
                    "id": signature_id,
                    "organization_id": organization_id,
                    "employee_id": employee_id,
                    "created_by_user_id": str(user["id"]),
                    "employee_cuil": cuil,
                    "employee_email": employee["email"],
                    "employee_name": employee_name,
                    "source_pdf_path": str(source_path),
                    "source_pdf_sha256": source_hash,
                    "token_hash": token_digest,
                    "token_expires_at": now + TOKEN_TTL,
                    "issuer_ip": get_real_ip(request),
                    "issuer_ua": request.headers.get("user-agent", "")[:500],
                },
            )
            audit(
                db,
                organization_id,
                "admin",
                str(user["id"]),
                "EMPLOYEE_LEGAJO_SIGNATURE_REQUESTED",
                signature_id,
                {"employee_id": employee_id, "source_pdf_sha256": source_hash},
            )
    except IntegrityError as exc:
        try:
            shutil.rmtree(base_dir)
        except OSError:
            logger.exception("employee_legajo.source_cleanup_failed")
        if "uq_employee_legajo_signature_pending" in str(exc.orig):
            raise HTTPException(409, "ya_existe_legajo_pendiente") from exc
        logger.exception("employee_legajo.persistence_integrity_error")
        raise HTTPException(500, "error_creando_solicitud_de_firma") from exc
    except Exception as exc:
        try:
            shutil.rmtree(base_dir)
        except OSError:
            logger.exception("employee_legajo.source_cleanup_failed")
        if isinstance(exc, HTTPException):
            raise
        logger.exception("employee_legajo.request_create_failed")
        raise HTTPException(500, "error_creando_solicitud_de_firma") from exc

    base_url = config._detect_ngrok_url() or config.BASE_PUBLIC_URL
    sign_url = f"{base_url}/ui/#/empleado/legajo-firma/{raw_token}"
    organization = db.execute(
        text("SELECT name FROM organizations WHERE id = :id"),
        {"id": organization_id},
    ).first()
    organization_name = organization.name if organization else "Empresa"
    safe_name = html.escape(employee_name)
    safe_org = html.escape(organization_name)
    safe_url = html.escape(sign_url, quote=True)
    try:
        await EmailService().send_html(
            to=employee["email"],
            subject="Tenés un legajo pendiente de firma",
            reply_to=user.get("email"),
            body_html=f"""
                <html><body style="font-family:Arial,sans-serif;color:#1e293b;line-height:1.6">
                  <p>Hola {safe_name},</p>
                  <p>{safe_org} te envió un legajo que requiere tu firma electrónica.</p>
                  <p>Ingresá a tu cuenta, revisá todas las páginas y confirmá tu CUIL antes de firmar.</p>
                  <p><a href="{safe_url}">Revisar y firmar legajo</a></p>
                  <p>El enlace es personal y vence en 7 días. Si no esperabas este pedido, contactá a tu empresa.</p>
                </body></html>
            """,
        )
    except Exception as exc:
        logger.exception("employee_legajo.signature_email_failed")
        with safe_transaction(db):
            db.execute(
                text("""
                    UPDATE employee_legajo_signatures
                    SET status = 'cancelled'
                    WHERE id = :id AND status = 'pending'
                """),
                {"id": signature_id},
            )
        raise HTTPException(
            502,
            "solicitud_creada_pero_no_se_pudo_enviar_el_correo",
        ) from exc

    return {"status": "pending", "id": signature_id}


@router.get("/pending")
async def list_my_pending_legajos(
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    if user.get("role") != "employee" or not user.get("employee_id"):
        raise HTTPException(403, "solo_empleados")
    rows = db.execute(
        text("""
            SELECT s.id, s.employee_name, s.created_at, s.token_expires_at,
                   o.name AS organization_name
            FROM employee_legajo_signatures s
            JOIN organizations o ON o.id = s.organization_id
            WHERE s.employee_id = :employee_id
              AND s.organization_id = :organization_id
              AND s.status = 'pending'
              AND s.token_expires_at > :now
            ORDER BY s.created_at DESC
        """),
        {
            "employee_id": str(user["employee_id"]),
            "organization_id": str(user["organization_id"]),
            "now": datetime.now(timezone.utc),
        },
    ).mappings().all()
    return {
        "legajos": [
            {
                "id": str(row["id"]),
                "employee_name": row["employee_name"],
                "organization_name": row["organization_name"],
                "created_at": row["created_at"].isoformat(),
                "expires_at": row["token_expires_at"].isoformat(),
            }
            for row in rows
        ]
    }


@router.get("/history")
async def list_company_legajo_history(
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        text("""
            SELECT id, employee_name, employee_email, status, created_at, signed_at,
                   token_expires_at
            FROM employee_legajo_signatures
            WHERE organization_id = :organization_id
            ORDER BY created_at DESC
            LIMIT 2000
        """),
        {"organization_id": str(user["organization_id"])},
    ).mappings().all()
    return {
        "legajos": [
            {
                "id": str(row["id"]),
                "employee_name": row["employee_name"],
                "employee_email": row["employee_email"],
                "status": (
                    "expired"
                    if row["status"] == "pending"
                    and row["token_expires_at"] <= datetime.now(timezone.utc)
                    else row["status"]
                ),
                "created_at": row["created_at"].isoformat(),
                "signed_at": row["signed_at"].isoformat() if row["signed_at"] else None,
            }
            for row in rows
        ]
    }


@router.get("/pending/{identifier}")
async def get_pending_legajo(
    identifier: str,
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    row = _lookup_legajo(db, identifier)
    if not row:
        raise HTTPException(404, "legajo_no_encontrado")
    _require_employee_request(row, user)
    if row["status"] != "pending" or row["token_expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(410, "solicitud_de_firma_vencida_o_completada")
    signature = db.execute(
        text("""
            SELECT signature_path FROM user_signatures
            WHERE user_id = :user_id AND is_active = true
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"user_id": str(user["id"])},
    ).first()
    has_signature = False
    if signature and signature.signature_path:
        try:
            signature_path = Path(signature.signature_path).resolve()
            signature_path.relative_to(STORAGE_ROOT)
            has_signature = signature_path.is_file()
        except (OSError, ValueError):
            logger.exception("employee_legajo.saved_signature_unavailable")
    return {
        "id": str(row["id"]),
        "employee_name": row["employee_name"],
        "organization_name": row["organization_name"],
        "created_at": row["created_at"].isoformat(),
        "has_signature": has_signature,
    }


@router.get("/pending/{identifier}/pdf")
async def view_pending_legajo(
    identifier: str,
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    row = _lookup_legajo(db, identifier)
    if not row:
        raise HTTPException(404, "legajo_no_encontrado")
    _require_employee_request(row, user)
    if row["status"] != "pending" or row["token_expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(410, "solicitud_de_firma_vencida_o_completada")
    temp_path = _decrypt_file(
        db,
        row["source_pdf_path"],
        str(row["organization_id"]),
        str(user["id"]),
        "employee",
        "employee_legajo_signature_source",
        row["source_pdf_sha256"],
    )
    return FileResponse(
        temp_path,
        media_type="application/pdf",
        background=BackgroundTask(EncryptionService.cleanup_temp_file, temp_path),
        headers={"Content-Disposition": "inline; filename=legajo_pendiente.pdf"},
    )


@router.post("/pending/{identifier}/sign")
async def sign_pending_legajo(
    identifier: str,
    body: EmployeeLegajoSignatureBody,
    request: Request,
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    row = _lookup_legajo(db, identifier)
    if not row:
        raise HTTPException(404, "legajo_no_encontrado")
    _require_employee_request(row, user)
    if row["status"] != "pending" or row["token_expires_at"] <= datetime.now(timezone.utc):
        raise HTTPException(410, "solicitud_de_firma_vencida_o_completada")

    from services.legajo.cuil_validator import normalize_cuil as normalize_registered_cuil, validate_cuil

    provided_cuil = normalize_registered_cuil(body.cuil or "")
    stored_cuil = normalize_registered_cuil(row["employee_cuil"] or "")
    if (
        not stored_cuil
        or not provided_cuil
        or not validate_cuil(provided_cuil)[0]
        or stored_cuil != provided_cuil
    ):
        raise HTTPException(400, "cuil_incorrecto")

    signature = db.execute(
        text("""
            SELECT signature_path, signature_hash
            FROM user_signatures
            WHERE user_id = :user_id AND is_active = true
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"user_id": str(user["id"])},
    ).first()
    if not signature or not signature.signature_path:
        raise HTTPException(400, "signature_required")
    try:
        signature_path = Path(signature.signature_path).resolve()
        signature_path.relative_to(STORAGE_ROOT)
        signature_bytes = signature_path.read_bytes()
    except (OSError, ValueError):
        logger.exception("employee_legajo.saved_signature_unavailable")
        raise HTTPException(400, "archivo_de_firma_perdido")
    signature_hash = signature.signature_hash or _sha256(signature_bytes)
    if not secrets.compare_digest(signature_hash, _sha256(signature_bytes)):
        logger.error("employee_legajo.saved_signature_integrity_failure")
        raise HTTPException(409, "integridad_de_firma_invalida")

    with safe_transaction(db):
        claimed = db.execute(
            text("""
                UPDATE employee_legajo_signatures
                SET processing_signature = true
                WHERE id = :id AND status = 'pending'
                  AND processing_signature = false
                  AND token_expires_at > :now
                RETURNING id
            """),
            {"id": str(row["id"]), "now": datetime.now(timezone.utc)},
        ).first()
    if not claimed:
        raise HTTPException(409, "solicitud_de_firma_ya_en_proceso")

    working_dir = STORAGE_ROOT / "employee_legajo_signatures" / str(row["organization_id"]) / str(row["id"])
    working_path = working_dir / "working.pdf"
    temp_decrypted = None
    engine_result = None
    try:
        temp_decrypted = _decrypt_file(
            db,
            row["source_pdf_path"],
            str(row["organization_id"]),
            str(user["id"]),
            "employee",
            "employee_legajo_signature_source",
            row["source_pdf_sha256"],
        )
        with open(working_path, "xb") as working_file:
            os.chmod(working_path, 0o600)
            with open(temp_decrypted, "rb") as source_file:
                shutil.copyfileobj(source_file, working_file)
        full_name = user.get("full_name") or row["employee_name"]
        ctx = {
            "receipt_id": str(row["id"]),
            "organization_id": str(row["organization_id"]),
            "role": "employee",
            "receipt_pdf_path": str(working_path),
            "full_name": full_name,
            "cuil": stored_cuil,
            "dni": user.get("dni") or stored_cuil,
            "email": user.get("email") or row["employee_email"],
            "logo_path": None,
            "verification_id": None,
            "source": "employee_legajo",
            "doc_type": "EMPLOYEE_LEGAJO",
            "apply_to_all_pages": True,
            "user": {
                **user,
                "role": "employee",
                "full_name": full_name,
                "dni": user.get("dni") or stored_cuil,
                "email": user.get("email") or row["employee_email"],
            },
        }
        import asyncio
        from modules.digital_signature import DigitalSignatureEngine, _pdf_executor

        engine_result = await asyncio.get_running_loop().run_in_executor(
            _pdf_executor,
            DigitalSignatureEngine.process_pdf,
            ctx,
            signature_bytes,
        )
        seal_id = ctx.get("generated_seal_id")
        if not seal_id:
            raise RuntimeError("signature_engine_did_not_return_seal_id")
        generated_path = Path(engine_result["signed_pdf_path"]).resolve()
        final_path = working_dir / "signed.pdf"
        shutil.copyfile(generated_path, final_path)
        os.chmod(final_path, 0o600)
        final_hash = _sha256(final_path.read_bytes())
        encryption_service = get_encryption_service()
        signed_encryption = encryption_service.encrypt_file_in_place(
            final_path,
            organization_id=str(row["organization_id"]),
            purpose="employee_legajo_signature_signed",
            plaintext_sha256=final_hash,
        )
        with safe_transaction(db):
            encryption_service.persist_metadata_and_audit(
                db,
                signed_encryption,
                actor_id=str(user["id"]),
                actor_type="employee",
            )
            updated = db.execute(
                text("""
                    UPDATE employee_legajo_signatures
                    SET status = 'signed',
                        processing_signature = false,
                        signed_by_user_id = :user_id,
                        signed_pdf_path = :signed_pdf_path,
                        signed_pdf_sha256 = :signed_pdf_sha256,
                        signature_hash = :signature_hash,
                        seal_id = :seal_id,
                        signer_ip = :signer_ip,
                        signer_ua = :signer_ua,
                        signed_at = :signed_at
                    WHERE id = :id AND status = 'pending'
                      AND processing_signature = true
                    RETURNING id
                """),
                {
                    "id": str(row["id"]),
                    "user_id": str(user["id"]),
                    "signed_pdf_path": str(final_path),
                    "signed_pdf_sha256": final_hash,
                    "signature_hash": signature_hash,
                    "seal_id": seal_id,
                    "signer_ip": get_real_ip(request),
                    "signer_ua": request.headers.get("user-agent", "")[:500],
                    "signed_at": datetime.now(timezone.utc),
                },
            ).first()
            if not updated:
                raise HTTPException(409, "solicitud_de_firma_ya_completada")
            db.execute(
                text("""
                    INSERT INTO receipt_seals (
                        seal_id, receipt_id, organization_id, signer_dni,
                        signer_name, signer_role, pdf_hash, metadata
                    ) VALUES (
                        :seal_id, :document_id, :organization_id, :signer_dni,
                        :signer_name, 'employee', :pdf_hash, CAST(:metadata AS JSONB)
                    )
                """),
                {
                    "seal_id": seal_id,
                    "document_id": str(row["id"]),
                    "organization_id": str(row["organization_id"]),
                    "signer_dni": user.get("dni") or stored_cuil,
                    "signer_name": full_name,
                    "pdf_hash": final_hash,
                    "metadata": json.dumps({
                        "document_type": "employee_legajo",
                        "source_pdf_sha256": row["source_pdf_sha256"],
                        "signature_hash": signature_hash,
                        "pages_stamped": True,
                    }),
                },
            )
            audit(
                db,
                str(row["organization_id"]),
                "employee",
                str(user["id"]),
                "EMPLOYEE_LEGAJO_SIGNED",
                str(row["id"]),
                {
                    "employee_id": str(row["employee_id"]),
                    "source_pdf_sha256": row["source_pdf_sha256"],
                    "signed_pdf_sha256": final_hash,
                    "signature_hash": signature_hash,
                },
            )
        return {"status": "signed"}
    except HTTPException:
        with safe_transaction(db):
            db.execute(
                text("""
                    UPDATE employee_legajo_signatures
                    SET processing_signature = false
                    WHERE id = :id AND status = 'pending'
                """),
                {"id": str(row["id"])},
            )
        try:
            (working_dir / "signed.pdf").unlink(missing_ok=True)
        except OSError:
            logger.exception("employee_legajo.failed_output_cleanup_failed")
        raise
    except Exception as exc:
        logger.exception("employee_legajo.sign_failed")
        with safe_transaction(db):
            db.execute(
                text("""
                    UPDATE employee_legajo_signatures
                    SET processing_signature = false
                    WHERE id = :id AND status = 'pending'
                """),
                {"id": str(row["id"])},
            )
        try:
            (working_dir / "signed.pdf").unlink(missing_ok=True)
        except OSError:
            logger.exception("employee_legajo.failed_output_cleanup_failed")
        raise HTTPException(500, "error_al_firmar_legajo") from exc
    finally:
        for path in (working_path, temp_decrypted):
            if path:
                try:
                    Path(path).unlink(missing_ok=True)
                except OSError:
                    logger.exception("employee_legajo.temp_cleanup_failed")
        if engine_result and engine_result.get("signed_pdf_path"):
            try:
                Path(engine_result["signed_pdf_path"]).unlink(missing_ok=True)
            except OSError:
                logger.exception("employee_legajo.engine_output_cleanup_failed")


@router.get("/{legajo_id}/pdf")
async def download_company_legajo_pdf(
    legajo_id: str,
    version: str = "signed",
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if version not in {"source", "signed"}:
        raise HTTPException(400, "version_invalida")
    row = db.execute(
        text("""
            SELECT * FROM employee_legajo_signatures
            WHERE id = :id AND organization_id = :organization_id
        """),
        {"id": legajo_id, "organization_id": str(user["organization_id"])},
    ).mappings().first()
    if not row:
        raise HTTPException(404, "legajo_no_encontrado")
    if version == "signed":
        if row["status"] != "signed" or not row["signed_pdf_path"]:
            raise HTTPException(404, "legajo_firmado_no_disponible")
        path, purpose, expected_hash = (
            row["signed_pdf_path"],
            "employee_legajo_signature_signed",
            row["signed_pdf_sha256"],
        )
    else:
        path, purpose, expected_hash = (
            row["source_pdf_path"],
            "employee_legajo_signature_source",
            row["source_pdf_sha256"],
        )
    temp_path = _decrypt_file(
        db,
        path,
        str(row["organization_id"]),
        str(user["id"]),
        "admin",
        purpose,
        expected_hash,
    )
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", row["employee_name"]).strip("_") or "empleado"
    filename = f"legajo_{safe_name}_{version}.pdf"
    return FileResponse(
        temp_path,
        media_type="application/pdf",
        background=BackgroundTask(EncryptionService.cleanup_temp_file, temp_path),
        headers={"Content-Disposition": f"inline; filename={filename}"},
    )
