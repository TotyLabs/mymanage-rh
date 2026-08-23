"""
Organization-specific public/shared API (Logo access, etc).
"""
import os
from pathlib import Path
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from io import BytesIO
from PIL import Image
import tempfile
from pydantic import BaseModel, EmailStr, Field

class OrganizationUpdateRequest(BaseModel):
    name: Optional[str] = None
    cuit: Optional[str] = None
    email: Optional[EmailStr] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    zip_code: Optional[str] = None
    activity: Optional[str] = None
    accept_tos: Optional[bool] = None

from payroll_core import (
    get_db,
    require_auth,
    require_admin,
    audit,
    file_transaction,
    safe_transaction,
    logger
)
import config

router = APIRouter(prefix="/api/organizations", tags=["organizations"])

ALLOWED_IMAGE_TYPES = {"png", "jpeg", "jpg", "webp", "gif", "bmp", "tiff", "mpo", "jfif"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024

@router.get("/{org_id}/logo")
async def get_org_logo(
    org_id: str,
    db: Session = Depends(get_db)
):
    """
    Publicly (or widely) accessible logo path.
    """
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

@router.post("/{org_id}/logo")
async def upload_org_logo(
    org_id: str,
    file: UploadFile = File(...),
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Bridge endpoint to match frontend expectations.
    Ensures that the admin uploading the logo belongs to the same organization.
    """
    if str(user.get("organization_id")) != str(org_id):
        raise HTTPException(403, "not_authorized_for_this_organization")

    content = await file.read()
    if not content:
        raise HTTPException(400, "empty_file")

    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "file_too_large")

    try:
        with Image.open(BytesIO(content)) as img:
            detected_type = img.format.lower() if img.format else None
    except Exception:
        detected_type = None

    if detected_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, "invalid_image_type")

    storage_base = Path(config.STORAGE_PATH)
    org_dir = storage_base / "orgs" / str(org_id)
    org_dir.mkdir(parents=True, exist_ok=True)
    
    logo_path = org_dir / "logo.png"
    
    try:
        with file_transaction(logo_path):
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
         raise

    return {"status": "ok", "path": str(logo_path)}

@router.patch("/me")
async def update_my_organization(
    body: OrganizationUpdateRequest,
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Onboarding endpoint: allows updating basic company data and accepting TOS.
    """
    org_id = user.get("organization_id")
    user_id = user.get("id")

    with safe_transaction(db):
        # 1. Update Organization data
        update_fields = {}
        fields = ["name", "cuit", "email", "address", "phone", "website", "city", "province", "zip_code", "activity"]
        for f in fields:
            val = getattr(body, f)
            if val is not None:
                update_fields[f] = str(val)

        if update_fields:
            set_clause = ", ".join([f"{f} = :{f}" for f in update_fields.keys()])
            db.execute(
                text(f"UPDATE organizations SET {set_clause} WHERE id = :oid"),
                {**update_fields, "oid": org_id}
            )

            # Synchronize admin user email if organization email changed
            if body.email:
                db.execute(text("""
                    UPDATE users 
                    SET email = :email 
                    WHERE organization_id = :oid AND role = 'admin'
                """), {"email": str(body.email), "oid": org_id})

        # 2. Accept TOS for the current admin user
        if body.accept_tos:
            db.execute(text("""
                UPDATE users 
                SET tos_accepted = true, 
                    tos_accepted_at = NOW(),
                    tos_version = '1.0'
                WHERE id = :uid
            """), {"uid": user_id})

        # 3. Audit
        audit(
            db=db,
            organization_id=org_id,
            actor_type="admin",
            actor_id=user_id,
            action="COMPANY_ONBOARDING_UPDATE",
            entity_id=org_id,
            data={**update_fields, "tos_accepted": body.accept_tos}
        )

    return {"status": "ok"}


@router.delete("/me")
async def delete_my_organization(
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Elimina la organización actual (soft delete) y todos sus datos asociados."""
    org_id = user["organization_id"]
    user_id = user["id"]
    
    try:
        with db.begin():
            # 1. Soft delete all employees
            db.execute(
                text("UPDATE employees SET is_deleted = true, deleted_at = NOW() WHERE organization_id = :org AND is_deleted = false"),
                {"org": org_id}
            )
            
            # 2. Soft delete all users in the organization
            db.execute(
                text("UPDATE users SET is_deleted = true, deleted_at = NOW() WHERE organization_id = :org AND is_deleted = false"),
                {"org": org_id}
            )
            
            # 3. Deactivate the organization
            db.execute(
                text("UPDATE organizations SET is_active = false WHERE id = :org"),
                {"org": org_id}
            )
            
            # 4. Audit
            audit(
                db=db,
                organization_id=org_id,
                actor_type="admin",
                actor_id=user_id,
                action="ORGANIZATION_DELETED",
                entity_id=org_id,
                data={"action": "soft_delete"}
            )
    except Exception as e:
        logger.exception("organizations.delete_error")
        raise HTTPException(status_code=500, detail=f"Error al eliminar la cuenta: {str(e)}")
    
    return {"status": "ok", "message": "Cuenta eliminada correctamente"}
