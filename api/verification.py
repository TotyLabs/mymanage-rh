"""
Verification API — Multi-channel OTP (SMS primary, Email fallback).

Phase 1: SMS + Email
Phase 2: WhatsApp (future)
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel, EmailStr
from typing import Optional

from payroll_core import get_db, logger, audit, utc_now, limiter, safe_transaction
from payroll_utils import get_real_ip
from services.verification_service import VerificationService
from services.email_service import EmailService
from services.sms_service import SmsService

router = APIRouter(prefix="/api/verification", tags=["verification"])


class SendOtpRequest(BaseModel):
    email: EmailStr
    phone: Optional[str] = None
    receipt_id: Optional[str] = None
    signature_token: Optional[str] = None
    channel: str = "sms"       # "sms" | "email"
    context: str = "signature"  # "signature" | "login" | "password_reset"


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    code: str
    receipt_id: Optional[str] = None
    signature_token: Optional[str] = None


class ResendOtpRequest(BaseModel):
    identifier: str


@router.post("/send")
@limiter.limit("3/minute")
async def send_otp(
    body: SendOtpRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Sends an OTP via the requested channel (SMS or Email).
    Auto-fallback: if SMS requested but no phone ? sends via email.
    """
    ip_address = get_real_ip(request)
    channel = body.channel if body.channel in ("sms", "email") else "sms"
    
    if channel == "sms" and not body.phone:
        channel = "email"

    destination = body.phone if channel == "sms" else body.email

    with safe_transaction(db):
        raw_code, status = VerificationService.create_code(
            db, body.email, ip_address,
            receipt_id=body.receipt_id,
            signature_token=body.signature_token,
            channel=channel,
            destination=destination,
            context=body.context
        )

        if status != "ok":
            raise HTTPException(400, status)

        # Resolve organization_id for audit (Bimodal)
        org_name = "MyManageRH"
        org_id = None
        if body.receipt_id:
            try:
                org_row = db.execute(text("""
                    SELECT o.id, o.name FROM organizations o 
                    WHERE o.id = (
                        SELECT COALESCE(pr.organization_id, nr.company_id)
                        FROM (SELECT CAST(:rid AS uuid) as id) q
                        LEFT JOIN payroll_receipts pr ON pr.id = q.id
                        LEFT JOIN receipts nr ON nr.id = q.id
                        LIMIT 1
                    )
                """), {"rid": body.receipt_id}).fetchone()
                if org_row:
                    org_name = org_row.name
                    org_id = str(org_row.id)
            except Exception:
                db.rollback()
        
        if not org_id:
            try:
                user_row = db.execute(text("SELECT organization_id FROM users WHERE email = :email"), {"email": body.email}).fetchone()
                if user_row:
                    org_id = str(user_row.organization_id)
            except Exception:
                db.rollback()

        # Send OTP in background
        if channel == "sms":
            background_tasks.add_task(SmsService().send_otp, body.phone, raw_code, org_name)
        else:
            background_tasks.add_task(EmailService().send_verification_otp_email, body.email, raw_code, org_name)

        audit(db, org_id or "00000000-0000-0000-0000-000000000000", "system", None, "OTP_SENT", None, {
            "email": body.email, 
            "channel": channel,
            "receipt_id": body.receipt_id
        })

    return {"status": "ok", "channel": channel}


@router.post("/verify")
async def verify_otp(
    body: VerifyOtpRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Verifies the OTP code.
    """
    with safe_transaction(db):
        success, reason = VerificationService.verify_code(
            db, body.email, body.code,
            receipt_id=body.receipt_id,
            signature_token=body.signature_token
        )

        # Resolve organization_id for audit (Bimodal)
        org_id = None
        if body.receipt_id:
            try:
                org_id_val = db.execute(text("""
                    SELECT COALESCE(pr.organization_id, nr.company_id)
                    FROM (SELECT CAST(:rid AS uuid) as id) q
                    LEFT JOIN payroll_receipts pr ON pr.id = q.id
                    LEFT JOIN receipts nr ON nr.id = q.id
                    LIMIT 1
                """), {"rid": body.receipt_id}).scalar()
                if org_id_val:
                    org_id = str(org_id_val)
            except Exception:
                db.rollback()

        if not success:
            audit(db, org_id or "00000000-0000-0000-0000-000000000000", "system", None, "OTP_FAILED", None, {
                "email": body.email, "reason": reason, "receipt_id": body.receipt_id
            })
            raise HTTPException(400, reason)

        audit(db, org_id or "00000000-0000-0000-0000-000000000000", "system", None, "OTP_VERIFIED", None, {
            "email": body.email, "receipt_id": body.receipt_id
        })

    return {"status": "ok", "verified": True}


@router.post("/resend")
@limiter.limit("2/minute")
async def resend_otp(
    body: ResendOtpRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Resends an OTP to a user. 
    Identifier can be email or phone.
    """
    identifier = body.identifier.strip()
    
    with safe_transaction(db):
        # 1. Find user
        user = db.execute(text("""
            SELECT u.email, u.full_name, o.name as org_name, e.phone
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            LEFT JOIN employees e ON u.employee_id = e.id
            WHERE u.email = :id OR e.phone = :id OR e.dni = :id
        """), {"id": identifier}).fetchone()

        if not user:
            # Silent fail for security, but return 404 if we want to be explicit for UX
            # In this context (verify-account), the user should exist.
            raise HTTPException(404, "usuario_no_encontrado")

        # 2. Trigger send (reuse logic from auth trigger)
        from api.auth import trigger_registration_otp
        background_tasks.add_task(
            trigger_registration_otp, 
            user.email, 
            user.phone if identifier == user.phone else None, 
            user.org_name or "MyManageRH", 
            get_real_ip(request)
        )

    return {"status": "ok", "message": "otp_resent"}
