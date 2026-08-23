"""
Legajo API â€” endpoints for mass employee import/export.
"""

import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel

from payroll_core import get_db, require_auth, logger
from models import ImportJob, ImportJobRow, ImportJobStatus, ImportMode
from services.legajo.import_service import ImportService
from services.legajo.exporters import ExporterFactory

router = APIRouter(prefix="/api/legajo", tags=["legajo"])

# =========================================================
# SCHEMAS
# =========================================================

class ImportJobSummary(BaseModel):
    id: str
    status: str
    original_filename: Optional[str]
    total_rows: int
    valid_rows: int
    invalid_rows: int
    warning_rows: int
    inserted_count: int
    updated_count: int
    created_at: datetime
    import_mode: str
    rows: List["ImportRowDetail"] = []

    class Config:
        from_attributes = True

class ImportRowDetail(BaseModel):
    id: str
    source_row_number: int
    external_key: Optional[str]
    planned_action: str
    resolution_status: str
    normalized_data_json: dict
    matching_result_json: Optional[dict] = {}
    validation_errors_json: List[Any]
    validation_warnings_json: List[Any]

    class Config:
        from_attributes = True


class ExecuteRequest(BaseModel):
    job_id: str
    selected_rows: Optional[List[int]] = None

# =========================================================
# ENDPOINTS
# =========================================================

MAX_FILE_SIZE = 20 * 1024 * 1024 # 20MB
ALLOWED_MIME_TYPES = [
    "text/csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "text/plain"
]

@router.post("/preview", response_model=ImportJobSummary)
async def preview_legajo(
    file: UploadFile = File(...),
    mode: str = Query("merge", regex="^(merge|replace)$"),
    db: Session = Depends(get_db),
    auth = Depends(require_auth)
):
    """Step 1: Upload file, validate security, and generate Preview snapshot."""
    # 1. Security: Size Validation
    # NOTE: file.size might be None in some versions of Starlette/FastAPI, 
    # we read a bit to check if it's too large if size is missing.
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="El archivo excede el lÃ­mite de 5MB.")

    # 2. Security: MIME Validation
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400, 
            detail=f"Tipo de archivo no permitido: {file.content_type}. Use CSV, Excel o TXT."
        )

    org_id = auth["organization_id"]
    user_id = auth["id"]
    service = ImportService(db)
    
    try:
        job = service.create_import_job(org_id, user_id, file.filename, content, ImportMode(mode))
        
        # Ensure imports directory exists
        os.makedirs(os.path.join("storage", "imports"), exist_ok=True)
        
        storage_path = os.path.join("storage", "imports", f"{job.id}_{file.filename}")
        with open(storage_path, "wb") as f:
            f.write(content)
            
        job.stored_file_path = storage_path
        db.commit()
        
        # Process to preview (in-memory parsing/validation)
        service.process_file_to_preview(job.id, storage_path)
        return job
    except Exception as e:
        logger.exception("legajo.preview_failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/import/jobs", response_model=List[ImportJobSummary])
def list_import_jobs(limit: int = 10, db: Session = Depends(get_db), auth = Depends(require_auth)):
    org_id = auth["organization_id"]
    return db.query(ImportJob).filter(ImportJob.organization_id == org_id).order_by(ImportJob.created_at.desc()).limit(limit).all()


@router.get("/import/jobs/{job_id}", response_model=ImportJobSummary)
def get_job_status(job_id: str, db: Session = Depends(get_db), auth = Depends(require_auth)):
    org_id = auth["organization_id"]
    job = db.query(ImportJob).filter(ImportJob.id == job_id, ImportJob.organization_id == org_id).first()
    if not job: raise HTTPException(status_code=404, detail="job_not_found")
    return job


@router.get("/import/jobs/{job_id}/rows", response_model=List[ImportRowDetail])
def get_job_rows(
    job_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    auth = Depends(require_auth)
):
    org_id = auth["organization_id"]
    job_exists = db.query(ImportJob).filter(ImportJob.id == job_id, ImportJob.organization_id == org_id).count()
    if not job_exists: raise HTTPException(status_code=404, detail="job_not_found")

    query = db.query(ImportJobRow).filter(ImportJobRow.import_job_id == job_id)
    if status_filter: query = query.filter(ImportJobRow.planned_action == status_filter)
    return query.order_by(ImportJobRow.source_row_number).offset((page-1)*page_size).limit(page_size).all()


@router.post("/execute")
def execute_import(
    body: ExecuteRequest,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_auth)
):
    """Encola un job de importación para procesamiento en segundo plano."""
    if body.selected_rows is not None and not body.selected_rows:
        raise HTTPException(400, "Debe seleccionar al menos un registro para importar.")

    job = db.query(ImportJob).filter(
        ImportJob.id == body.job_id,
        ImportJob.organization_id == auth["organization_id"]
    ).first()

    if not job:
        raise HTTPException(404, "job_not_found")

    if job.status in (ImportJobStatus.queued, ImportJobStatus.processing):
        raise HTTPException(409, "job_already_queued")

    if job.status not in (ImportJobStatus.preview_ready, ImportJobStatus.failed):
        raise HTTPException(400, f"El trabajo está en un estado inválido para ejecutar: {job.status}")

    job.operation_type = "execute"
    job.status = ImportJobStatus.queued
    job.metadata_json = job.metadata_json or {}
    job.metadata_json["execute_selection"] = body.selected_rows
    job.metadata_json["queue_attempts"] = 0
    db.commit()

    return JSONResponse(
        status_code=202,
        content={
            "status": "queued",
            "job_id": job.id,
            "location": f"/api/legajo/import/jobs/{job.id}"
        }
    )


@router.post("/preview-execution")
def preview_execution(
    body: ExecuteRequest,
    db: Session = Depends(get_db),
    auth: dict = Depends(require_auth)
):
    """Returns the planned impact summary for a specific subset of rows."""
    service = ImportService(db)
    try:
        summary = service.get_execution_summary(
            job_id=body.job_id,
            selected_rows=body.selected_rows
        )
        return summary
    except Exception as e:
        logger.error(f"legajo.preview_execution_failed: {e}")
        raise HTTPException(400, str(e))


@router.get("/export")
def export_legajo(
    format: str = Query("csv", regex="^(csv|xlsx|txt|isis_txt|isis_xlsx)$"), 
    debug: bool = Query(False),
    db: Session = Depends(get_db), 
    auth = Depends(require_auth)
):
    """Downloads the entire legajo database for the organization."""
    org_id = auth["organization_id"]

    try:
        service = ImportService(db)
        records = service.fetch_export_data(org_id)
        
        exporter = ExporterFactory.get_exporter(format)
        mode = "debug" if debug else "business"
        content = exporter.export(records, mode=mode)
        
        # Determine filename and media type
        is_isis = "isis" in format
        ts = datetime.now().strftime("%Y%m%d")
        ext = "xlsx" if "xlsx" in format else ("txt" if "txt" in format else "csv")
        filename = f"{'isis_' if is_isis else ''}legajo_export_{ts}.{ext}"
        
        media_map = {
            "csv": "text/csv",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "isis_xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "txt": "text/plain",
            "isis_txt": "text/plain"
        }
        
        return Response(
            content=content,
            media_type=media_map.get(format, "application/octet-stream"),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.exception(f"legajo.export_failed format={format}")
        raise HTTPException(status_code=500, detail=str(e))
