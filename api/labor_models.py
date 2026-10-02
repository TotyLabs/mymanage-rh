"""Modelos Laborales API: TLG-INT-001 vertical slice."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

import config
from payroll_core import audit, get_db, require_admin, safe_join_under_storage, utc_now
from services.email_service import EmailService
from services.labor_model_service import catalog, get_model, pending_fields, render_instance, resolve_fields

router = APIRouter(prefix="/api/labor-models", tags=["labor-models"])


class CreateLaborDocumentRequest(BaseModel):
    template_code: str = "TLG-INT-001"
    employee_id: Optional[str] = None


class UpdateLaborDocumentRequest(BaseModel):
    fields: Dict[str, Any] = Field(default_factory=dict)


class EmailLaborDocumentRequest(BaseModel):
    employee_id: Optional[str] = None
    recipient_email: Optional[EmailStr] = None


def _serialize(row) -> dict:
    fields = row["fields"] or {}
    return {
        "id": str(row["id"]),
        "template_code": row["template_code"],
        "template_version": row["template_version"],
        "category": row["category"],
        "title": row["title"],
        "status": row["status"],
        "employee_id": str(row["employee_id"]) if row["employee_id"] else None,
        "fields": fields,
        "pending_fields": pending_fields(fields, row["template_code"]),
        "rendered_pdf_path": row["rendered_pdf_path"],
        "final_pdf_path": row["final_pdf_path"],
        "rendered_pdf_sha256": row["rendered_pdf_sha256"],
        "final_pdf_sha256": row["final_pdf_sha256"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        "signed_at": row["signed_at"].isoformat() if row["signed_at"] else None,
    }


def _get_document(db: Session, document_id: str, organization_id: str):
    row = db.execute(text("""
        SELECT * FROM labor_model_documents
        WHERE id = :id AND organization_id = :org
    """), {"id": document_id, "org": organization_id}).mappings().first()
    if not row:
        raise HTTPException(404, "labor_document_not_found")
    return row


@router.get("/catalog")
async def get_catalog(user=Depends(require_admin)):
    return {"models": catalog()}


@router.get("/documents")
async def list_labor_documents(user=Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT * FROM labor_model_documents
        WHERE organization_id = :org AND status <> 'ELIMINADO'
        ORDER BY created_at DESC
    """), {"org": user["organization_id"]}).mappings().all()
    return {"documents": [_serialize(row) for row in rows]}


@router.post("/documents")
async def create_labor_document(
    body: CreateLaborDocumentRequest,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    model = get_model(body.template_code)
    fields = resolve_fields(db, str(user["organization_id"]), body.employee_id)
    document_id = str(uuid.uuid4())
    db.execute(text("""
        INSERT INTO labor_model_documents (
            id, organization_id, template_code, template_version, category, title,
            status, employee_id, fields, template_path, created_by_user_id
        ) VALUES (
            :id, :org, :code, :version, :category, :title,
            'BORRADOR', :employee, CAST(:fields AS jsonb), :template, :user
        )
    """), {
        "id": document_id,
        "org": user["organization_id"],
        "code": model["code"],
        "version": model["version"],
        "category": model["category"],
        "title": model["title"],
        "employee": body.employee_id,
        "fields": json.dumps(fields),
        "template": model["template_path"],
        "user": user["id"],
    })
    db.commit()
    audit(db, user["organization_id"], "admin", user["id"], "LABOR_MODEL_CREATED", document_id, {"template_code": model["code"]})
    row = _get_document(db, document_id, str(user["organization_id"]))
    return _serialize(row)


@router.get("/documents/{document_id}")
async def get_labor_document(document_id: str, user=Depends(require_admin), db: Session = Depends(get_db)):
    return _serialize(_get_document(db, document_id, str(user["organization_id"])))


@router.patch("/documents/{document_id}")
async def update_labor_document(
    document_id: str,
    body: UpdateLaborDocumentRequest,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = _get_document(db, document_id, str(user["organization_id"]))
    if row["status"] in ("FIRMADO", "ENVIADO"):
        raise HTTPException(409, "labor_document_locked")
    fields = dict(row["fields"] or {})
    fields.update({key: str(value) if value is not None else "" for key, value in body.fields.items()})
    db.execute(text("""
        UPDATE labor_model_documents
        SET fields = CAST(:fields AS jsonb), updated_at = :now
        WHERE id = :id AND organization_id = :org
    """), {"fields": json.dumps(fields), "now": utc_now(), "id": document_id, "org": user["organization_id"]})
    db.commit()
    return _serialize(_get_document(db, document_id, str(user["organization_id"])))


@router.delete("/documents/{document_id}")
async def delete_labor_document(document_id: str, user=Depends(require_admin), db: Session = Depends(get_db)):
    row = _get_document(db, document_id, str(user["organization_id"]))
    if row["status"] == "ELIMINADO":
        raise HTTPException(404, "labor_document_not_found")
    db.execute(text("""
        UPDATE labor_model_documents
        SET status = 'ELIMINADO', updated_at = :now
        WHERE id = :id AND organization_id = :org
    """), {"now": utc_now(), "id": document_id, "org": user["organization_id"]})
    db.commit()
    return {"status": "deleted", "document": _serialize(_get_document(db, document_id, str(user["organization_id"])))}


@router.post("/documents/{document_id}/autofill")
async def autofill_labor_document(document_id: str, user=Depends(require_admin), db: Session = Depends(get_db)):
    row = _get_document(db, document_id, str(user["organization_id"]))
    if not row["employee_id"]:
        raise HTTPException(400, "employee_required_for_autofill")
    if row["status"] in ("FIRMADO", "ENVIADO"):
        raise HTTPException(409, "labor_document_locked")
    fields = resolve_fields(db, str(user["organization_id"]), str(row["employee_id"]))
    db.execute(text("""
        UPDATE labor_model_documents
        SET fields = CAST(:fields AS jsonb), updated_at = :now
        WHERE id = :id AND organization_id = :org
    """), {"fields": json.dumps(fields), "now": utc_now(), "id": document_id, "org": user["organization_id"]})
    db.commit()
    return _serialize(_get_document(db, document_id, str(user["organization_id"])))


@router.post("/documents/{document_id}/render")
async def render_labor_document(document_id: str, user=Depends(require_admin), db: Session = Depends(get_db)):
    row = _get_document(db, document_id, str(user["organization_id"]))
    missing = pending_fields(row["fields"] or {}, row["template_code"])
    if missing:
        raise HTTPException(400, {"code": "required_fields_pending", "fields": missing})
    result = render_instance(db, document_id, str(user["organization_id"]))
    audit(db, user["organization_id"], "admin", user["id"], "LABOR_MODEL_RENDERED", document_id, {"sha256": result["sha256"]})
    return {"status": "rendered", "document": _serialize(_get_document(db, document_id, str(user["organization_id"]))) }


@router.get("/documents/{document_id}/download")
async def download_labor_document(document_id: str, user=Depends(require_admin), db: Session = Depends(get_db)):
    row = _get_document(db, document_id, str(user["organization_id"]))
    relative = row["final_pdf_path"] or row["rendered_pdf_path"]
    if not relative:
        raise HTTPException(404, "labor_document_not_rendered")
    path = Path(safe_join_under_storage(relative))
    if not path.exists():
        raise HTTPException(404, "labor_document_file_missing")
    return FileResponse(str(path), media_type="application/pdf", filename=f"{row['template_code']}_{document_id[:8]}.pdf", headers={"Cache-Control": "private, no-store"})


@router.post("/documents/{document_id}/sign")
async def sign_labor_document(document_id: str, request: Request, user=Depends(require_admin), db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT * FROM labor_model_documents
        WHERE id = :id AND organization_id = :org
        FOR UPDATE
    """), {"id": document_id, "org": user["organization_id"]}).mappings().first()
    if not row:
        raise HTTPException(404, "labor_document_not_found")
    if row["status"] != "LISTO_PARA_FIRMAR":
        raise HTTPException(409, "labor_document_not_ready_for_signature")
    missing = pending_fields(row["fields"] or {}, row["template_code"])
    if missing:
        raise HTTPException(400, {"code": "required_fields_pending", "fields": missing})
    relative = row["rendered_pdf_path"]
    if not relative:
        raise HTTPException(400, "labor_document_must_be_rendered")
    source_pdf = Path(safe_join_under_storage(relative))
    if not source_pdf.is_file():
        raise HTTPException(404, "labor_document_file_missing")

    signer = db.execute(text("""
        SELECT id, name, position, signature_image_path, signature_image_data
        FROM company_signers
        WHERE organization_id = :org AND is_active = true
        ORDER BY created_at DESC LIMIT 1
    """), {"org": user["organization_id"]}).mappings().first()
    if not signer:
        raise HTTPException(400, "company_signer_required")
    image_bytes = signer["signature_image_data"]
    if not image_bytes and signer["signature_image_path"] and Path(signer["signature_image_path"]).exists():
        image_bytes = Path(signer["signature_image_path"]).read_bytes()
    if not image_bytes:
        raise HTTPException(400, "company_signer_signature_missing")

    from modules.digital_signature import DigitalSignatureEngine, _pdf_executor
    company_cuit = db.execute(
        text("SELECT cuit FROM organizations WHERE id = :id"),
        {"id": user["organization_id"]},
    ).scalar() or ""
    ctx = {
        "receipt_id": document_id,
        "organization_id": str(user["organization_id"]),
        "receipt_pdf_path": relative,
        "receipt_pdf_sha256": row["rendered_pdf_sha256"],
        "role": "employer",
        "source": "labor_model",
        "doc_type": "labor_model",
        "full_name": signer["name"],
        "cuit": company_cuit,
        "user": {
            "id": user["id"],
            "role": "employer",
            "full_name": signer["name"],
            "dni": company_cuit,
            "email": user.get("email"),
            "organization_id": str(user["organization_id"]),
        },
        "verification_id": f"LM-{document_id}",
    }
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(_pdf_executor, DigitalSignatureEngine.process_pdf, ctx, image_bytes)
    final_relative = result["signed_pdf_relative"]
    signed_hash = result["new_pdf_sha256"]
    db.execute(text("""
        UPDATE labor_model_documents
        SET final_pdf_path = :path, final_pdf_sha256 = :hash, status = 'FIRMADO',
            signed_by_user_id = :user, signed_at = :now, updated_at = :now
        WHERE id = :id AND organization_id = :org AND status = 'LISTO_PARA_FIRMAR'
    """), {"path": final_relative, "hash": signed_hash, "user": user["id"], "now": utc_now(), "id": document_id, "org": user["organization_id"]})
    db.commit()
    audit(db, user["organization_id"], "admin", user["id"], "LABOR_MODEL_SIGNED", document_id, {"signer_id": str(signer["id"]), "pdf_sha256": signed_hash})
    return {"status": "signed", "document": _serialize(_get_document(db, document_id, str(user["organization_id"]))) }


@router.post("/documents/{document_id}/email")
async def email_labor_document(document_id: str, body: EmailLaborDocumentRequest, user=Depends(require_admin), db: Session = Depends(get_db)):
    row = _get_document(db, document_id, str(user["organization_id"]))
    relative = row["final_pdf_path"] or row["rendered_pdf_path"]
    if not relative:
        raise HTTPException(400, "labor_document_must_be_rendered")

    if bool(body.employee_id) == bool(body.recipient_email):
        raise HTTPException(400, "select_exactly_one_recipient")

    if body.employee_id:
        employee = db.execute(text("""
            SELECT email FROM employees
            WHERE id = :employee AND organization_id = :org AND is_deleted = false
        """), {"employee": body.employee_id, "org": user["organization_id"]}).mappings().first()
        if not employee:
            raise HTTPException(404, "employee_not_found")
        if not employee["email"]:
            raise HTTPException(400, "employee_email_not_configured")
        recipient = employee["email"]
    else:
        recipient = str(body.recipient_email)

    pdf_path = Path(safe_join_under_storage(relative))
    if not pdf_path.is_file():
        raise HTTPException(404, "labor_document_file_missing")

    try:
        await EmailService().send_html(
            to=recipient,
            subject=row["title"] or "Documento laboral",
            body_html="<p>Se adjunta el documento laboral generado por MyManageRH.</p>",
            attachments=[{
                "filename": f"{row['template_code']}_{document_id[:8]}.pdf",
                "content": pdf_path.read_bytes(),
                "subtype": "pdf",
            }],
        )
    except Exception as exc:
        db.execute(text("""
            INSERT INTO labor_model_email_events (labor_document_id, organization_id, recipient_email, status, error)
            VALUES (:doc, :org, :email, 'failed', :error)
        """), {"doc": document_id, "org": user["organization_id"], "email": recipient, "error": str(exc)[:1000]})
        db.commit()
        raise HTTPException(502, "labor_document_email_failed") from exc

    db.execute(text("""
        INSERT INTO labor_model_email_events (labor_document_id, organization_id, recipient_email, status)
        VALUES (:doc, :org, :email, 'sent')
    """), {"doc": document_id, "org": user["organization_id"], "email": recipient})
    db.commit()
    audit(db, user["organization_id"], "admin", user["id"], "LABOR_MODEL_EMAILED", document_id, {"recipient_email": recipient})
    return {"status": "sent", "recipient_email": recipient}