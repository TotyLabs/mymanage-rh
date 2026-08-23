"""
Company Signers API
Manage authorized company signers (name, position, signature image).
Company signatures use uploaded images, not canvas drawing.
"""

import os
import base64
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException, Form, UploadFile, File
from sqlalchemy import text
from sqlalchemy.orm import Session

from payroll_core import get_db, require_admin, audit, logger, safe_transaction, sanitize_text_input

router = APIRouter(prefix="/api/company-signers", tags=["company-signers"])

import config
STORAGE_BASE = Path(config.STORAGE_PATH)
SIGNERS_DIR = STORAGE_BASE / "signatures" / "company"


@router.get("")
async def list_company_signers(
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all company signers for the org."""
    org_id = user["organization_id"]
    rows = db.execute(
        text("""
            SELECT id, name, position, signature_image_path, is_active, created_at
            FROM company_signers
            WHERE organization_id = :org
            ORDER BY created_at DESC
        """),
        {"org": org_id}
    ).fetchall()

    return {
        "signers": [
            {
                "id": str(r.id),
                "name": r.name,
                "position": r.position,
                "has_signature": bool(r.signature_image_path),
                "is_active": r.is_active,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "file_exists": os.path.exists(r.signature_image_path) if r.signature_image_path else False,
                "needs_reupload": not os.path.exists(r.signature_image_path) if r.signature_image_path else True
            }
            for r in rows
        ]
    }


@router.post("")
async def create_company_signer(
    name: str = Form(...),
    position: str = Form(...),
    signature_image: Optional[UploadFile] = File(None),
    signature_base64: Optional[str] = Form(None),
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new company signer with uploaded signature image or canvas base64."""
    org_id = user["organization_id"]
    clean_name = sanitize_text_input(name)
    clean_position = sanitize_text_input(position)

    if not clean_name or not clean_position:
        raise HTTPException(400, "nombre_y_cargo_requeridos")

    try:
        img_bytes = None
        
        # 1. Handle File Upload
        if signature_image and signature_image.filename:
            img_bytes = await signature_image.read()
            
        # 2. Handle Base64 (Canvas)
        elif signature_base64:
            try:
                if "," in signature_base64:
                    header, encoded = signature_base64.split(",", 1)
                else:
                    encoded = signature_base64
                img_bytes = base64.b64decode(encoded)
            except Exception:
                raise HTTPException(400, "base64_invalido")

        if not img_bytes or len(img_bytes) < 100:
            raise HTTPException(400, "imagen_firma_requerida")

        with safe_transaction(db):
            # Insert signer record
            res = db.execute(
                text("""
                    INSERT INTO company_signers (organization_id, name, position, is_active)
                    VALUES (:org, :name, :pos, true)
                    RETURNING id
                """),
                {"org": org_id, "name": clean_name, "pos": clean_position}
            )
            signer_id = str(res.fetchone().id)

            # Save image atomically using tempfile and os.replace
            SIGNERS_DIR.mkdir(parents=True, exist_ok=True)
            sig_path = SIGNERS_DIR / f"{signer_id}.png"
            
            import tempfile
            import os
            from file_processing.dispatcher import process_file
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(img_bytes)
                tmp_name = tmp.name
                
            try:
                opt_path = process_file(tmp_name, "signature")
                with open(opt_path, "rb") as f:
                    opt_bytes = f.read()

                from payroll_core import save_bytes_atomically
                save_bytes_atomically(opt_bytes, sig_path)
            finally:
                if os.path.exists(opt_path):
                    os.remove(opt_path)
                if os.path.exists(tmp_name):
                    try: os.remove(tmp_name)
                    except: pass

            # Update path and DATA in DB (Phase 26 Hardening)
            db.execute(
                text("UPDATE company_signers SET signature_image_path = :path, signature_image_data = :data WHERE id = :sid"),
                {"path": str(sig_path), "data": opt_bytes, "sid": signer_id}
            )

            audit(db, org_id, "admin", user["id"], "CREATE_COMPANY_SIGNER", signer_id,
                  {"name": clean_name, "position": clean_position})

        logger.info(f"company_signer_created: {signer_id} for org {org_id}")
        return {"status": "ok", "signer_id": signer_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("create_company_signer_error")
        raise HTTPException(500, "error_al_crear_firmante")


@router.delete("/{signer_id}")
async def delete_company_signer(
    signer_id: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove a company signer."""
    org_id = user["organization_id"]

    try:
        with safe_transaction(db):
            existing = db.execute(
                text("SELECT id FROM company_signers WHERE id = :id AND organization_id = :org"),
                {"id": signer_id, "org": org_id}
            ).fetchone()

            if not existing:
                raise HTTPException(404, "firmante_no_encontrado")

            db.execute(text("DELETE FROM company_signers WHERE id = :id"), {"id": signer_id})
            audit(db, org_id, "admin", user["id"], "DELETE_COMPANY_SIGNER", signer_id, {})

        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("delete_company_signer_error")
        raise HTTPException(500, "error_al_eliminar_firmante")


@router.post("/{signer_id}/toggle")
async def toggle_company_signer(
    signer_id: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Toggle active status of a company signer."""
    org_id = user["organization_id"]

    try:
        with safe_transaction(db):
            existing = db.execute(
                text("SELECT id, is_active FROM company_signers WHERE id = :id AND organization_id = :org"),
                {"id": signer_id, "org": org_id}
            ).fetchone()

            if not existing:
                raise HTTPException(404, "firmante_no_encontrado")

            new_status = not existing.is_active

            db.execute(
                text("UPDATE company_signers SET is_active = :active WHERE id = :id"),
                {"active": new_status, "id": signer_id}
            )

        return {"status": "ok", "is_active": new_status}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("toggle_company_signer_error")
        raise HTTPException(500, "error_al_actualizar_firmante")


@router.get("/{signer_id}/image")
async def get_signer_image(
    signer_id: str,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Serve the signer's signature image."""
    org_id = user["organization_id"]
    from fastapi.responses import FileResponse

    from payroll_core import sync_signer_image_from_db
    image_path = sync_signer_image_from_db(db, signer_id)

    if not image_path:
        raise HTTPException(404, "firma_no_encontrada")

    from payroll_core import safe_join_under_storage
    try:
        # API-004 FIX: Use safe_join_under_storage to prevent path traversal
        rel_path = os.path.relpath(image_path, str(STORAGE_BASE))
        safe_path = safe_join_under_storage(rel_path)
    except Exception:
        raise HTTPException(403, "acceso_denegado")

    if not os.path.exists(safe_path):
        raise HTTPException(404, "archivo_firma_no_encontrado")

    return FileResponse(safe_path, media_type="image/png")
