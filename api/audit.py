"""
Corporate Audit Trail API
Provides structured transparency for digital signatures, including OCSP/CRL validation results.
"""

from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from payroll_core import get_db, require_auth
from modules.pdf_reports import generate_audit_pdf

router = APIRouter(prefix="/api/audit", tags=["audit"])

@router.get("/{verification_id}/pdf")
async def download_audit_pdf_report(
    verification_id: str,
    db: Session = Depends(get_db),
    user: Dict = Depends(require_auth)
):
    """
    C-004 FIX: Requires authentication. Downloads the Audit PDF report.
    Validates that the requesting user belongs to the same organization as the receipt.
    """
    row = db.execute(text("""
        SELECT e.*, o.name as organization_name, r.organization_id
        FROM signature_evidence e
        JOIN payroll_receipts r ON e.receipt_id = r.id
        JOIN organizations o ON r.organization_id = o.id
        WHERE e.verification_id = :vid
    """), {"vid": verification_id}).mappings().fetchone()

    if not row:
        raise HTTPException(404, "verificacion_no_encontrada")

    # C-004: Validate org membership
    if str(user.get("organization_id")) != str(row["organization_id"]):
        raise HTTPException(403, "not_authorized_for_this_organization")
    
    # Generate PDF
    pdf_buffer = generate_audit_pdf(dict(row))
    
    filename = f"auditoria_{verification_id[:8]}.pdf"
    return StreamingResponse(
        pdf_buffer, 
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/{document_id}")
async def get_document_audit_trail(
    document_id: str,
    db: Session = Depends(get_db),
    user: Dict = Depends(require_auth)
):
    """
    Returns the complete audit trail for a document, including cryptographic evidence.
    Note: document_id corresponds to the receipt_id in the system.
    """
    # 1. Verify existence and permissions (simplification: if you can view it, you can audit it)
    # In a real multi-tenant system, we should verify organization_id here.
    
    rows = db.execute(text("""
        SELECT 
            e.signer_full_name, e.signer_cuil, e.signed_at, 
            e.cert_fingerprint_sha256, e.cert_serial, 
            e.validation_status, e.ocsp_status, e.crl_status,
            e.tsa_timestamp, e.signing_method,
            e.validation_checked_at
        FROM signature_evidence e
        JOIN payroll_receipts r ON e.receipt_id = r.id
        WHERE e.receipt_id = :rid AND r.organization_id = :org_id
        ORDER BY e.signed_at ASC
    """), {"rid": document_id, "org_id": user["organization_id"]}).mappings().fetchall()

    if not rows:
        # Check if the receipt exists at least
        receipt = db.execute(text("SELECT id FROM payroll_receipts WHERE id = :rid AND organization_id = :org_id"), 
                             {"rid": document_id, "org_id": user["organization_id"]}).fetchone()
        if not receipt:
            raise HTTPException(404, "documento_no_encontrado")
        
    signatures = []
    for r in rows:
        signatures.append({
            "role": "employee", # Currently evidence is primarily for employees
            "signed_at": r["signed_at"].isoformat() if r["signed_at"] else None,
            "certificate_fingerprint": r["cert_fingerprint_sha256"],
            "certificate_serial": r["cert_serial"],
            "validation_status": r["validation_status"],
            "tsa_timestamp": r["tsa_timestamp"].isoformat() if r["tsa_timestamp"] else None,
            "ocsp_status": r["ocsp_status"],
            "crl_status": r["crl_status"],
            "signing_method": r["signing_method"],
            "checked_at": r["validation_checked_at"].isoformat() if r["validation_checked_at"] else None
        })

    return {
        "document_id": document_id,
        "signatures": signatures
    }
