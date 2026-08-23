"""
Password Reset API — Forgot/Reset password endpoints.

Security:
- POST /forgot-password: Returns error if email not found. Rate-limited 3/min.
- POST /reset-password: Validates token, updates password, purges sessions.
- All events logged to audit_log.
"""

from typing import Optional
from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy.orm import Session

from payroll_core import get_db, limiter, audit, logger, safe_transaction, hash_token, purge_user_sessions
from payroll_utils import get_real_ip
from services.password_reset_service import create_reset_token, validate_and_consume_token
from services.email_service import EmailService
import config

router = APIRouter(prefix="/api/auth", tags=["auth"])


# =============================================================================
# SCHEMAS
# =============================================================================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)

class ResetClaveEmpresaRequest(BaseModel):
    email: EmailStr
    otp: str = Field(..., min_length=6, max_length=6)
    custom_key: Optional[str] = Field(None, min_length=18)


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Initiates the password reset flow using OTP.
    Returns error if the email is not registered.
    """
    ip = get_real_ip(request)

    try:
        from services.verification_service import VerificationService
        raw_code, status = VerificationService.create_code(
            db, email=body.email, ip_address=ip, channel="email", context="password_reset"
        )

        if status == "user_not_found":
            raise HTTPException(
                status_code=404,
                detail="No se encontró una cuenta asociada a este correo electrónico."
            )

        if status.startswith("rate_limit"):
            raise HTTPException(
                status_code=429,
                detail="Demasiados intentos. Esperá unos minutos antes de volver a intentar."
            )

        if status == "ok" and raw_code:
            db.commit()  # IMPORTANT: Commit the new code to DB
            
            # Send OTP email
            await EmailService().send_password_reset_otp_email(to=body.email, code=raw_code)

            # Audit log
            from sqlalchemy import text
            user_row = db.execute(
                text("SELECT id, organization_id FROM users WHERE email = :e LIMIT 1"),
                {"e": body.email}
            ).fetchone()
            if user_row:
                with safe_transaction(db):
                    audit(
                        db, str(user_row.organization_id), "admin", str(user_row.id),
                        "PASSWORD_RESET_REQUESTED", str(user_row.id),
                        {"ip": ip, "channel": "otp"}
                    )

    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"password_reset.forgot_error: {e}")
        raise HTTPException(status_code=500, detail="Error interno. Intentá de nuevo más tarde.")

    return {
        "status": "ok",
        "message": "Te enviamos un código de 6 dígitos a tu correo electrónico."
    }


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Consumes a password reset OTP and sets a new password.
    """
    from services.password_reset_service import validate_password_strength
    from payroll_core import hash_password

    # 1. Validate password strength
    strength_error = validate_password_strength(body.new_password)
    if strength_error:
        return {
            "status": "error",
            "message": strength_error
        }

    # 2. Verify OTP
    from services.verification_service import VerificationService
    is_valid, error_msg = VerificationService.verify_code(
        db, email=body.email, code=body.otp
    )

    if not is_valid:
        msg = "Código inválido o expirado."
        if error_msg == "max_attempts_reached":
            msg = "Demasiados intentos fallidos. Solicitá un nuevo código."
        elif error_msg == "code_already_used":
            msg = "Este código ya fue utilizado."
        
        return {
            "status": "error",
            "message": msg
        }

    # 3. Update Password & Purge Sessions
    from sqlalchemy import text
    user_row = db.execute(
        text("SELECT id, organization_id FROM users WHERE email ILIKE :e"),
        {"e": body.email.strip()}
    ).fetchone()

    if user_row:
        user_id = str(user_row.id)
        new_hash = hash_password(body.new_password)
        with safe_transaction(db):
            # Update password
            db.execute(text("UPDATE users SET password_hash = :hash WHERE id = :uid"), 
                       {"hash": new_hash, "uid": user_id})
            
            # Purge sessions
            purge_user_sessions(db, user_id)
            
            # Audit
            audit(
                db, str(user_row.organization_id), "admin", user_id,
                "PASSWORD_RESET_COMPLETED", user_id,
                {"ip": get_real_ip(request), "channel": "otp"}
            )

    return {
        "status": "ok",
        "message": "Tu contraseña fue restablecida exitosamente. Ya podés iniciar sesión."
    }

@router.post("/reset-clave-empresa")
@limiter.limit("5/minute")
async def reset_clave_empresa(
    request: Request,
    body: ResetClaveEmpresaRequest,
    db: Session = Depends(get_db),
):
    """
    Consumes a password reset OTP for a Company, invalidates the old Clave,
    generates a NEW Clave, and returns it.
    """
    # 1. Verify OTP
    from services.verification_service import VerificationService
    is_valid, error_msg = VerificationService.verify_code(
        db, email=body.email, code=body.otp
    )

    if not is_valid:
        msg = "Código inválido o expirado."
        if error_msg == "max_attempts_reached":
            msg = "Demasiados intentos fallidos. Solicitá un nuevo código."
        elif error_msg == "code_already_used":
            msg = "Este código ya fue utilizado."
        return {"status": "error", "message": msg}

    from sqlalchemy import text
    user_row = db.execute(
        text("SELECT id, organization_id, full_name FROM users WHERE email ILIKE :e AND role = 'admin' LIMIT 1"),
        {"e": body.email.strip()}
    ).fetchone()

    if not user_row:
        # Prevent enumeration
        import time; time.sleep(0.5)
        return {"status": "error", "message": "No se encontró una empresa asociada a este correo."}

    org_id = user_row.organization_id
    user_id = str(user_row.id)

    raw_key = None
    if body.custom_key:
        raw_key = body.custom_key.strip()
        # Check for duplicates
        existing_hash = hash_token(raw_key)
        if db.execute(text("SELECT 1 FROM registration_keys WHERE key_hash = :h"), {"h": existing_hash}).fetchone():
            return {"status": "error", "message": "Esta clave ya está en uso. Por favor elegí otra."}
    else:
        # Generate new random key
        import string
        import secrets
        charset = string.ascii_lowercase + string.digits
        parts = [
            "YCP",
            "".join(secrets.choice(charset) for _ in range(4)),
            "".join(secrets.choice(charset) for _ in range(4)),
            "".join(secrets.choice(charset) for _ in range(4))
        ]
        raw_key = "-".join(parts)
    
    key_hash = hash_token(raw_key)
    prefix = raw_key[:8]

    with safe_transaction(db):
        # Invalidate old keys for this org
        db.execute(text("""
            UPDATE registration_keys 
            SET is_revoked = true 
            WHERE used_by_org_id = :org_id AND is_active = true
        """), {"org_id": org_id})

        # Insert new key
        db.execute(text("""
            INSERT INTO registration_keys (key_hash, key_prefix, max_uses, used_by_org_id, is_active, label)
            VALUES (:h, :p, -1, :org_id, true, :lbl)
        """), {
            "h": key_hash, "p": prefix, "org_id": org_id, "lbl": user_row.full_name
        })

        # Purge sessions
        db.execute(text("DELETE FROM user_sessions WHERE user_id = :uid"), {"uid": user_id})

        # Audit
        audit(
            db, str(org_id), "admin", user_id,
            "COMPANY_KEY_RESET", user_id,
            {"ip": get_real_ip(request), "channel": "otp", "new_key_prefix": prefix}
        )
        
        # Send new key by email
        subject = f"Tu nueva Clave de Acceso Corporativo — {config.SYSTEM_NAME}"
        body_html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #1d4ed8;">Clave de Acceso Restablecida</h2>
            <p>Tu clave de empresa anterior ha sido revocada por seguridad.</p>
            <p>Tu <strong>nueva Clave de Acceso</strong> es:</p>
            <div style="background: #f1f5f9; border-radius: 8px; padding: 24px; text-align: center; margin: 24px 0;">
                <span style="font-family: monospace; font-size: 24px; font-weight: bold; letter-spacing: 2px; color: #0f172a;">{raw_key}</span>
            </div>
            <p>Usa esta nueva clave para ingresar al sistema.</p>
        </body>
        </html>
        """
        await EmailService().send_html(to=body.email, subject=subject, body_html=body_html)

    return {
        "status": "ok",
        "message": "Tu clave ha sido restablecida exitosamente.",
        "new_clave": raw_key  # Returned to the frontend to display it once
    }
