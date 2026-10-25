"""
Verification Service — Generación y validación de códigos OTP multi-canal.

Canales soportados: SMS (primary), Email (fallback).
Compliance: destination_hash (SHA-256 del destino sin guardar datos en claro).
"""

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from typing import Optional, Tuple
from sqlalchemy import text
from sqlalchemy.orm import Session
from payroll_core import SECRET_KEY, logger, safe_transaction, utc_now
import config


class VerificationService:
    ALLOWED_CONTEXTS = {
        "registration",
        "signature",
        "login",
        "password_reset",
        "company_key_reset",
        "download",
    }

    @staticmethod
    def generate_code() -> str:
        """Generates a 6-digit numeric OTP."""
        return "".join([str(secrets.randbelow(10)) for _ in range(6)])

    @staticmethod
    def _keyed_digest(payload: dict) -> str:
        key = hmac.new(
            SECRET_KEY.encode("utf-8"),
            b"mymanage-verification-code-v1",
            hashlib.sha256,
        ).digest()
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.new(key, canonical, hashlib.sha256).hexdigest()

    @staticmethod
    def compute_context_hash(
        receipt_id: Optional[str],
        signature_token: Optional[str],
        code: str,
        context: str = "signature",
    ) -> str:
        return VerificationService._keyed_digest({
            "context": context,
            "receipt_id": receipt_id,
            "signature_token": signature_token,
            "code": code,
        })

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
        if context not in VerificationService.ALLOWED_CONTEXTS:
            return None, "invalid_context"

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
              AND context = :context
              AND receipt_id IS NOT DISTINCT FROM :rid 
              AND signature_token IS NOT DISTINCT FROM :signature_token
              AND verified = false
              AND used_at IS NULL
              AND created_at < :grace
        """), {
            "now": utc_now(),
            "uid": user.id,
            "context": context,
            "rid": receipt_id,
            "signature_token": signature_token,
            "grace": grace_period_limit,
        })

        # 4. Generate & Hash
        raw_code = VerificationService.generate_code()
        code_hash = VerificationService._keyed_digest({
            "context": context,
            "code": raw_code,
        })
        context_hash = VerificationService.compute_context_hash(
            receipt_id, signature_token, raw_code, context
        )
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
        signature_token: Optional[str] = None,
        context: str = "signature",
    ) -> Tuple[bool, str]:
        """Verify and consume a one-time code for exactly one operation and resource."""
        if context not in VerificationService.ALLOWED_CONTEXTS:
            return False, "invalid_context"

        # 1. Find User (Case-insensitive + stripped)
        clean_email = email.strip().lower()
        clean_code = (code or "").strip()
        user = db.execute(text("SELECT id FROM users WHERE email ILIKE :email"), {"email": clean_email}).fetchone()
        if not user:
            logger.warning(f"verification.user_not_found: email={clean_email}")
            return False, "user_not_found"

        # 2. Find only active codes for the requested operation and resource.
        rows = db.execute(text("""
            SELECT id, receipt_id, signature_token, code_hash, context_hash, expires_at, attempts, verified, used_at
            FROM verification_codes
            WHERE user_id = :uid 
              AND context = :context
              AND receipt_id IS NOT DISTINCT FROM :rid
              AND signature_token IS NOT DISTINCT FROM :signature_token
              AND verified = false
              AND used_at IS NULL
              AND expires_at > :now
              AND attempts < :max_attempts
            FOR UPDATE
        """), {
            "uid": user.id,
            "context": context,
            "rid": receipt_id,
            "signature_token": signature_token,
            "now": utc_now(),
            "max_attempts": config.OTP_MAX_ATTEMPTS,
        }).fetchall()

        if not rows:
            logger.warning(f"verification.otp_not_found_at_all: user={user.id} rid={receipt_id}")
            return False, "code_invalid_or_expired"
        
        logger.info(f"verification.active_codes_found: user={user.id} count={len(rows)}")

        # Compare keyed digests to avoid offline guessing from a database dump.
        matched_row = None
        for row in rows:
            expected_hash = VerificationService.compute_context_hash(
                receipt_id, signature_token, clean_code, context
            )
            if hmac.compare_digest(row.context_hash, expected_hash):
                matched_row = row
                break
        
        if not matched_row:
            with safe_transaction(db):
                attempts = db.execute(text("""
                    UPDATE verification_codes
                    SET attempts = attempts + 1,
                        expires_at = CASE
                            WHEN attempts + 1 >= :max_attempts THEN :now
                            ELSE expires_at
                        END
                    WHERE user_id = :uid
                      AND context = :context
                      AND receipt_id IS NOT DISTINCT FROM :rid
                      AND signature_token IS NOT DISTINCT FROM :signature_token
                      AND verified = false
                      AND used_at IS NULL
                      AND expires_at > :now
                      AND attempts < :max_attempts
                    RETURNING attempts
                """), {
                    "uid": user.id,
                    "context": context,
                    "rid": receipt_id,
                    "signature_token": signature_token,
                    "now": utc_now(),
                    "max_attempts": config.OTP_MAX_ATTEMPTS,
                }).fetchall()
            logger.warning(
                "verification.otp_incorrect: user=%s context=%s candidate_count=%s",
                user.id,
                context,
                len(rows),
            )
            if any(attempt.attempts >= config.OTP_MAX_ATTEMPTS for attempt in attempts):
                return False, "max_attempts_reached"
            return False, "code_incorrect" if rows else "code_invalid_or_expired"

        row = matched_row

        with safe_transaction(db):
            consumed = db.execute(text("""
                UPDATE verification_codes
                SET verified = true, verified_at = :now, used_at = :now
                WHERE id = :id
                  AND context = :context
                  AND verified = false
                  AND used_at IS NULL
                  AND expires_at > :now
                  AND attempts < :max_attempts
                RETURNING id
            """), {
                "id": row.id,
                "context": context,
                "now": utc_now(),
                "max_attempts": config.OTP_MAX_ATTEMPTS,
            }).fetchone()
            if not consumed:
                return False, "max_attempts_reached"

            if context == "registration":
                db.execute(text("""
                    UPDATE users
                    SET is_verified = true, user_status = 'active'
                    WHERE id = :id
                """), {"id": user.id})

        logger.info(f"verification.otp_verified: user={user.id} receipt={receipt_id}")
        return True, "ok"
