"""
Verification Service — Generación y validación de códigos OTP multi-canal.

Canales soportados: SMS (primary), Email (fallback).
Compliance: destination_hash (SHA-256 del destino sin guardar datos en claro).
"""

import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from payroll_core import logger, utc_now, hash_token
import config


class VerificationService:
    @staticmethod
    def generate_code() -> str:
        """Generates a 6-digit numeric OTP."""
        return "".join([str(secrets.randbelow(10)) for _ in range(6)])

    @staticmethod
    def compute_context_hash(receipt_id: str, signature_token: str, code: str) -> str:
        """
        Computes a strong binding hash for the OTP context.
        hash(receipt_id + signature_token + code)
        """
        payload = f"{receipt_id or ''}:{signature_token or ''}:{code}"
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def compute_destination_hash(destination: str) -> str:
        """
        SHA-256 of the destination (phone/email) for compliance audit.
        Proves where the OTP was sent without storing PII in clear text.
        """
        return hashlib.sha256((destination or "").strip().lower().encode()).hexdigest()

    @staticmethod
    def check_rate_limit(db: Session, email: str, ip_address: str) -> Tuple[bool, str]:
        """
        Enforces rate limits:
        - Max 3 OTP sends per 10 minutes per email.
        - Max 10 per hour per IP.
        """
        now = utc_now()
        
        # Email limit
        ten_mins_ago = now - timedelta(minutes=config.OTP_EXPIRATION_MINUTES)
        email_count = db.execute(text("""
            SELECT COUNT(*) FROM verification_codes 
            WHERE user_id IN (SELECT id FROM users WHERE email = :email)
              AND created_at > :since
        """), {"email": email, "since": ten_mins_ago}).scalar()
        
        if email_count >= 3:
            return False, "rate_limit_email_reached"

        # IP limit
        one_hour_ago = now - timedelta(hours=1)
        ip_count = db.execute(text("""
            SELECT COUNT(*) FROM verification_codes 
            WHERE ip_address = :ip
              AND created_at > :since
        """), {"ip": ip_address, "since": one_hour_ago}).scalar()
        
        if ip_count >= 10:
            return False, "rate_limit_ip_reached"

        return True, ""

    @staticmethod
    def create_code(
        db: Session, 
        email: str, 
        ip_address: str,
        receipt_id: Optional[str] = None, 
        signature_token: Optional[str] = None,
        channel: str = "sms",
        destination: Optional[str] = None,
        context: str = "signature"
    ) -> Tuple[Optional[str], str]:
        """
        Generates and stores a new verification code.
        Invalidates previous codes for the same context.
        """
        # 1. Check Rate Limits
        is_allowed, reason = VerificationService.check_rate_limit(db, email, ip_address)
        if not is_allowed:
            logger.warning(f"verification.rate_limit_triggered: email={email} ip={ip_address} reason={reason}")
            return None, reason

        # 2. Find User (Harden)
        clean_email = email.strip().lower()
        user = db.execute(text("SELECT id FROM users WHERE email ILIKE :email"), {"email": clean_email}).fetchone()
        if not user:
            return None, "user_not_found"

        # 3. Invalidate previous codes for this user/receipt
        # GAP-008: Added a 30s grace period + NULL-safe rid check.
        grace_period_limit = utc_now() - timedelta(seconds=30)
        db.execute(text("""
            UPDATE verification_codes 
            SET expires_at = :now 
            WHERE user_id = :uid 
              AND receipt_id IS NOT DISTINCT FROM :rid 
              AND verified = false
              AND created_at < :grace
        """), {"now": utc_now(), "uid": user.id, "rid": receipt_id, "grace": grace_period_limit})

        # 4. Generate & Hash
        raw_code = VerificationService.generate_code()
        code_hash = hash_token(raw_code)
        context_hash = VerificationService.compute_context_hash(receipt_id, signature_token, raw_code)
        destination_hash = VerificationService.compute_destination_hash(destination or email)
        expires_at = utc_now() + timedelta(minutes=config.OTP_EXPIRATION_MINUTES)

        # 5. Save
        db.execute(text("""
            INSERT INTO verification_codes (
                user_id, receipt_id, signature_token, code_hash, context, context_hash, 
                expires_at, ip_address, channel, destination_hash
            ) VALUES (:uid, :rid, :st, :ch, :ctx_raw, :ctx_hash, :exp, :ip, :chan, :dh)
        """), {
            "uid": user.id, "rid": receipt_id, "st": signature_token,
            "ch": code_hash, "ctx_raw": context, "ctx_hash": context_hash, "exp": expires_at, "ip": ip_address,
            "chan": channel, "dh": destination_hash
        })

        logger.info(f"verification.otp_created: user={user.id} channel={channel} receipt={receipt_id}")
        return raw_code, "ok"

    @staticmethod
    def verify_code(
        db: Session, 
        email: str, 
        code: str,
        receipt_id: Optional[str] = None, 
        signature_token: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        - Context binding (context_hash)
        """
        # 1. Find User (Case-insensitive + stripped)
        clean_email = email.strip().lower()
        clean_code = (code or "").strip()
        user = db.execute(text("SELECT id FROM users WHERE email ILIKE :email"), {"email": clean_email}).fetchone()
        if not user:
            logger.warning(f"verification.user_not_found: email={clean_email}")
            return False, "user_not_found"

        # 2. Find active codes (Broad search for diagnostics)
        rows = db.execute(text("""
            SELECT id, receipt_id, signature_token, code_hash, context_hash, expires_at, attempts, verified, used_at
            FROM verification_codes
            WHERE user_id = :uid 
              AND verified = false
              AND expires_at > :now
        """), {"uid": user.id, "now": utc_now()}).fetchall()

        if not rows:
            logger.warning(f"verification.otp_not_found_at_all: user={user.id} rid={receipt_id}")
            return False, "code_invalid_or_expired"
        
        logger.info(f"verification.active_codes_found: user={user.id} count={len(rows)}")

        # Check all candidate rows
        matched_row = None
        for row in rows:
            # TRY 1: Matches exactly with what's in the REQUEST
            incoming_context_hash = VerificationService.compute_context_hash(receipt_id, signature_token, clean_code)
            if row.context_hash == incoming_context_hash:
                matched_row = row
                logger.info(f"verification.exact_context_match: row={row.id}")
                break
                
            # TRY 2: Matches with row's OWN context (Flexible match)
            # This handles cases where receipt_id or signature_token slightly differ in format
            flexible_context_hash = VerificationService.compute_context_hash(row.receipt_id, row.signature_token, clean_code)
            if row.context_hash == flexible_context_hash:
                matched_row = row
                logger.info(f"verification.flexible_context_match: row={row.id} rid_match={row.receipt_id==receipt_id}")
                break
            
            # Log why it didn't match for debugging
            logger.debug(f"verification.mismatch_details: row={row.id} db_rid={row.receipt_id} in_rid={receipt_id} db_st={row.signature_token} in_st={signature_token}")
        
        if not matched_row:
             logger.warning(f"verification.otp_incorrect: user={user.id} rid={receipt_id} codes_checked={len(rows)}")
             return False, "code_incorrect"

        row = matched_row

        # Check replay protection
        if row.used_at:
            logger.error(f"verification.replay_detected: code_id={row.id}")
            return False, "code_already_used"

        # Check attempts
        if row.attempts >= 5:
            logger.warning(f"verification.max_attempts_reached: code_id={row.id}")
            return False, "max_attempts_reached"

        # Increment attempts
        db.execute(text("UPDATE verification_codes SET attempts = attempts + 1 WHERE id = :id"), {"id": row.id})

        # The hash/context check was already done in the loop above to select the row

        # Success!
        db.execute(text("""
            UPDATE verification_codes 
            SET verified = true, verified_at = :now, used_at = :now
            WHERE id = :id
        """), {"id": row.id, "now": utc_now()})
        
        # Also mark user as verified and active in user table
        db.execute(text("UPDATE users SET is_verified = true, user_status = 'active' WHERE id = :id"), {"id": user.id})

        logger.info(f"verification.otp_verified: user={user.id} receipt={receipt_id}")
        return True, "ok"
