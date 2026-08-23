from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, List, Optional
from payroll_core import get_db, require_admin, require_auth, logger
from services.document_service import DocumentService, DocumentIntegrityError
from services.encryption_service import EncryptionService

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.get("/list")
async def list_documents(
    doc_type: str = None,
    include_archived: bool = Query(False),
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Lists documents for the unified hub. Filters by status and type.
    """
    org_id = user["organization_id"]
    
    query = """
        SELECT id, doc_type, file_name, period_label, created_at, metadata, status 
        FROM company_documents 
        WHERE organization_id = :org AND status != 'DELETED'
    """
    params = {"org": org_id}
    
    if not include_archived:
        query += " AND status = 'ACTIVE'"
    
    if doc_type:
        query += " AND doc_type = :type"
        params["type"] = doc_type.upper()
        
    query += " ORDER BY created_at DESC"
    
    rows = db.execute(text(query), params).fetchall()
    
    return {
        "documents": [
            {
                "id": str(r.id),
                "doc_type": r.doc_type,
                "file_name": r.file_name,
                "period_label": r.period_label,
                "created_at": r.created_at.isoformat(),
                "metadata": r.metadata,
                "status": r.status
            } for r in rows
        ]
    }

@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Downloads a document with on-read integrity verification.
    """
    from fastapi.responses import FileResponse
    import os
    
    org_id = user["organization_id"]

    # Authorization: allow admins, or the employee who uploaded the document
    row = db.execute(text("SELECT organization_id, metadata FROM company_documents WHERE id = :id"), {"id": document_id}).fetchone()
    if not row:
        raise HTTPException(404, "documento_no_encontrado")

    # Ensure organization matches
    if str(row.organization_id) != str(org_id):
        raise HTTPException(404, "documento_no_encontrado")

    is_admin = user.get("role") == "admin"
    uploaded_by_user_id = None
    try:
        uploaded_by_user_id = (row.metadata or {}).get("uploaded_by", {}).get("user_id")
    except Exception:
        uploaded_by_user_id = None

    # Allow admins or any authenticated user in the same organization to download
    # (employees should be able to view/sign company documents in their org).
    # Keep the organization check above; no further ownership check required.

    try:
        file_path, original_name, is_temp = DocumentService.get_document_file(
            db,
            document_id,
            str(org_id),
            actor_id=str(user.get("id")) if user.get("id") else None,
            actor_type="admin" if is_admin else "employee",
            return_temp_flag=True,
        )
        
        if not file_path or not os.path.exists(file_path):
            raise HTTPException(404, "documento_no_encontrado")
            
        return FileResponse(
            file_path,
            filename=original_name,
            headers={
                "Content-Disposition": f"attachment; filename={original_name}",
                "X-Document-Integrity": "verified"
            },
            background=BackgroundTask(EncryptionService.cleanup_temp_file, file_path) if is_temp else None,
        )
    except DocumentIntegrityError as e:
        logger.critical(f"INTEGRITY_FAILURE_DURING_CLIENT_DOWNLOAD: {str(e)}")
        raise HTTPException(status_code=500, detail="fallo_de_integridad_detectado_contacte_soporte")
    except Exception as e:
        logger.error(f"download_failed: {str(e)}")
        raise HTTPException(500, "error_interno_en_descarga")


@router.get("/{document_id}/preview")
async def preview_document(
    document_id: str,
    user: Dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    Preview a document inline. Currently restricted to Fondo de Desempleo (UNEMPLOYMENT)
    to avoid changing existing recibos flow.
    """
    from fastapi.responses import FileResponse
    import os

    org_id = user["organization_id"]

    row = db.execute(text("SELECT organization_id, metadata, doc_type FROM company_documents WHERE id = :id"), {"id": document_id}).fetchone()
    if not row:
        raise HTTPException(404, "documento_no_encontrado")

    if str(row.organization_id) != str(org_id):
        raise HTTPException(404, "documento_no_encontrado")

    doc_type = (row.doc_type or "").upper()
    if doc_type != 'UNEMPLOYMENT':
        raise HTTPException(400, "preview_no_disponible_para_este_tipo_de_documento")

    try:
        file_path, original_name, is_temp = DocumentService.get_document_file(
            db,
            document_id,
            str(org_id),
            actor_id=str(user.get("id")) if user.get("id") else None,
            actor_type="employee",
            return_temp_flag=True,
        )

        if not file_path or not os.path.exists(file_path):
            raise HTTPException(404, "documento_no_encontrado")

        return FileResponse(
            file_path,
            filename=original_name,
            headers={
                "Content-Disposition": f"inline; filename={original_name}",
                "X-Document-Integrity": "verified"
            },
            background=BackgroundTask(EncryptionService.cleanup_temp_file, file_path) if is_temp else None,
        )
    except DocumentIntegrityError as e:
        logger.critical(f"INTEGRITY_FAILURE_DURING_CLIENT_PREVIEW: {str(e)}")
        raise HTTPException(status_code=500, detail="fallo_de_integridad_detectado_contacte_soporte")
    except Exception as e:
        logger.error(f"preview_failed: {str(e)}")
        raise HTTPException(500, "error_interno_en_previsualizacion")

@router.post("/{document_id}/archive")
async def archive_document(
    document_id: str,
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Moves document to ARCHIVED state."""
    try:
        DocumentService.update_status(db, document_id, str(user["organization_id"]), "ARCHIVED")
        return {"status": "success", "message": "document_archived"}
    except Exception as e:
        raise HTTPException(400, str(e))

@router.post("/{document_id}/restore")
async def restore_document(
    document_id: str,
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Moves document back to ACTIVE state."""
    try:
        DocumentService.update_status(db, document_id, str(user["organization_id"]), "ACTIVE")
        return {"status": "success", "message": "document_restored"}
    except Exception as e:
        raise HTTPException(400, str(e))

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Soft deletes document (DELETED state)."""
    try:
        DocumentService.update_status(db, document_id, str(user["organization_id"]), "DELETED")
        return {"status": "success", "message": "document_deleted"}
    except Exception as e:
        raise HTTPException(400, str(e))
