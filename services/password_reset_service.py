"""
Password Reset Service — Secure token-based password reset.

Security:
- Tokens hashed with HMAC-SHA256 (SECRET_KEY as key) — never stored raw.
- Single-use: `used_at` column marks consumption.
- Configurable TTL (default 20 min via PASSWORD_RESET_TTL_MINUTES).
- Previous unused tokens invalidated transactionally before creating new ones.
- All user sessions purged after password change.
- No user enumeration: returns None silently when email not found.
"""

import re
import hmac
import hashlib
import secrets
from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from payroll_core import (
    utc_now, hash_password, safe_transaction, logger, SECRET_KEY
)
import config


# =============================================================================
# HMAC TOKEN HASHING (salted — not plain SHA-256)
# =============================================================================

def _hmac_hash_token(raw_token: str) -> str:
    """
    HMAC-SHA256 using SECRET_KEY as the key.
    Superior to plain SHA-256: even if DB leaks, tokens can't be brute-forced
    without knowing the application secret.
    """
    return hmac.new(
        SECRET_KEY.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


# =============================================================================
# PASSWORD STRENGTH VALIDATION
# =============================================================================

def validate_password_strength(password: str) -> Optional[str]:
    """
    Validates password meets minimum complexity requirements.
    Returns an error message string on failure, None on success.
    
    Rules:
    - Length >= 8 characters
    - At least 1 letter (a-z or A-Z)
    - At least 1 number (0-9)
    """
    if not password or len(password) < 8:
        return "La contraseña debe tener al menos 8 caracteres."
    if not re.search(r'[a-zA-Z]', password):
        return "La contraseña debe contener al menos una letra."
    if not re.search(r'[0-9]', password):
        return "La contraseña debe contener al menos un número."
    return None


# =============================================================================
# CORE SERVICE
# =============================================================================

def create_reset_token(
    db: Session,
    email: str,
    ip_address: Optional[str] = None,
) -> Optional[str]:
    """
    Generates a password reset token for a user identified by email.
    
    Returns:
        - The raw token string if the user exists (caller sends it via email).
        - None if no user found (caller returns 200 OK anyway — no enumeration).
    
    Security:
        - Invalidates ALL previous unused tokens for this user (transactional).
        - Stores only the HMAC-SHA256 hash.
        - Per-email cooldown: if a token was created < 60s ago, returns None
          to prevent flood/abuse even if user exists.
    """
    # 1. Lookup user by email (cross-organization: first match)
    user_row = db.execute(text("""
        SELECT id, organization_id FROM users
        WHERE email = :email AND is_active = true
        LIMIT 1
    """), {"email": email.strip().lower() if email else ""}).fetchone()

    if not user_row:
        logger.info("password_reset.user_not_found", extra={"event": "password_reset.no_user"})
        return None

    user_id = str(user_row.id)
    now = utc_now()
    ttl_minutes = getattr(config, "PASSWORD_RESET_TTL_MINUTES", 20)

    # 2. Per-email cooldown (60 seconds between requests)
    recent = db.execute(text("""
        SELECT 1 FROM password_reset_tokens
        WHERE user_id = :uid AND created_at > :cutoff AND used_at IS NULL
        LIMIT 1
    """), {"uid": user_id, "cutoff": now - timedelta(seconds=60)}).fetchone()

    if recent:
        logger.warning("password_reset.cooldown_active", extra={"user_id": user_id})
        return None  # Silent — caller still returns 200

    # 3. Generate token
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hmac_hash_token(raw_token)
    expires_at = now + timedelta(minutes=ttl_minutes)

    with safe_transaction(db):
        # 4. Invalidate ALL previous unused tokens for this user (transactional)
        db.execute(text("""
            UPDATE password_reset_tokens
            SET used_at = :now
            WHERE user_id = :uid AND used_at IS NULL
        """), {"now": now, "uid": user_id})

        # 5. Insert new token
        db.execute(text("""
            INSERT INTO password_reset_tokens
                (user_id, token_hash, expires_at, ip_address)
            VALUES (:uid, :hash, :expires, :ip)
        """), {
            "uid": user_id,
            "hash": token_hash,
            "expires": expires_at,
            "ip": ip_address,
        })

    logger.info("password_reset.token_created", extra={
        "user_id": user_id,
        "ttl_minutes": ttl_minutes,
    })

    return raw_token


def validate_and_consume_token(
    db: Session,
    raw_token: str,
    new_password: str,
) -> Tuple[bool, Optional[str]]:
    """
    Validates a password reset token and updates the user's password.
    
    Returns:
        (True, None)           — success
        (False, "error_code")  — failure with specific error code
    
    On success:
        - New password is bcrypt-hashed and stored.
        - Token marked as consumed (used_at = now).
        - ALL user sessions purged (forces re-login everywhere).
    """
    # 1. Validate password strength
    strength_error = validate_password_strength(new_password)
    if strength_error:
        return False, strength_error

    # 2. Hash incoming token with HMAC
    token_hash = _hmac_hash_token(raw_token)
    now = utc_now()

    # 3. Lookup token
    token_row = db.execute(text("""
        SELECT id, user_id, expires_at, used_at
        FROM password_reset_tokens
        WHERE token_hash = :hash
    """), {"hash": token_hash}).fetchone()

    if not token_row:
        logger.warning("password_reset.token_not_found")
        return False, "Token inválido o expirado."

    # 4. Check expiration
    if now > token_row.expires_at:
        logger.warning("password_reset.token_expired", extra={"token_id": str(token_row.id)})
        return False, "El enlace de restablecimiento ha expirado. Solicitá uno nuevo."

    # 5. Check single-use
    if token_row.used_at is not None:
        logger.warning("password_reset.token_already_used", extra={"token_id": str(token_row.id)})
        return False, "Este enlace ya fue utilizado. Solicitá uno nuevo."

    user_id = str(token_row.user_id)

    # 6. Execute password change + session purge in a single transaction
    new_hash = hash_password(new_password)

    with safe_transaction(db):
        # 6a. Update password
        db.execute(text("""
            UPDATE users SET password_hash = :hash WHERE id = :uid
        """), {"hash": new_hash, "uid": user_id})

        # 6b. Mark token as consumed
        db.execute(text("""
            UPDATE password_reset_tokens SET used_at = :now WHERE id = :tid
        """), {"now": now, "tid": str(token_row.id)})

        # 6c. Purge ALL sessions for this user (force re-login everywhere)
        db.execute(text("""
            DELETE FROM user_sessions WHERE user_id = :uid
        """), {"uid": user_id})

    logger.info("password_reset.success", extra={"user_id": user_id})
    return True, None
