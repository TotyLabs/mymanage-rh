"""
Signature Service - LÃ³gica de dominio para firma digital de recibos.

Este mÃ³dulo encapsula toda la lÃ³gica de negocio relacionada con:
- ValidaciÃ³n de tokens de firma
- VerificaciÃ³n de estado de signature requests
- Helpers especÃ­ficos del flujo de firma

Separado de core.py para mantener separaciÃ³n entre:
- Utilities tÃ©cnicas puras (core.py)
- LÃ³gica de dominio de negocio (services/)
"""

import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import timezone
from fastapi import HTTPException

from payroll_core import (
    hash_token,
    validate_token_format,
    utc_now,
    audit,
    logger,
)


def check_token_hash_misuse(db: Session, raw_normalized_token: str) -> None:
    """
    Detecta si alguien estÃ¡ usando token_hash directamente como token.
    
    Esto es un security issue porque el hash no deberÃ­a ser conocido
    por el usuario. Si esto sucede, alguien estÃ¡ leyendo la DB directamente.
    
    Args:
        db: Database session
        raw_normalized_token: Token normalizado (strip + lowercase)
        
    Raises:
        HTTPException: 400 si se detecta uso de hash como token
    """
    row_hash = db.execute(text("""
        SELECT id, receipt_id, organization_id, status, token_expires_at
        FROM signature_requests 
        WHERE token_hash = :raw 
        LIMIT 1
    """), {"raw": raw_normalized_token}).fetchone()
    
    if row_hash:
        logger.warning(
            "security.token_hash_used_as_token",
            extra={
                "event_type": "security.token_hash_used_as_token",
                "signature_request_id": str(row_hash.id),
                "receipt_id": str(row_hash.receipt_id),
                "organization_id": str(row_hash.organization_id),
                "detected_value": raw_normalized_token[:16] + "...",  # No loggear completo
            }
        )
        
        # Intentar auditar (best effort)
        try:
            audit(
                db,
                str(row_hash.organization_id),
                "system",
                None,
                "HASH_AS_TOKEN_DETECTED",
                str(row_hash.id),
                {"value": raw_normalized_token[:16] + "..."}  # Truncado por seguridad
            )
            db.commit()
        except Exception:
            db.rollback()
            # Don't fail on audit error
            pass
        
        raise HTTPException(400, "invalid_link_format")


def validate_and_fetch_signature_request(
    db: Session,
    token: str,
    for_update: bool = False
) -> Dict[str, Any]:
    """
    Centraliza validaciÃ³n completa de token de firma y fetch de datos.
    
    Este helper reemplaza ~40 lÃ­neas de cÃ³digo duplicado en cada endpoint.
    
    Flow:
    1. Valida formato del token
    2. Hashea el token
    3. Verifica que no sea un hash usado como token (security)
    4. Fetch signature_request con JOINs necesarios
    5. Verifica expiraciÃ³n y marca como expired si corresponde
    6. Retorna row data o raise HTTPException apropiada
    
    Args:
        db: Database session
        token: Token plano (hex de 64 caracteres)
        for_update: Si True, agrega FOR UPDATE lock para modificaciones
        
    Returns:
        Dict con datos completos del signature_request + employee + receipt
        
    Raises:
        HTTPException: 
            - 400 si formato invÃ¡lido o hash usado como token
            - 404 si token no existe
            - 410 si token expirÃ³
    """
    # 1. Validar formato
    validate_token_format(token)
    
    # 2. Hashear
    t_hash = hash_token(token)
    now = utc_now()
    
    # 3. Security check: no permitir hash usado como token
    raw_norm = token.strip().lower()
    check_token_hash_misuse(db, raw_norm)
    
    # 4. Fetch con JOINs optimizados
    lock_clause = "FOR UPDATE OF sr" if for_update else ""
    
    row = db.execute(text(f"""
        SELECT 
            sr.id as sr_id,
            sr.status as sr_status,
            sr.token_expires_at,
            sr.organization_id,
            COALESCE(sr.employee_id, nr.user_id) as employee_id,
            COALESCE(sr.receipt_id, sr.enterprise_receipt_id) as receipt_id,
            sr.document_source,
            COALESCE((e.first_name || ' ' || e.last_name), u.full_name) as employee_name,
            e.cuil as employee_cuil,
            COALESCE(e.email, u.email) as employee_email,
            e.phone as employee_phone,
            COALESCE(pr.receipt_pdf_path, nr.file_path) as receipt_pdf_path,
            COALESCE(pr.receipt_pdf_sha256, nr.file_hash) as receipt_pdf_sha256,
            COALESCE(pr.extracted_fields::jsonb, nr.receipt_metadata::jsonb) as extracted_fields,
            COALESCE(pr.employer_signed_at, nr.employer_signed_at) as employer_signed_at,
            COALESCE(pr.employee_signed_at, nr.employee_signed_at) as employee_signed_at,
            COALESCE(pr.status::text, nr.status::text) as receipt_status,
            o.name as organization_name,
            sr.issuer_ip,
            sr.issuer_ua,
            sr.requires_verification
        FROM signature_requests sr
        JOIN organizations o ON o.id = sr.organization_id
        LEFT JOIN payroll_receipts pr ON pr.id = sr.receipt_id
        LEFT JOIN receipts nr ON nr.id = sr.enterprise_receipt_id
        LEFT JOIN users u ON u.id = nr.user_id
        LEFT JOIN employees e ON e.id = sr.employee_id OR e.id = pr.employee_id OR e.id = u.employee_id
        WHERE sr.token_hash = :h
          AND (pr.id IS NOT NULL OR nr.id IS NOT NULL)
        {lock_clause}
    """), {"h": t_hash}).fetchone()
    
    if not row:
        raise HTTPException(404, "invalid_link")
    
    # 5. Auto-expire si estÃ¡ vencido
    token_expires_at = row.token_expires_at
    if token_expires_at and token_expires_at.tzinfo is None:
        token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)

    if row.sr_status == "pending" and token_expires_at < now:
        db.execute(text("""
            UPDATE signature_requests 
            SET status = 'expired'
            WHERE id = :id 
              AND status = 'pending'
        """), {"id": row.sr_id})
        db.commit()
        
        logger.info(
            "signature.token_auto_expired",
            extra={
                "event_type": "signature.token_auto_expired",
                "signature_request_id": str(row.sr_id),
                "receipt_id": str(row.receipt_id),
                "expired_at": row.token_expires_at.isoformat(),
            }
        )
        
        raise HTTPException(410, "token_expired")
    
    # Convert row to dict para mejor ergonomics
    return {
        "sr_id": row.sr_id,
        "sr_status": row.sr_status,
        "token_expires_at": token_expires_at,
        "organization_id": row.organization_id,
        "employee_id": row.employee_id,
        "receipt_id": row.receipt_id,
        "employee_name": row.employee_name,
        "employee_cuil": row.employee_cuil,
        "employee_email": row.employee_email,
        "employee_phone": getattr(row, "employee_phone", None),
        "receipt_pdf_path": row.receipt_pdf_path,
        "receipt_pdf_sha256": row.receipt_pdf_sha256,
        "extracted_fields": row.extracted_fields,
        "employer_signed_at": row.employer_signed_at,
        "employee_signed_at": row.employee_signed_at,
        "receipt_status": row.receipt_status,
        "organization_name": row.organization_name,
        "issuer_ip": row.issuer_ip,
        "issuer_ua": row.issuer_ua,
        "requires_verification": row.requires_verification,
    }


def create_signature_event(
    db: Session,
    receipt_id: str,
    organization_id: str,
    action: str,
    actor_type: str,
    actor_id: Optional[str] = None,
    status_before: Optional[str] = None,
    status_after: Optional[str] = None,
    pdf_sha_before: Optional[str] = None,
    pdf_sha_after: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    data: Optional[Dict] = None
) -> None:
    """
    Registra un evento de firma inmutable en la tabla signature_events.
    """
    db.execute(text("""
        INSERT INTO signature_events (
            id, receipt_id, organization_id, actor_type, actor_id, 
            action, status_before, status_after, pdf_sha256_before, 
            pdf_sha256_after, ip_address, user_agent, data
        ) VALUES (
            uuid_generate_v4(), :rid, :oid, :atype, :aid,
            :action, :sb, :sa, :psb, :psa, CAST(:ip AS inet), :ua, :data
        )
    """), {
        "rid": receipt_id,
        "oid": organization_id,
        "atype": actor_type,
        "aid": actor_id,
        "action": action,
        "sb": status_before,
        "sa": status_after,
        "psb": pdf_sha_before,
        "psa": pdf_sha_after,
        "ip": ip_address,
        "ua": user_agent[:500] if user_agent else None,
        "data": json.dumps(data or {})
    })

