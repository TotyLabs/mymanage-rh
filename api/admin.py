"""
Admin API: Employer signature upload and admin tasks.
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict
from io import BytesIO
import os
from pathlib import Path
from PIL import Image
import tempfile

from payroll_core import (
    get_db,
    require_admin,
    audit,
    safe_transaction,
    file_transaction,
    logger,
)
from modules.signature import get_signature_engine

router = APIRouter(prefix="/api/admin", tags=["admin"])

ALLOWED_IMAGE_TYPES = {"png", "jpeg", "jpg", "webp", "gif", "bmp", "tiff", "mpo", "jfif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@router.post("/upload-employer-signature")
async def upload_employer_signature(
    file: UploadFile = File(...),
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Upload employer signature/seal image (PNG/JPG).
    Stored as fixed organization signature.
    """

    org_id = user["organization_id"]
    if not org_id:
        raise HTTPException(400, "admin_has_no_organization")

    try:
        content = await file.read()

        if not content:
            raise HTTPException(400, "empty_file")

        if len(content) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "file_too_large")

        # Real image type detection (not client MIME)
        try:
            with Image.open(BytesIO(content)) as img:
                detected_type = img.format.lower() if img.format else None
        except Exception:
            detected_type = None

        if detected_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(400, "invalid_image_type")

        import tempfile
        import os
        from file_processing.dispatcher import process_file
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(content)
            tmp_name = tmp.name
            
        try:
            opt_path = process_file(tmp_name, "signature")
            with open(opt_path, "rb") as f:
                content = f.read()
        finally:
            if os.path.exists(opt_path):
                os.remove(opt_path)
            if os.path.exists(tmp_name):
                try: os.remove(tmp_name)
                except: pass

        engine = get_signature_engine()

        result = engine.save_signature_image(
            role="employer",
            entity_id=org_id,
            image_bytes=content,
        )

        # Structured log
        logger.info(
            "admin.employer_signature_uploaded",
            extra={
                "event_type": "admin.employer_signature_uploaded",
                "organization_id": org_id,
                "file_path": result["path"],
            },
        )

        # Audit trail
        audit(
            db=db,
            organization_id=org_id,
            actor_type="admin",
            actor_id=user["id"],
            action="UPLOAD_EMPLOYER_SIGNATURE",
            entity_id=org_id,
            data={"path": result["path"], "sha256": result["sha"]},
        )

        return {
            "status": "uploaded",
            "path": result["path"],
            "sha256": result["sha"],
        }

    except HTTPException:
        raise

    except ValueError as e:
        logger.warning(
            "admin.upload_employer_signature_invalid",
            extra={
                "event_type": "admin.upload_employer_signature_invalid",
                "organization_id": org_id,
                "error": str(e),
            },
        )
        raise HTTPException(400, "invalid_image_content")

    except Exception:
        logger.exception(
            "admin.upload_employer_signature_failed",
            extra={
                "event_type": "admin.upload_employer_signature_failed",
                "organization_id": org_id,
            },
        )
        raise HTTPException(500, "upload_failed")

@router.post("/upload-logo")
async def upload_company_logo(
    file: UploadFile = File(...),
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Upload company logo (PNG/JPG).
    """
    org_id = user.get("organization_id")
    if not org_id:
        logger.error("admin.upload_logo_failed: admin_has_no_organization", extra={"user_id": user.get("id")})
        raise HTTPException(400, "admin_has_no_organization")

    try:
        content = await file.read()

        if not content:
            logger.warning("admin.upload_logo_failed: empty_file", extra={"org_id": org_id})
            raise HTTPException(400, "empty_file")

        if len(content) > MAX_IMAGE_BYTES:
            logger.warning("admin.upload_logo_failed: file_too_large", extra={"org_id": org_id, "size": len(content)})
            raise HTTPException(413, "file_too_large")

        # Detect image type
        try:
            with Image.open(BytesIO(content)) as img:
                detected_type = img.format.lower() if img.format else None
        except Exception as e:
            logger.warning("admin.upload_logo_failed: pil_open_error", extra={"org_id": org_id, "error": str(e)})
            detected_type = None

        if detected_type not in ALLOWED_IMAGE_TYPES:
            logger.warning(f"admin.upload_logo_failed: invalid_image_type - {detected_type}", extra={"org_id": org_id, "type": detected_type})
            raise HTTPException(400, f"tipo_de_imagen_invalido_{detected_type}" if detected_type else "archivo_no_es_una_imagen_valida")

        import config
        storage_base = Path(config.STORAGE_PATH)
        org_dir = storage_base / "orgs" / str(org_id)
        org_dir.mkdir(parents=True, exist_ok=True)
        
        logo_path = org_dir / "logo.png"
        
        # GAP-L1-01: Atomic file write and consistency guard
        try:
            with file_transaction(logo_path):
                # Convert to PNG for consistency in PDF 
                # Convert in-memory first to avoid file lock issues during PIL save
                buffer = BytesIO()
                with Image.open(BytesIO(content)) as img:
                    img.save(buffer, format="PNG")
                
                import tempfile
                import os
                from file_processing.dispatcher import process_file
                
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    tmp.write(buffer.getvalue())
                    tmp_name = tmp.name
                    
                try:
                    opt_path = process_file(tmp_name, "logo")
                    with open(opt_path, "rb") as f:
                        opt_bytes = f.read()

                    from payroll_core import save_bytes_atomically
                    save_bytes_atomically(opt_bytes, logo_path)
                finally:
                    if os.path.exists(opt_path):
                        os.remove(opt_path)
                    if os.path.exists(tmp_name):
                        try: os.remove(tmp_name)
                        except: pass

                with safe_transaction(db):
                    db.execute(
                        text("UPDATE organizations SET logo_path = :path WHERE id = :oid"),
                        {"path": str(logo_path), "oid": org_id}
                    )
                    audit(
                        db=db,
                        organization_id=org_id,
                        actor_type="admin",
                        actor_id=user["id"],
                        action="UPLOAD_COMPANY_LOGO",
                        entity_id=org_id,
                        data={"path": str(logo_path)}
                    )
        except Exception:
             # file_transaction will remove logo_path if it was just created
             raise

        logger.info("admin.upload_logo_success", extra={"org_id": org_id, "path": str(logo_path)})
        return {
            "status": "ok",
            "path": str(logo_path)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("admin.upload_logo_failed_fatal", extra={"org_id": org_id})
        raise HTTPException(500, "error_al_subir_logo")

@router.get("/logo")
async def get_company_logo(
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Serve the company logo.
    """
    org_id = user["organization_id"]
    from fastapi.responses import FileResponse

    row = db.execute(
        text("SELECT logo_path FROM organizations WHERE id = :id"),
        {"id": org_id}
    ).fetchone()

    if not row or not row.logo_path:
        raise HTTPException(404, "logo_no_encontrado")

    l_path = Path(row.logo_path)
    if not l_path.exists():
        raise HTTPException(404, "archivo_logo_no_encontrado")

    return FileResponse(str(l_path), media_type="image/png")


@router.get("/organization")
async def get_organization_details(
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Fetch organization details (name, cuit).
    """
    org_id = user["organization_id"]
    row = db.execute(
        text("SELECT id, name, cuit, logo_path, email, address, phone, website, city, province, zip_code, activity FROM organizations WHERE id = :id"),
        {"id": org_id}
    ).mappings().fetchone()

    if not row:
        raise HTTPException(404, "org_not_found")

    return {
        "id": str(row["id"]),
        "name": row["name"],
        "cuit": row["cuit"],
        "logo_path": row["logo_path"],
        "email": row["email"],
        "address": row["address"],
        "phone": row["phone"],
        "website": row["website"],
        "city": row["city"],
        "province": row["province"],
        "zip_code": row["zip_code"],
        "activity": row["activity"]
    }


@router.patch("/organization")
async def update_organization_details(
    payload: Dict[str, str],
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Update organization details.
    """
    org_id = user["organization_id"]
    updates = []
    params = {"oid": org_id}

    fields = ["name", "cuit", "email", "address", "phone", "website", "city", "province", "zip_code", "activity"]
    for f in fields:
        val = payload.get(f)
        if val is not None:
            updates.append(f"{f} = :{f}")
            params[f] = val

    if not updates:
        raise HTTPException(400, "datos_requeridos")

    with safe_transaction(db):
        sql = f"UPDATE organizations SET {', '.join(updates)} WHERE id = :oid"
        db.execute(text(sql), params)

        # Synchronize admin user email if organization email changed
        if "email" in params:
            db.execute(text("""
                UPDATE users 
                SET email = :email 
                WHERE organization_id = :oid AND role = 'admin'
            """), {"email": params["email"], "oid": org_id})

        audit(
            db=db,
            organization_id=org_id,
            actor_type="admin",
            actor_id=user["id"],
            action="UPDATE_ORGANIZATION_DETAILS",
            entity_id=org_id,
            data=payload
        )

    return {"status": "ok"}

