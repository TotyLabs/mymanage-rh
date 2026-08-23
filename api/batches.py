from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from payroll_core import get_db, require_admin, logger
from services.receipt_service import process_payroll_batch
from services.document_service import DocumentService

router = APIRouter(prefix="/api/batches", tags=["batches"])

@router.post("/upload")
async def upload_batch(
    organization_id: str = Form(...),
    period_label: str = Form(..., description="Etiqueta del período (ej: Enero 2026)"),
    document_type: str = Form("PAYROLL", description="Tipo de documento: PAYROLL, TRANSFER, ART, UNEMPLOYMENT, MISC"),
    pdf: UploadFile = File(...), # We keep 'pdf' for backward compatibility in the form field name
    user: Dict = Depends(require_admin),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    V4.1 UNIFIED HUB: Directs the file to the appropriate engine based on document_type.
    """
    
    # Security: Ensure admin belongs to the organization
    safe_org_id = user["organization_id"]
    if str(safe_org_id) != organization_id:
        logger.warning(
            "security.unauthorized_batch_upload",
            extra={
                "admin_id": user["id"],
                "requested_org": organization_id,
                "admin_org": safe_org_id
            }
        )
        # We enforce the safe_org_id regardless of form input for security
        organization_id = str(safe_org_id)

    # 1. Logic branch by document_type
    doc_type = document_type.upper()
    valid_types = ["PAYROLL", "TRANSFER", "ART", "UNEMPLOYMENT", "MISC"]
    if doc_type not in valid_types:
        raise HTTPException(400, f"tipo_de_documento_invalido: {document_type}")

    # 2. File extraction
    import tempfile
    import shutil
    import os
    
    # PAYROLL still requires PDF
    if doc_type == "PAYROLL" and not pdf.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "payroll_requires_pdf")

    try:
        # Read file bytes
        content = await pdf.read()
        if not content:
            raise HTTPException(400, "empty_file")

        # --- NEW: RUN PDF OPTIMIZATION VIA file_processing PIPELINE ---
        from file_processing.dispatcher import process_file
        
        # Write to temp file for optimization
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf" if pdf.filename.lower().endswith(".pdf") else "") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            # We determine file_type loosely based on extension
            file_type_for_opt = "pdf" if pdf.filename.lower().endswith(".pdf") else "excel" if pdf.filename.lower().endswith((".xls", ".xlsx")) else "default"
            
            # Execute central dispatch processing
            opt_path = process_file(tmp_path, file_type_for_opt)
            
            # Read optimized bytes back into memory for the rest of upload pipeline
            with open(opt_path, "rb") as opt_f:
                content = opt_f.read()
        finally:
            # Assure clean up of temporary assets
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            if 'opt_path' in locals() and os.path.exists(opt_path) and opt_path != tmp_path:
                os.remove(opt_path)
        # -------------------------------------------------------------

        # 3. Execution branch
        if doc_type == "PAYROLL":
            # Traditional split/OCR flow
            result = process_payroll_batch(
                db=db,
                organization_id=organization_id,
                period_label=period_label.strip(),
                file_bytes=content,
                original_filename=pdf.filename,
                background_tasks=background_tasks # Pass background tasks
            )
        else:
            # Unified Document Hub flow (Generic Document)
            result = DocumentService.save_document(
                db=db,
                organization_id=organization_id,
                doc_type=doc_type,
                file_bytes=content,
                original_filename=pdf.filename,
                period_label=period_label.strip(),
                uploaded_by=user
            )
        
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"api.batches.upload_failed: {doc_type}")
        raise HTTPException(500, f"error_processing_batch: {str(e)}")
