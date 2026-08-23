import os
import re
import fitz
import hashlib
import secrets
import logging
import tempfile
import time
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, BackgroundTasks
import json
from datetime import datetime, timezone

from payroll_core import (
    logger,
    safe_transaction,
    file_transaction,
    audit,
    compute_file_sha256,
    safe_write_file,
    safe_remove_file,
    create_signature_request,
    utc_now,
    ALLOWED_STORAGE_DIR,
    build_storage_path
)
from models.tables import PayrollBatch, PayrollReceipt, Employee, User
from models.receipts import Receipt
import config

# =====================================================================
# Helper Functions
# =====================================================================

def delete_batch_files(db: Session, batch_id: str) -> None:
    """
    Safely deletes all receipt files associated with a batch.
    Uses Windows-safe retry logic to handle file locks.
    """
    try:
        # Get all receipt files for this batch
        receipts = db.execute(
            text("SELECT receipt_pdf_path FROM payroll_receipts WHERE batch_id = :bid"),
            {"bid": batch_id}
        ).fetchall()
        
        for receipt in receipts:
            if not receipt or not receipt.receipt_pdf_path:
                continue
            
            file_path = receipt.receipt_pdf_path
            # safe_remove_file handles non-existent files gracefully
            safe_remove_file(file_path, max_retries=5)
    except Exception as e:
        logger.error(f"batch.file_cleanup_error batch_id={batch_id} err={e}")
        # Don't raise - allow batch deletion to proceed even if file cleanup has issues


# =====================================================================
# OCR Patterns
# =====================================================================
DNI_PATTERN = re.compile(r"(?:\D|^)(\d{7,8})(?:\D|$)")  # 7-8 digits not part of larger number
CUIL_PATTERN = re.compile(r"(\d{2}[-.\\s]?\d{7,8}[-.\\s]?\d)")
# Look for DNI or Documento or CUIL nearby
DNI_CONTEXT_PATTERN = re.compile(
    r"(DNI|DOCUMENTO|DOC|D\.N\.I|CUIL|CUIT)\s*[:.-]?\s*(\d{7,8})", re.IGNORECASE
)

# GAP-007: Keywords that identify the EMPLOYER section â€” blocks in these sections are discarded
EMPLOYER_KEYWORDS = re.compile(
    r"(razÃ³n\s*social|razon\s*social|empleador|empresa|cuit\s*empresa|"
    r"cuit\s*empleador|r\.?c\.?s\.?|r\s*social|establecimiento|"
    r"nombre\s*comercial|razÃ³n\s*del\s*empleador)",
    re.IGNORECASE,
)

# Threshold: blocks within the top N% of the page height are considered "header" blocks.
# 20% is more conservative than the previous 100px fixed threshold.
TOP_PAGE_FRACTION = 0.20

# GAP-007: Explicit Scoring Anchors
CUIL_ANCHORS = re.compile(r"(CUIL|C\.U\.I\.L\.|IDENTIFICACION|IDENTIFICACI\u00d3N)", re.IGNORECASE)
NAME_ANCHORS = re.compile(r"(APELLIDO\s*Y\s*NOMBRE|NOMBRE|EMPLEADO)", re.IGNORECASE)
LEGAJO_ANCHORS = re.compile(r"(LEGAJO|FICHA|NRO\s*EMP)", re.IGNORECASE)


def normalize_dni(dni: str) -> str:
    """Cleans DNI from dots, dashes and spaces."""
    if not dni:
        return ""
    clean = re.sub(r"\D", "", str(dni))
    if len(clean) == 11:
        # Extract DNI from CUIL (middle 8 digits)
        return clean[2:10]
    return clean


def _is_employer_block(raw_text: str, y0: float, page_height: float) -> bool:
    """
    GAP-007: Returns True if this text block is likely the employer header.
    Checks both position (top fraction of page) and keyword presence.
    """
    # Top-of-page positional heuristic
    top_threshold = page_height * TOP_PAGE_FRACTION
    if y0 < top_threshold:
        return True
    # Employer keyword match anywhere in the block
    if EMPLOYER_KEYWORDS.search(raw_text):
        return True
    return False


def extract_dni_from_page(
    page, 
    employer_cuit: Optional[str] = None, 
    known_employee_dnis: Optional[List[str]] = None
) -> Optional[str]:
    """
    GAP-007: Extracts DNI using an EXPLICIT SCORING SYSTEM.
    Rules:
    - Equals Employer CUIT: -100 (Immediate rejection)
    - Matches Employee DB: +80
    - Near CUIL anchor: +50
    - Near Name anchor: +30
    - Top of page: -10 (Penalty)
    - CUIL format (11 digits): +20
    """
    all_text = page.get_text().strip()
    if not all_text:
        return "SCAN_REQUIRED"

    page_height = page.rect.height
    blocks = page.get_text("blocks")
    candidates = []

    # Pre-calculate normalized DB matches if provided
    db_set = set(known_employee_dnis) if known_employee_dnis else set()

    for b in blocks:
        # b = (x0, y0, x1, y1, "text", block_no, block_type)
        y0 = b[1]
        raw_text = b[4].strip()
        if not raw_text:
            continue

        # Detect potential identities in this block
        found_identities = []
        
        # 1. Look for CUILs
        for m in CUIL_PATTERN.finditer(raw_text):
            found_identities.append({"val": normalize_dni(m.group(1)), "type": "CUIL"})
            
        # 2. Look for Contextual DNIs
        for m in DNI_CONTEXT_PATTERN.finditer(raw_text):
            found_identities.append({"val": normalize_dni(m.group(2)), "type": "CONTEXT_DNI"})
            
        # 3. Bare DNIs (only if nothing else found to avoid noise)
        if not found_identities:
            for m in DNI_PATTERN.finditer(raw_text):
                found_identities.append({"val": normalize_dni(m.group(1)), "type": "BARE_DNI"})

        for ident in found_identities:
            val = ident["val"]
            score = 0
            reasons = []

            # RULE: Employer exclusion
            if employer_cuit and val == employer_cuit:
                score -= 100
                reasons.append("EQUALS_EMPLOYER")
            
            # RULE: DB Match
            if val in db_set:
                score += 80
                reasons.append("DB_MATCH")
                
            # RULE: CUIL Anchors
            if CUIL_ANCHORS.search(raw_text):
                score += 50
                reasons.append("NEAR_CUIL_ANCHOR")
                
            # RULE: Name Anchors
            if NAME_ANCHORS.search(raw_text) or LEGAJO_ANCHORS.search(raw_text):
                score += 30
                reasons.append("NEAR_IDENTITY_ANCHOR")
                
            # RULE: Top of page penalty (reduced from blind discard)
            if y0 < (page_height * TOP_PAGE_FRACTION):
                score -= 10
                reasons.append("TOP_PAGE_ZONE")
                
            # RULE: Format reliability
            if ident["type"] == "CUIL":
                score += 20
                reasons.append("CUIL_FORMAT")
            elif ident["type"] == "CONTEXT_DNI":
                score += 15
                reasons.append("CONTEXT_DNI_FORMAT")

            # RULE: Employer keyword penalty (if block contains company-related words)
            if EMPLOYER_KEYWORDS.search(raw_text):
                score -= 30
                reasons.append("EMPLOYER_KEYWORDS_IN_BLOCK")

            candidates.append({
                "val": val, 
                "score": score, 
                "reasons": reasons,
                "text": raw_text[:50]
            })

    if not candidates:
        return None

    # Sort by score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]

    # Threshold: Score must be positive to be considered a match
    if best["score"] <= 0:
        logger.debug(f"OCR: Best candidate {best['val']} rejected (Score {best['score']} <= 0)")
        return None

    logger.info(
        f"OCR match: {best['val']} | Score: {best['score']} | Reasons: {', '.join(best['reasons'])}"
    )
    return best["val"]


def has_employer_signature(pdf_bytes: bytes, page_index: int = 0) -> bool:
    """
    Detects if a PDF page already has an employer signature.
    Looks for images in the signature area (typically lower half of page).
    
    Returns True if signature is detected, False otherwise.
    """
    try:
        with fitz.open("pdf", pdf_bytes) as doc:
            if page_index >= doc.page_count:
                return False
            
            page = doc[page_index]
            
            # Get page dimensions
            page_height = page.rect.height
            
            # Signature areas are typically in the lower half
            # Look for images in the bottom 40% of the page
            signature_zone_y_start = page_height * 0.6
            
            # Get all images on the page using correct API
            try:
                image_list = page.get_images()
                for img_index in image_list:
                    # img_index is (xref, smask) tuple
                    try:
                        xref = img_index[0]
                        # Get image location on page
                        rect = page.get_image_bbox(xref)
                        
                        if rect:
                            img_y0 = min(rect.y0, rect.y1)
                            
                            # If image is in signature zone (lower 40%), it's likely a signature
                            if img_y0 >= signature_zone_y_start:
                                logger.info(f"Signature image detected in PDF page {page_index}")
                                return True
                    except Exception:
                        # Skip this image if we can't get its bbox
                        continue
            except Exception:
                # If image detection fails, continue to check drawings
                pass
            
            # No signature found
            return False
    except Exception as e:
        logger.warning(f"Could not detect signature in PDF: {e}")
        # On error, assume NO signature to be conservative
        return False

def process_payroll_batch(
    db: Session,
    organization_id: str,
    period_label: str,
    file_bytes: bytes,
    original_filename: str,
    background_tasks: Optional[BackgroundTasks] = None
) -> Dict[str, Any]:
    """
    Processes a payroll PDF batch:
    1. GAP-008: Detects duplicate batch by SHA-256 of the file.
    2. Saves original batch PDF.
    3. Splits into pages with per-page savepoint transactions (GAP-002).
    4. Extracts DNI/Name via OCR (GAP-007: improved employer exclusion).
    5. Creates records and performs Proactive Matching.
    6. Generates SignatureRequests for matched receipts.

    GAP-002: Each page is processed in its own nested transaction (savepoint).
    A single corrupt page does NOT roll back the entire batch.
    """
    # Phase 3 Fix: PDF Magic Byte Verification (Polyglot Protection)
    if not file_bytes.startswith(b'%PDF-'):
         logger.warning(f"security.invalid_magic_bytes: {original_filename} from org {organization_id}")
         raise HTTPException(400, "El archivo no es un PDF v\u00e1lido.")

    # Phase 3 Fix: Organization Storage Quota Enforcement
    # Default quota: 500MB per organization (config.STORAGE_QUOTA_MB)
    try:
        quota_mb = int(os.getenv("STORAGE_QUOTA_MB", "500"))
        current_usage = db.execute(text("""
            SELECT COALESCE(SUM(size_bytes), 0) FROM (
                SELECT (metadata->>'size_bytes')::bigint as size_bytes FROM company_documents WHERE organization_id = :org
                UNION ALL
                SELECT (receipt_metadata->>'size_bytes')::bigint FROM receipts WHERE company_id = :org
            ) as total
        """), {"org": organization_id}).scalar() or 0
        
        incoming_size = len(file_bytes)
        if (current_usage + incoming_size) > (quota_mb * 1024 * 1024):
             logger.error(f"quota.exceeded org={organization_id} usage={current_usage} incoming={incoming_size}")
             raise HTTPException(403, f"L\u00edmite de almacenamiento alcanzado ({quota_mb}MB). Contacte a soporte.")
    except HTTPException: raise
    except Exception as e:
        logger.warning(f"quota.check_failed: {e}")

    # P3: File size guard (from config, default 50MB)
    if len(file_bytes) > config.MAX_FILE_SIZE:
        max_mb = config.MAX_FILE_SIZE // (1024 * 1024)
        raise HTTPException(400, f"El archivo excede el l\u00edmite de {max_mb}MB")

    stats = {
        "total_pages": 0,
        "matched": 0,
        "pending_match": 0,
        "errors": 0,
    }
    alerts = []
    sample_urls = []

    # 1. Initialize Storage (Phase 3 Fix: Tenant Segregation)
    # 1. Initialize Storage (GAP-016 Fix: Industrial Segregation via Centralized Path Builder)
    # The actual folders are ensured inside build_storage_path()

    # GAP-008: Detect duplicate batch before saving
    batch_sha256 = hashlib.sha256(file_bytes).hexdigest()
    existing_batch = db.execute(text("""
        SELECT id, period_label, total_receipts, processed_receipts
        FROM payroll_batches
        WHERE organization_id = :org AND source_pdf_sha256 = :sha
        FOR UPDATE
    """), {"org": organization_id, "sha": batch_sha256}).fetchone()

    if existing_batch:
        actual_receipts = db.execute(
            text("SELECT COUNT(*) FROM payroll_receipts WHERE batch_id = :bid"),
            {"bid": existing_batch.id}
        ).scalar()
        
        if existing_batch.processed_receipts < existing_batch.total_receipts or actual_receipts == 0:
            # GAP-F03: Delete incomplete or empty batch and allow re-uploading
            logger.info(f"Deleting incomplete or empty batch {existing_batch.id} to allow re-upload")
            with safe_transaction(db):
                # First clean up all associated receipt files
                delete_batch_files(db, existing_batch.id)
                # Then delete the batch record from database
                db.execute(text("DELETE FROM payroll_batches WHERE id = :bid"), {"bid": existing_batch.id})
        else:
            # Unconditionally allow upload by archiving the old batch's SHA256 constraint.
            logger.info(f"Archiving batch {existing_batch.id} to allow re-upload")
            archived_sha = hashlib.sha256(f"{batch_sha256}_archived_{existing_batch.id}_{datetime.now().timestamp()}".encode('utf-8')).hexdigest()
            with safe_transaction(db):
                db.execute(text("UPDATE payroll_batches SET source_pdf_sha256 = :new_sha WHERE id = :bid"), {"new_sha": archived_sha, "bid": existing_batch.id})

    # 2. Save Original Batch Atomically
    batch_filename = (
        f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{original_filename}"
    )
    batch_path = build_storage_path(
        org_id=organization_id,
        category="batches",
        filename=batch_filename
    )
    batch_dir = os.path.dirname(batch_path)
    
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=batch_dir, suffix=".pdf")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(file_bytes)
        os.replace(tmp_path, batch_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    # 3. Open PDF from memory (avoids all batch_path lock issues on Windows)
    doc = None
    try:
        doc = fitz.open("pdf", file_bytes)
        if doc.is_encrypted:
            raise HTTPException(400, "pdf_is_encrypted")

        total_pages = len(doc)
        stats["total_pages"] = total_pages
        
        # P3: Page count guard (from config)
        if total_pages > config.MAX_PDF_PAGES:
            doc.close()
            raise HTTPException(400, f"El PDF tiene {total_pages} páginas (máximo {config.MAX_PDF_PAGES})")
        
        doc.close() # Close memory doc, we re-open per page for isolation
        doc = None

        # 4. Create Batch record in its own transaction
        # ... (record creation)
        batch_id = None
        try:
            with safe_transaction(db):
                batch_id_res = db.execute(text("""
                    INSERT INTO payroll_batches (
                        organization_id, period_label, source_pdf_path,
                        source_pdf_sha256, total_receipts
                    )
                    VALUES (:org, :period_label, :path, :sha, :total)
                    RETURNING id
                """), {
                    "org": organization_id,
                    "period_label": period_label,
                    "path": batch_path,
                    "sha": batch_sha256,
                    "total": total_pages,
                })
                batch_id = batch_id_res.fetchone().id
        except IntegrityError:
            # Under concurrent exact same upload, bypassing error to allow duplicate unconditionally.
            import uuid
            with safe_transaction(db):
                retry_sha = f"{batch_sha256}_{uuid.uuid4().hex[:8]}"
                batch_id_res = db.execute(text("""
                    INSERT INTO payroll_batches (
                        organization_id, period_label, source_pdf_path,
                        source_pdf_sha256, total_receipts
                    )
                    VALUES (:org, :period_label, :path, :sha, :total)
                    RETURNING id
                """), {
                    "org": organization_id,
                    "period_label": period_label,
                    "path": batch_path,
                    "sha": retry_sha,
                    "total": total_pages,
                })
                batch_id = batch_id_res.fetchone().id

        # GAP-007: Pre-fetch employer identity for better extraction scoring
        org_data = db.execute(text("SELECT cuit FROM organizations WHERE id = :org"), {"org": organization_id}).fetchone()
        employer_cuit = normalize_dni(org_data.cuit) if org_data and org_data.cuit else None
        
        # GAP-007: Pre-fetch known employee identities for DB_MATCH scoring
        employee_rows = db.execute(text("SELECT dni, cuil FROM employees WHERE organization_id = :org AND is_deleted = false"), {"org": organization_id}).fetchall()
        known_dnis = []
        for er in employee_rows:
            if er.dni: known_dnis.append(normalize_dni(er.dni))
            if er.cuil: known_dnis.append(normalize_dni(er.cuil))

        # 5. GAP-002: Process each page
        processed_count = 0
        for i in range(total_pages):
            try:
                # GAP-L1-01: Fully isolated in-memory processing
                dni = None
                try:
                    with fitz.open("pdf", file_bytes) as src_doc:
                        page = src_doc[i]
                        dni = extract_dni_from_page(
                            page, 
                            employer_cuit=employer_cuit,
                            known_employee_dnis=known_dnis
                        )
                except Exception as e:
                    logger.error(f"batch.ocr_failed page={i+1} err={e}")

                if dni == "SCAN_REQUIRED":
                    dni = None
                    alerts.append(f"PÃ¡gina {i+1}: No se detectÃ³ texto (posible escaneo).")

                # Proactive Matching
                employee_id = None
                user_id = None
                status = "pending_match"
                full_name = None
                emp_row = None

                if dni:
                    emp_row = db.execute(text("""
                        SELECT e.id, (e.first_name || ' ' || COALESCE(e.last_name, '')) AS full_name,
                               u.id AS user_id, e.email, e.cuil, e.file_number
                        FROM employees e
                        LEFT JOIN users u ON u.employee_id = e.id
                        WHERE e.organization_id = :org AND e.dni = :dni AND e.is_deleted = false
                    """), {"org": organization_id, "dni": dni}).fetchone()

                    if emp_row:
                        employee_id = emp_row.id
                        full_name = emp_row.full_name
                        user_id = emp_row.user_id # New: User linked to this employee
                        # Check if employer signature is already present in the PDF
                        has_sig = has_employer_signature(file_bytes, i)
                        if has_sig:
                            status = "pending_employee_signature"
                            logger.info(f"batch: Employer signature detected, status=pending_employee_signature")
                        else:
                            status = "pending_employer_signature"
                        stats["matched"] += 1
                    else:
                        stats["pending_match"] += 1
                else:
                    stats["pending_match"] += 1

                # NEW: Determine more friendly filename based on match
                def sanitize(s):
                    return re.sub(r'[^a-zA-Z0-9_\-]', '_', str(s).strip().replace(' ', '_'))

                if full_name:
                    base_name = sanitize(full_name)
                elif dni:
                    base_name = f"DNI_{dni}"
                else:
                    base_name = f"receipt_{i+1}"
                
                # Append batch ID and page to ensure uniqueness
                page_filename = f"{base_name}_{str(batch_id)[:8]}_{i+1}.pdf"
                page_path = build_storage_path(
                    org_id=organization_id,
                    category="receipts",
                    filename=page_filename
                )

                # Save the page
                try:
                    with fitz.open("pdf", file_bytes) as src_doc:
                        src_doc.select([i])
                        page_bytes = src_doc.tobytes(garbage=4)
                    safe_write_file(page_path, page_bytes)
                except Exception as e:
                    logger.error(f"batch.page_write_failed page={i+1} path={page_path} err={e}")
                    raise e

                page_sha256 = compute_file_sha256(page_path)

                # GAP-002: Each page insert + SR creation in its own savepoint.
                # Prevent duplicate receipts by checking existing records before inserting.
                with safe_transaction(db):
                    # 1) Check duplicate by batch_id + page_number
                    existing = db.execute(text("""
                        SELECT id FROM payroll_receipts WHERE batch_id = :bid AND page_number = :pnum LIMIT 1
                    """), {"bid": batch_id, "pnum": i + 1}).fetchone()

                    if existing:
                        receipt_id = existing.id
                        logger.info(f"batch.page_skipped_duplicate batch={batch_id} page={i+1} receipt={receipt_id}")
                    else:
                        # 2) Check duplicate by organization + sha (same page content across batches)
                        existing_sha = db.execute(text("""
                            SELECT id FROM payroll_receipts WHERE organization_id = :oid AND receipt_pdf_sha256 = :sha LIMIT 1
                        """), {"oid": organization_id, "sha": page_sha256}).fetchone()

                        if existing_sha:
                            receipt_id = existing_sha.id
                            logger.info(f"batch.page_skipped_duplicate_by_sha org={organization_id} page={i+1} receipt={receipt_id}")
                        else:
                            receipt_id_res = db.execute(text("""
                                INSERT INTO payroll_receipts (
                                    batch_id, organization_id, employee_id, page_number,
                                    receipt_pdf_path, receipt_pdf_sha256, status, extracted_fields,
                                    snapshot_employee_name, snapshot_employee_dni,
                                    snapshot_employee_cuil, snapshot_employee_legajo,
                                    snapshot_created_at
                                )
                                VALUES (:bid, :oid, :eid, :pnum, :path, :sha, :status, :extra,
                                        :snap_name, :snap_dni, :snap_cuil, :snap_legajo, :snap_ts)
                                RETURNING id
                            """), {
                                "bid": batch_id,
                                "oid": organization_id,
                                "eid": employee_id,
                                "pnum": i + 1,
                                "path": page_path,
                                "sha": page_sha256,
                                "status": status,
                                "extra": json.dumps({
                                    "dni": dni,
                                    "periodo": period_label,
                                    "email": emp_row.email if emp_row else None
                                }),
                                "snap_name": full_name,
                                "snap_dni": dni,
                                "snap_cuil": emp_row.cuil if emp_row else None,
                                "snap_legajo": emp_row.file_number if emp_row else None,
                                "snap_ts": utc_now(),
                            })
                            receipt_id = receipt_id_res.fetchone().id

                            if employee_id:
                                sr = create_signature_request(
                                    db, str(receipt_id), organization_id, str(employee_id)
                                )
                                if len(sample_urls) < 5:
                                    sample_urls.append({
                                        "name": full_name,
                                        "url": sr["sign_url"],
                                    })

                                # Trigger notification if status is pending_employee_signature (employer signature detected)
                                if status == "pending_employee_signature" and background_tasks:
                                    from notifications.service import NotificationService
                                    notifier = NotificationService.get_instance()
                                    background_tasks.add_task(
                                        notifier.send_signature_pending_notification,
                                        receipt_id=str(receipt_id),
                                        organization_id=organization_id,
                                        employee_id=str(employee_id),
                                        employee_token=sr["token"]
                                    )

                                # --- New: Mirror to the 'receipts' Source of Truth table ---
                                if employee_id and user_id:
                                    db.execute(text("""
                                        INSERT INTO receipts (user_id, company_id, file_path, file_hash, receipt_metadata, status, created_at)
                                        VALUES (:uid, :cid, :path, :sha, :meta, :status, :now)
                                    """), {
                                        "uid": user_id,
                                        "cid": organization_id,
                                        "path": page_path,
                                        "sha": page_sha256,
                                        "meta": json.dumps({"dni": dni, "periodo": period_label}),
                                        "status": "pending", # Always pending at ingestion
                                        "now": utc_now()
                                    })

                processed_count += 1

            except HTTPException:
                raise  # Re-raise HTTP errors (e.g., file too large) as-is
            except Exception as page_err:
                # GAP-002: Individual page failure â€” log, mark error, continue
                stats["errors"] += 1
                alerts.append(f"PÃ¡gina {i+1}: Error al procesar - {str(page_err)[:100]}")
                logger.warning(
                    f"batch.page_error batch_id={batch_id} page={i+1} err={page_err}"
                )

        # 6. Update Batch processed count
        with safe_transaction(db):
            db.execute(text("""
                UPDATE payroll_batches
                SET processed_receipts = :proc
                WHERE id = :bid
            """), {"proc": processed_count, "bid": batch_id})

        return {
            "status": "success",
            "batch_id": str(batch_id),
            "stats": {
                "total_pages": stats["total_pages"],
                "matched": stats["matched"],
                "pending_match": stats["pending_match"],
                "errors": stats["errors"],
            },
            "alerts": alerts,
            "sample_urls": sample_urls,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error processing batch {original_filename}")
        raise HTTPException(500, f"Error al procesar el lote: {str(e)}")
    finally:
        if doc is not None:
            doc.close()
