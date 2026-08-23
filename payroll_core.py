import payroll_utils

def get_real_ip(request):
    return payroll_utils.get_real_ip(request)
import os
import re
import json
import hmac
import hashlib
import secrets
import time
import logging
import base64
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Generator, Union
from contextlib import contextmanager

from fastapi import Depends, HTTPException, Request, Cookie
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from pathlib import Path
import bcrypt
from slowapi.util import get_remote_address
from slowapi import Limiter
from services.redis_service import redis_service

def user_ip_key(request: Request):
    """
    Combined rate limit key (IP + UserID).
    Prevents a single authenticated user from saturating heavy endpoints 
    even if they rotate IPs or use a shared VPN/NAT.
    """
    ip = get_remote_address(request)
    
    # Try to identify user without hitting DB if possible
    # Most routes have 'require_auth' which populates request.state.user
    user_id = "anon"
    if hasattr(request, "state") and hasattr(request.state, "user") and request.state.user:
        # request.state.user is usually a dict or object from get_current_user
        if isinstance(request.state.user, dict):
            user_id = request.state.user.get("id", "unknown")
        else:
            user_id = getattr(request.state.user, "id", "unknown")
            
    return f"{ip}:{user_id}"


__all__ = [
    'PRODUCTION', 'LOG_LEVEL', 'DATABASE_URL', 'SECRET_KEY', 'STORAGE_PATH',
    'ALLOWED_STORAGE_DIR', 'STORAGE_ROOT', 'BASE_DIR', 'UI_DIR', 'MAX_FILE_SIZE',
    'TOKEN_TTL_HOURS', 'SESSION_TTL_HOURS', 'TOKEN_REGEX', 'CUIL_REGEX',
    'SIGNATURE_MODE', 'get_real_ip', 'get_db', 'engine', 'SessionLocal',
    'limiter', 'user_ip_key', 'safe_transaction', 'utc_now', 'safe_write_file',
    'safe_remove_file', 'file_transaction', 'new_token', 'hash_token',
    'validate_token_format', 'get_current_user', 'require_auth', 'require_admin',
    'hash_password', 'verify_password', 'create_session', 'audit',
    'normalize_cuil', 'normalize_dni', 'normalize_org_name',
    'ensure_storage_dirs', 'build_storage_path', 'safe_join_under_storage', 'compute_file_sha256',
    'validate_pdf_magic', 'save_bytes_atomically', 'write_upload_to_disk',
    'validate_email_format', 'sanitize_text_input',
    'validate_organization_access', 'create_signature_token',
    'get_existing_signature_request', 'create_signature_request'
]

# Config - Basic (algunos valores se redefinen desde config.py al final)
import config

# Config - Linked to central config.py
PRODUCTION = config.PRODUCTION
LOG_LEVEL = config.LOG_LEVEL
DATABASE_URL = config.DATABASE_URL
SECRET_KEY = getattr(config, "SECRET_KEY")
STORAGE_PATH = config.STORAGE_PATH
ALLOWED_STORAGE_DIR = config.ALLOWED_STORAGE_DIR
STORAGE_ROOT = config.STORAGE_ROOT
BASE_DIR = config.BASE_DIR
UI_DIR = config.UI_DIR
MAX_FILE_SIZE = config.MAX_FILE_SIZE
TOKEN_TTL_HOURS = config.TOKEN_TTL_HOURS
SESSION_TTL_HOURS = config.SESSION_TTL_HOURS
TOKEN_REGEX = config.TOKEN_REGEX
CUIL_REGEX = config.CUIL_REGEX
SIGNATURE_MODE = config.SIGNATURE_MODE

# =============================================================================
# BASIC UTILS (Moved up for circular import safety)
# =============================================================================


# SignatureService global instance (lazy-loaded)
_signature_service = None

import logging.handlers

# =============================================================================
# EXCEPTIONS
# =============================================================================
class EmailSendFailedError(Exception):
    """Lanzada cuando falla el envío de un correo vía SMTP."""
    def __init__(self, message: str = "Email delivery failed", code: str = "SMTP_SEND"):
        super().__init__(message)
        self.code = code


# =============================================================================
# STRUCTURED LOGGING & PII MASKING
# =============================================================================

def redact_pii(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Redacts sensitive Personal Identifiable Information (PII) from log data.
    Uses a blacklist approach for common sensitive fields.
    """
    if not data or not isinstance(data, dict):
        return data
    
    # Sensitive keys to redact fully
    SENSITIVE_KEYS = {
        "password", "password_hash", "token", "session_token", "secret", "key",
        "signature_image", "img_bytes", "signature_bytes", "logo_bytes"
    }
    # Keys to mask partially (e.g., CBU, CUIL, Email)
    MASK_KEYS = {"email", "cbu", "cuil", "cuit", "dni", "address", "phone"}

    redacted = {}
    for k, v in data.items():
        k_lower = k.lower()
        if k_lower in SENSITIVE_KEYS:
            redacted[k] = "[REDACTED]"
        elif k_lower in MASK_KEYS and isinstance(v, str) and len(v) > 4:
            # Mask all but last 3-4 chars
            prefix = v[:1] if "@" in v else v[:2]
            redacted[k] = f"{prefix}...{v[-3:]}"
        elif isinstance(v, dict):
            redacted[k] = redact_pii(v)
        elif isinstance(v, list):
            redacted[k] = [redact_pii(i) if isinstance(i, dict) else i for i in v]
        else:
            redacted[k] = v
    return redacted

class PIIMaskingFilter(logging.Filter):
    """
    Intercerpta todos los mensajes de log y enmascara patrones sensibles
    (DNI, CUIL, Tokens) autom !ticamente antes de que lleguen al archivo/consola.
    """
    # GAP-009 Fix: Contextual PII masking for CUIL to avoid hiding timestamps or UUID fragments
    PII_PATTERNS = [
        (re.compile(r'(?i)(?:cuil|cuit)[=:\s"]*\d{11}\b'), lambda m: re.sub(r'\d{11}', '***********', m.group())), 
        (re.compile(r'(?i)(?:dni|documento|doc_num)[=:\s"]*\d{7,8}\b'), lambda m: re.sub(r'\d{7,8}', '********', m.group())),  # DNI: only near labels
        (re.compile(r'\b[a-fA-F0-9]{64}\b'), '[HASH_MASKED]'),  # SHA-256 hashes only (exactly 64 hex chars)
    ]

    def filter(self, record):
        smtp_pass = getattr(config, "SMTP_PASSWORD", None)
        has_smtp_pass = smtp_pass and len(smtp_pass) > 2

        if isinstance(record.msg, str):
            for pattern, replacement in self.PII_PATTERNS:
                record.msg = pattern.sub(replacement, record.msg)
            if has_smtp_pass:
                record.msg = record.msg.replace(smtp_pass, "[REDACTED_PASSWORD]")
        
        # Scrub args
        if has_smtp_pass and record.args:
            new_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    new_args.append(arg.replace(smtp_pass, "[REDACTED_PASSWORD]"))
                else:
                    new_args.append(arg)
            record.args = tuple(new_args)

        # Scrub exc_text
        if has_smtp_pass and record.exc_text:
            record.exc_text = record.exc_text.replace(smtp_pass, "[REDACTED_PASSWORD]")

        # Scrub exc_info
        if has_smtp_pass and record.exc_info and not record.exc_text:
            import traceback
            exc_type, exc_val, exc_tb = record.exc_info
            formatted_lines = traceback.format_exception(exc_type, exc_val, exc_tb)
            exc_text = "".join(formatted_lines)
            record.exc_text = exc_text.replace(smtp_pass, "[REDACTED_PASSWORD]")

        # Enmascarar también 'extra' si existe (para Structured Logging)
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            # Usamos la función redact_pii existente
# Apply redaction to extra and finish filter
            record.extra = redact_pii(record.extra)
        return True


# Monkeypatch Logger.makeRecord to defensively strip reserved LogRecord keys
# This prevents accidental KeyError when callers pass an `extra` dict containing
# names that conflict with LogRecord attributes (e.g. 'filename'). Do this early
# so all log calls in worker processes are protected even before we can restart
# every module that logs.
_LOGRECORD_RESERVED_KEYS = {
    'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
    'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
    'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
    'processName', 'process'
}

_original_makeRecord = logging.Logger.makeRecord

def _makeRecord_safe(*args, **kwargs):
    """Wrapper that delegates to original makeRecord but strips reserved
    LogRecord keys from the `extra` mapping if a KeyError occurs during
    LogRecord construction.
    """
    try:
        return _original_makeRecord(*args, **kwargs)
    except KeyError:
        # Defensive: if there's an 'extra' dict, remove reserved fields
        if 'extra' in kwargs and isinstance(kwargs['extra'], dict):
            for k in list(kwargs['extra'].keys()):
                if k in _LOGRECORD_RESERVED_KEYS:
                    kwargs['extra'].pop(k, None)
            # If extra became empty, remove it entirely
            if not kwargs['extra']:
                kwargs.pop('extra', None)

        # Also defensively remove reserved keys passed at top-level
        for k in list(kwargs.keys()):
            if k in _LOGRECORD_RESERVED_KEYS:
                kwargs.pop(k, None)

        return _original_makeRecord(*args, **kwargs)

logging.Logger.makeRecord = _makeRecord_safe

# Aplicar filtro global
pii_filter = PIIMaskingFilter()


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("dircom.payroll")
logger.addFilter(pii_filter)
logging.getLogger().addFilter(pii_filter) # Root logger filter

# Configurar directorios de logs
LOGS_DIR = BASE_DIR / "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# Formateador base para archivos
file_fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

# Server Log (Info and up)
server_handler = logging.handlers.RotatingFileHandler(LOGS_DIR / "server.log", maxBytes=10485760, backupCount=5)
server_handler.setFormatter(file_fmt)
server_handler.setLevel(logging.INFO)
logger.addHandler(server_handler)

# Capture root logs into our file too, but don't depend ONLY on it
logging.getLogger().addHandler(server_handler)

# Error Log (Error and Critical only)
error_handler = logging.handlers.RotatingFileHandler(LOGS_DIR / "error.log", maxBytes=10485760, backupCount=5)
error_handler.setFormatter(file_fmt)
error_handler.setLevel(logging.ERROR)
logger.addHandler(error_handler)

# Signature Log (Specific to the signature module)
signature_handler = logging.handlers.RotatingFileHandler(LOGS_DIR / "signature.log", maxBytes=10485760, backupCount=5)
signature_handler.setFormatter(file_fmt)
sig_logger = logging.getLogger("dircom.payroll.signature")
sig_logger.addHandler(signature_handler)
sig_logger.addFilter(pii_filter) # Apply PII filter here too
sig_logger.propagate = True


class StructuredFormatter(logging.Formatter):
    """
    Formatter para logging estructurado compatible con ELK/Datadog.
    
    Convierte logs a JSON con campos consistentes y parseables.
    Usa el dict 'extra' para campos adicionales.
    """
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Agregar campos extra si existen
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_data.update(record.extra)
        
        # Agregar exception info si existe
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


# Configurar handler con structured logging (solo en PRODUCTION)
if PRODUCTION:
    structured_handler = logging.StreamHandler()
    structured_handler.setFormatter(StructuredFormatter())
    # No limpiamos handlers para mantener los RotatingFileHandlers de arriba
    logger.addHandler(structured_handler)
    logger.info(
        "logging.structured_enabled",
        extra={"event_type": "logging.structured_enabled"}
    )

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no definida")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=config.DB_POOL_SIZE,
    max_overflow=config.DB_MAX_OVERFLOW,
    pool_recycle=config.DB_POOL_RECYCLE,
    pool_timeout=config.DB_POOL_TIMEOUT,
    connect_args={"connect_timeout": config.DB_CONNECT_TIMEOUT},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=config.REDIS_URL if config.REDIS_URL else None,
    in_memory_fallback_enabled=True,
    key_prefix="mymanagerh-limiter",
)


def get_db() -> Generator[Session, None, None]:
    """Yields a DB session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass  # Silently handle stale/broken connections


@contextmanager
def safe_transaction(db: Session):
    """
    Context manager for safe database transactions.
    Supports nested calls via SAVEPOINTs — uses an explicit depth counter
    because db.in_transaction() is ALWAYS True with autocommit=False.
    Only the outermost call does db.commit(). Inner calls use savepoints.
    """
    # Track nesting depth on the session object itself
    depth = getattr(db, '_safe_tx_depth', 0)
    db._safe_tx_depth = depth + 1

    if depth > 0:
        # Nested: use savepoint for isolation (e.g., per-page in batch processing)
        savepoint = db.begin_nested()
        try:
            yield
            savepoint.commit()
        except Exception:
            try:
                savepoint.rollback()
            except Exception:
                pass
            raise
        finally:
            db._safe_tx_depth -= 1
    else:
        # Top-level: full commit/rollback
        try:
            yield
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            raise
        finally:
            db._safe_tx_depth -= 1


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def purge_user_sessions(db: Session, user_id: str) -> None:
    """Delete session records from PostgreSQL and the Redis cache."""
    db.execute(text("DELETE FROM user_sessions WHERE user_id = :uid"), {"uid": user_id})
    if redis_service:
        try:
            redis_service.delete_sessions_for_user(user_id)
        except Exception as exc:
            logger.warning(f"redis.purge_user_sessions_failed: user_id={user_id} error={exc}")


def delete_session_by_hash(token_hash: str, user_id: Optional[str] = None) -> None:
    """Delete a specific session from PostgreSQL and Redis."""
    if redis_service:
        try:
            redis_service.delete_session(token_hash, user_id)
        except Exception as exc:
            logger.warning(f"redis.delete_session_failed: token_hash={token_hash} error={exc}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_write_file(dest_path: Union[str, Path], data: bytes) -> None:
    """
    GAP-L1-01: Atomic file write using tempfile + os.replace.
    Ensures that a partial write never leaves a corrupted file at dest_path.
    """
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    import tempfile
    import shutil
    # GAP-W1-02: Use system temp dir to avoid OneDrive/Antivirus locks during initial write
    fd, temp_path = tempfile.mkstemp(suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(fd)
            except OSError:
                pass

        # GAP-W1-01: Windows-specific robust replace with retry
        max_retries = 10
        for attempt in range(max_retries):
            try:
                # os.replace is atomic if on same drive, shutil.move handles cross-drive
                if os.path.exists(dest):
                    os.replace(temp_path, dest)
                else:
                    shutil.move(temp_path, dest)
                return
            except (PermissionError, OSError) as e:
                if attempt == max_retries - 1:
                    logger.error(f"file.replace_failed final_attempt={attempt} dest={dest} err={e}")
                    raise e
                time.sleep(0.2 * (attempt+1))
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e


def safe_remove_file(file_path: Union[str, Path], max_retries: int = 5) -> bool:
    """
    Windows-safe file deletion with retry logic.
    Handles file locks from antivirus, OneDrive indexing, or other processes.
    Returns True if successful, False if file doesn't exist or cleanup failed.
    """
    path = str(file_path)
    
    if not os.path.exists(path):
        return True  # Nothing to delete
    
    for attempt in range(max_retries):
        try:
            os.remove(path)
            logger.debug(f"file.removed path={path}")
            return True
        except (PermissionError, OSError) as e:
            if attempt == max_retries - 1:
                logger.warning(f"file.remove_failed final_attempt path={path} err={e}")
                return False
            # Wait before retry - gives antivirus/indexer time to release the file
            time.sleep(0.3 * (attempt + 1))
    
    return False


@contextmanager
def file_transaction(file_path: Union[str, Path]):
    """
    GAP-L2-01: Provides a transaction-like rollback for file operations.
    If the code block fails, the file is removed if it's new.
    """
    path = Path(file_path)
    existed = path.exists()
    try:
        yield
    except Exception:
        if not existed and path.exists():
            try:
                os.remove(path)
            except Exception:
                pass
        raise


def new_token() -> str:
    return secrets.token_urlsafe(32)




def validate_token_format(token: str) -> None:
    if not token:
        raise HTTPException(400, "invalid_token_format")
    t = token.strip()
    if not TOKEN_REGEX.match(t):
        raise HTTPException(400, "invalid_token_format")





def get_current_user(db: Session, session_token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not session_token:
        return None
    token_hash = hash_token(session_token)
    now = utc_now()

    # GAP-008 Fix: 5-minute grace period for OTP sessions.
    from datetime import timedelta
    grace_now = now - timedelta(minutes=5)

    if redis_service:
        try:
            cached = redis_service.get_session(token_hash)
            if cached:
                expires_at = cached.get("expires_at")
                if expires_at:
                    try:
                        expires_at_dt = datetime.fromisoformat(expires_at)
                    except Exception:
                        expires_at_dt = None
                    if expires_at_dt and expires_at_dt > now:
                        user_id = cached.get("user_id")
                        if user_id:
                            row = db.execute(text("""
                                SELECT u.id, u.email, u.full_name, u.role, u.organization_id, u.employee_id, u.is_active, u.user_status,
                                       u.tos_accepted, u.tos_accepted_at, u.tos_version,
                                       o.name as organization_name, o.cuit as organization_cuit, o.email as organization_email,
                                       (SELECT signature_path FROM user_signatures WHERE user_id = u.id AND is_active = true LIMIT 1) AS sig_path
                                FROM users u
                                LEFT JOIN organizations o ON o.id = u.organization_id
                                WHERE u.id = :user_id
                                  AND u.is_active = true
                            """), {"user_id": user_id}).fetchone()
                            if row:
                                m = row._mapping
                                emp_id = str(m["employee_id"]) if m["employee_id"] else None
                                if not emp_id and m["organization_id"] and m["email"]:
                                    res_emp = db.execute(text("""
                                        SELECT id FROM employees 
                                        WHERE LOWER(TRIM(email)) = LOWER(TRIM(:email)) 
                                          AND organization_id = :org_id 
                                          AND is_active = true
                                        LIMIT 1
                                    """), {"email": m["email"], "org_id": m["organization_id"]}).fetchone()
                                    if res_emp:
                                        emp_id = str(res_emp[0])
                                return {
                                    "id": str(m["id"]),
                                    "email": m["email"],
                                    "full_name": m["full_name"],
                                    "role": m["role"],
                                    "user_status": m["user_status"],
                                    "organization_id": str(m["organization_id"]) if m["organization_id"] else None,
                                    "employee_id": emp_id,
                                    "organization_name": m["organization_name"],
                                    "organization_cuit": m["organization_cuit"],
                                    "organization_email": m["organization_email"],
                                    "has_stored_signature": bool(m["sig_path"]),
                                    "tos_accepted": bool(m["tos_accepted"]),
                                    "tos_accepted_at": m["tos_accepted_at"],
                                    "tos_version": m["tos_version"],
                                }
        except Exception as exc:
            logger.warning(f"redis.session_lookup_failed: token_hash={token_hash} error={exc}")

    row = db.execute(text("""
        SELECT u.id, u.email, u.full_name, u.role, u.organization_id, u.employee_id, u.is_active, u.user_status,
                u.tos_accepted, u.tos_accepted_at, u.tos_version,
                o.name as organization_name, o.cuit as organization_cuit, o.email as organization_email,
                (SELECT signature_path FROM user_signatures WHERE user_id = u.id AND is_active = true LIMIT 1) AS sig_path
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        LEFT JOIN organizations o ON o.id = u.organization_id
        WHERE s.session_token_hash = :token_hash 
          AND u.is_active = true
          AND (
              s.expires_at > :now 
              OR (u.user_status = 'otp_session' AND s.expires_at > :grace_now)
          )
    """), {"token_hash": token_hash, "now": now, "grace_now": grace_now}).fetchone()
    if not row:
        return None
    # Normalize row to mapping for explicit and stable access
    m = row._mapping
    
    # GAP-024: Dynamic Employee Link (Robustness for Enterprise/Payroll hybrid)
    emp_id = str(m["employee_id"]) if m["employee_id"] else None
    if not emp_id and m["organization_id"] and m["email"]:
        # Fallback: look up by email + org_id
        res_emp = db.execute(text("""
            SELECT id FROM employees 
            WHERE LOWER(TRIM(email)) = LOWER(TRIM(:email)) 
              AND organization_id = :org_id 
              AND is_active = true
            LIMIT 1
        """), {"email": m["email"], "org_id": m["organization_id"]}).fetchone()
        if res_emp:
            emp_id = str(res_emp[0])

    user = {
        "id": str(m["id"]),
        "email": m["email"],
        "full_name": m["full_name"],
        "role": m["role"],
        "user_status": m["user_status"],
        "organization_id": str(m["organization_id"]) if m["organization_id"] else None,
        "employee_id": emp_id,
        "organization_name": m["organization_name"],
        "organization_cuit": m["organization_cuit"],
        "organization_email": m["organization_email"],
        "has_stored_signature": bool(m["sig_path"]),
        "tos_accepted": bool(m["tos_accepted"]),
        "tos_accepted_at": m["tos_accepted_at"],
        "tos_version": m["tos_version"],
    }

    if redis_service:
        try:
            expires_at = m["expires_at"] if "expires_at" in m else None
            if not expires_at:
                expires_at = now + timedelta(hours=SESSION_TTL_HOURS)
            session_data = {
                "user_id": user["id"],
                "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at),
            }
            ttl = int((expires_at - now).total_seconds()) if hasattr(expires_at, "total_seconds") else SESSION_TTL_HOURS * 3600
            if ttl > 0:
                redis_service.set_session(token_hash, session_data, ttl)
        except Exception as exc:
            logger.warning(f"redis.session_cache_write_failed: token_hash={token_hash} error={exc}")

    return user


def require_auth(
    request: Request,
    session_token: Optional[str] = Cookie(default=None, alias="session"),
    db: Session = Depends(get_db),
):
    """
    Dependency that ensures the user is authenticated.
    Supports both 'session' cookie and 'Authorization: Bearer <token>' header.
    """
    token = session_token
    
    # Try header if cookie is missing
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "").strip()

    if not token:
        token = request.headers.get("X-Session-Token") or request.headers.get("X-Auth-Token")

    user = get_current_user(db, token)
    if not user:
        logger.warning(
            "auth.failed",
            extra={
                "ip": get_real_ip(request),
                "has_token": bool(token),
                "auth_method": "bearer" if "Bearer " in (request.headers.get("Authorization") or "") else "session"
            }
        )
        raise HTTPException(401, "not_authenticated")
    
    # Phase 1 Hardening: Row-Level Security (RLS) Session Injection
    if user.get("organization_id"):
        try:
            db.execute(text("SET app.current_org_id = :oid"), {"oid": user["organization_id"]})
        except Exception as e:
            logger.error(f"rls.session_init_failed: {e}")
            
    return user


def require_admin(user: Dict = Depends(require_auth)):
    if user["role"] != "admin":
        raise HTTPException(403, "admin_required")
    return user


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def create_session(db: Session, user_id: str, request: Request) -> str:
    token = new_token()
    token_hash = hash_token(token)
    expires_at = utc_now() + timedelta(hours=SESSION_TTL_HOURS)
    db.execute(text("""
        INSERT INTO user_sessions (user_id, session_token_hash, expires_at, ip_address, user_agent)
        VALUES (:user_id, :token_hash, :expires_at, :ip, :ua)
    """), {
        "user_id": user_id,
        "token_hash": token_hash,
        "expires_at": expires_at,
        "ip": get_real_ip(request),
        "ua": request.headers.get("User-Agent", "unknown")[:500],
    })
    if redis_service:
        try:
            redis_service.set_session(
                token_hash,
                {
                    "user_id": user_id,
                    "expires_at": expires_at.isoformat(),
                },
                int((expires_at - utc_now()).total_seconds()),
            )
        except Exception as exc:
            logger.warning(f"redis.session_cache_write_failed: user_id={user_id} error={exc}")
    return token



def audit(
    db: Session,
    organization_id: Optional[str],
    actor_type: str,
    actor_id: Optional[str],
    action: str,
    entity_id: Optional[str],
    data: Dict[str, Any],
    request_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> None:
    # Normalize/fallback null/invalid organization_id to nil UUID to prevent NOT NULL and UUID format errors
    if not organization_id or str(organization_id).strip().lower() in ("none", "null", ""):
        organization_id = "00000000-0000-0000-0000-000000000000"

    # PRV-001 FIX: Redact PII before storing in audit log
    safe_data = redact_pii(data or {})
    
    # Inject correlation IDs if provided
    if request_id:
        safe_data["request_id"] = request_id
    if trace_id:
        safe_data["trace_id"] = trace_id

    from sqlalchemy.exc import IntegrityError

    # We use a nested transaction (Savepoint) to avoid poisoning the main transaction block
    try:
        with db.begin_nested():
            db.execute(text("""
                INSERT INTO audit_log (organization_id, actor_type, actor_id, action, entity_id, data)
                VALUES (:org, :actor_type, :actor_id, :action, :entity_id, :data)
            """), {
                "org": organization_id,
                "actor_type": actor_type,
                "actor_id": actor_id,
                "action": action,
                "entity_id": entity_id,
                "data": json.dumps(safe_data),
            })
    except IntegrityError as e:
        err_msg = str(e).lower()
        if "audit_log_pkey" in err_msg or "duplicate key" in err_msg:
            logger.warning("audit.sequence_out_of_sync: Catching audit_log duplicate key. Syncing sequence and retrying...")
            try:
                # Sync the sequence to the maximum ID + 1
                db.execute(text("""
                    SELECT setval('audit_log_id_seq', COALESCE((SELECT MAX(id) FROM audit_log), 0) + 1, false)
                """))
                # Retry the insert cleanly
                db.execute(text("""
                    INSERT INTO audit_log (organization_id, actor_type, actor_id, action, entity_id, data)
                    VALUES (:org, :actor_type, :actor_id, :action, :entity_id, :data)
                """), {
                    "org": organization_id,
                    "actor_type": actor_type,
                    "actor_id": actor_id,
                    "action": action,
                    "entity_id": entity_id,
                    "data": json.dumps(safe_data),
                })
                logger.info("audit.sequence_synced_and_retried_successfully")
            except Exception as retry_err:
                logger.error(f"audit.self_healing_failed: {retry_err}")
                raise e
        else:
            raise e



def normalize_cuil(cuil: Optional[str]) -> Optional[str]:
    if not cuil:
        return None
    return re.sub(r"\D", "", cuil)


def normalize_dni(dni: str) -> str:
    """Remueve todo lo que no sea d  gito y valida longitud (7-8 d  gitos)."""
    if not dni:
        raise HTTPException(400, "dni_is_required")
    clean = re.sub(r"\D", "", str(dni))
    if not re.fullmatch(r"\d{7,8}", clean):
        raise HTTPException(400, "dni_invalido_formato")
    return clean


def sync_signer_image_from_db(db, signer_id: str) -> Optional[str]:
    """
    Checks if a signer image exists on disk. If not, attempts to restore it from DB (BYTEA).
    Returns the path if exists or restored, None otherwise.
    """
    row = db.execute(
        text("SELECT signature_image_path, signature_image_data FROM company_signers WHERE id = :id"),
        {"id": signer_id}
    ).fetchone()

    if not row or not row.signature_image_path:
        return None

    path = Path(row.signature_image_path)
    if path.exists():
        return str(path)

    if row.signature_image_data:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(row.signature_image_data)
            logger.info(f"signature_restored_from_db: {signer_id} -> {path}")
            return str(path)
        except Exception as e:
            logger.error(f"error_restoring_signature_from_db: {signer_id} - {e}")
    
    return None


def normalize_org_name(name: str) -> str:
    if not name:
        return ""
    return re.sub(r"\s+", " ", name.strip())


def ensure_storage_dirs() -> None:
    """Asegura que existan todos los directorios de almacenamiento necesarios."""
    os.makedirs(ALLOWED_STORAGE_DIR, exist_ok=True)
    os.makedirs(os.path.join(ALLOWED_STORAGE_DIR, "batches"), exist_ok=True)
    os.makedirs(os.path.join(ALLOWED_STORAGE_DIR, "receipts"), exist_ok=True)
    
    # Estructura de firmas (nueva arquitectura modularizada)
    os.makedirs(os.path.join(ALLOWED_STORAGE_DIR, "signatures", "employer"), exist_ok=True)
    os.makedirs(os.path.join(ALLOWED_STORAGE_DIR, "signatures", "employee"), exist_ok=True)
    os.makedirs(os.path.join(ALLOWED_STORAGE_DIR, "signatures", "company"), exist_ok=True)
    
    logger.debug(f"storage_dirs_ensured storage_path={ALLOWED_STORAGE_DIR}")


def build_storage_path(org_id: str, category: str, filename: str, subfolder: Optional[str] = None) -> str:
    """
    Centralized path builder for all system assets.
    Enforces organization-level segregation and absolute paths.
    GAP-016: Prevents path leakage and redundant nested folders.
    Returns: Absolute path string.
    """
    # 1. Strict Validation (Industrial Hardening)
    if not org_id:
        raise ValueError("organization_id_required")
    
    org_str = str(org_id).strip()
    if org_str.lower() in ("none", "null", "default", ""):
        logger.error(f"security.path_leak_detected org={org_str} category={category} file={filename}")
        raise ValueError(f"invalid_organization_id_for_storage: {org_str}")

    # 2. Path Assembly (Ensures structure: storage/[category]/[org_id]/[subfolder?]/[filename])
    # Note: Use category.lower() to keep filesystem consistent (batches, receipts, signatures)
    base = Path(ALLOWED_STORAGE_DIR) / category.lower() / org_str
    
    if subfolder:
        # Sanitize subfolder to avoid relative traversal (e.g. "signed")
        clean_sub = re.sub(r'[^a-zA-Z0-9_\-]', '_', subfolder)
        base = base / clean_sub
        
    # Ensure directory exists
    base.mkdir(parents=True, exist_ok=True)
    
    # 3. Security: Prevent path traversal in filename
    clean_filename = os.path.basename(filename)
    full_path = (base / clean_filename).resolve()
    
    # Final boundary check (Ensure we are still inside ALLOWED_STORAGE_DIR)
    root_resolved = Path(ALLOWED_STORAGE_DIR).resolve()
    if not str(full_path).lower().startswith(str(root_resolved).lower()):
         raise ValueError(f"security.path_traversal_attempt: {full_path}")
         
    return str(full_path)


def safe_join_under_storage(*parts: str) -> str:
    base_dir = os.path.abspath(ALLOWED_STORAGE_DIR)
    path = os.path.abspath(os.path.join(base_dir, *parts))
    
    # GAP-L1-X: Avoid prefix path-traversal by using strict structural path comparison instead of startswith string matching
    try:
        if os.path.commonpath([base_dir, path]) != base_dir:
            raise HTTPException(403, "invalid_path")
    except ValueError:
        raise HTTPException(403, "invalid_path")
        
    return path


def resolve_storage_path(path_str: str) -> str:
    if not path_str:
        raise ValueError("empty_storage_path")

    candidate = Path(path_str)
    if candidate.is_absolute():
        resolved = candidate.resolve()
        root = Path(ALLOWED_STORAGE_DIR).resolve()
        if root not in resolved.parents and resolved != root:
            raise ValueError(f"storage_path_outside_allowed_dir: {resolved}")
        return str(resolved)

    # Strip optional leading storage prefix for legacy paths.
    parts = list(candidate.parts)
    while parts and parts[0] in (".", "storage"):
        parts.pop(0)

    if not parts:
        raise ValueError("empty_storage_path")

    return safe_join_under_storage(*parts)


def compute_file_sha256(file_path: Union[str, Path]) -> str:
    """Calcula el SHA-256 de un archivo f  sico en chunks."""
    path = str(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    
    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE:
        raise HTTPException(413, "file_too_large")
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def validate_pdf_magic(path: str) -> None:
    with open(path, "rb") as f:
        if f.read(5) != b"%PDF-":
            raise HTTPException(400, "invalid_pdf_format")


def save_bytes_atomically(data: bytes, dest_path: Union[str, Path]) -> None:
    """
    Saves bytes to a destination atomically using a temp file and os.replace.
    Includes a retry loop for Windows-specific locking issues (e.g., OneDrive).
    """
    import tempfile
    import time
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    # We use a context manager for the file descriptor to ensure it's closed before replace
    fd, temp_path = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        
        # Windows retry loop (Mitigates WinError 32: Permission denied during sync)
        for i in range(5):
            try:
                os.replace(temp_path, dest)
                return
            except PermissionError:
                if i == 4: raise
                time.sleep(0.1 * (i + 1))
    except Exception as e:
        # I-003 FIX: fd is already closed by os.fdopen() — do NOT double-close
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        raise e


def write_upload_to_disk(upload, dest_path: str) -> None:
    """
    Refactored to use atomic tempfile approach with support for large files.
    """
    import tempfile
    import time
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    fd, temp_path = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    total = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FILE_SIZE:
                    raise HTTPException(413, "file_too_large")
                out.write(chunk)
        
        # Windows retry loop
        for i in range(5):
            try:
                os.replace(temp_path, dest)
                return
            except PermissionError:
                if i == 4: raise
                time.sleep(0.1 * (i + 1))
    except Exception as e:
        # I-003 FIX: fd is already closed by os.fdopen() — do NOT double-close
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        raise e


# =============================================================================
# VALIDATION HELPERS (Added in Phase 1 refactoring)
# =============================================================================

def validate_email_format(email: str) -> bool:
    """Valida formato de email con regex."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def sanitize_text_input(
    text: str,
    min_length: int = 1,
    max_length: int = 1000,
    field_name: str = "text"
) -> str:
    """Sanitiza y valida input de texto."""
    if not isinstance(text, str):
        raise HTTPException(400, f"{field_name}_must_be_string")
    sanitized = text.strip()
    if len(sanitized) < min_length:
        raise HTTPException(400, f"{field_name}_too_short")
    if len(sanitized) > max_length:
        raise HTTPException(400, f"{field_name}_too_long")
    return sanitized.replace("<", "").replace(">", "")


def validate_organization_access(
    user: Dict[str, Any],
    resource_organization_id: str,
    resource_type: str = "resource"
) -> None:
    """Valida que el usuario tiene acceso al recurso de la organizaci  n."""
    user_org_id = user.get("organization_id")
    if not user_org_id or str(user_org_id) != str(resource_organization_id):
        raise HTTPException(403, f"{resource_type}_access_denied")


def create_signature_token(
    receipt_id: str,
    employee_id: str,
    organization_id: str,
    expires_at: Optional[datetime] = None
) -> str:
    """
    Genera un token firmado (HMAC-SHA256) que contiene los IDs necesarios
    para la firma de un recibo. Devuelve un string url-safe.
    """
    payload = {
        "receipt_id": str(receipt_id),
        "employee_id": str(employee_id),
        "organization_id": str(organization_id),
        "exp": expires_at.timestamp() if expires_at else None,
        # Phase 2 Fix: Include Nonce to force uniqueness and prevent replay attacks
        "nonce": secrets.token_hex(16)
    }
    
    # Serializar a JSON compacto
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_bytes = payload_json.encode("utf-8")
    
    # Firmar con SECRET_KEY
    secret = SECRET_KEY.encode("utf-8")
    signature = hmac.new(secret, payload_bytes, hashlib.sha256).digest()
    
    # Codificar en Base64 URL-safe (sin padding para limpieza)
    p_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    s_b64 = base64.urlsafe_b64encode(signature).decode("utf-8").rstrip("=")
    
    return f"{p_b64}.{s_b64}"


def get_existing_signature_request(
    db: Session, receipt_id: str
) -> Optional[Dict[str, Any]]:
    """
    Returns the existing pending+non-expired signature_request for a receipt,
    without the raw token (since it's not stored).
    Returns None if no valid pending SR exists.
    Used by read-only GET endpoints to avoid token churn.
    """
    row = db.execute(text("""
        SELECT id, token_hash, token_expires_at
        FROM signature_requests
        WHERE receipt_id = :rid
          AND status = 'pending'
          AND token_expires_at > :now
        ORDER BY requested_at DESC
        LIMIT 1
    """), {"rid": receipt_id, "now": utc_now()}).fetchone()
    if not row:
        return None
    return {"sr_id": str(row.id), "token_hash": row.token_hash, "expires_at": row.token_expires_at}


def create_signature_request(
    db: Session, receipt_id: str, organization_id: str, employee_id: str,
    issuer_ip: Optional[str] = None, issuer_ua: Optional[str] = None,
    issuer_user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Crea un nuevo signature_request con token   nico.
    GAP-001/020: Locks the receipt row (FOR UPDATE) before replacing any
    pending token, preventing concurrent duplicate inserts.
    The caller must already be inside a safe_transaction() block.
    """
    # 1. Detect source and lock
    source = "payroll"
    row = None
    try:
        from uuid import UUID
        # Check new architecture first
        row = db.execute(text("SELECT id FROM receipts WHERE id = :rid FOR UPDATE"), {"rid": receipt_id}).fetchone()
        if row:
            source = "enterprise"
    except ValueError:
        pass
        
    if not row:
        # Check legacy architecture
        row = db.execute(text("SELECT id FROM payroll_receipts WHERE id = :rid FOR UPDATE"), {"rid": receipt_id}).fetchone()
        if not row:
             return None # Or raise 404

    # 2. Delete any existing pending SR for this receipt (Dual-FK way)
    rid_col = "receipt_id" if source == "payroll" else "enterprise_receipt_id"
    db.execute(text(f"DELETE FROM signature_requests WHERE {rid_col} = :rid AND status = 'pending'"), {"rid": receipt_id})

    # 3. Create fresh signature request token
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    expires_at = utc_now() + timedelta(hours=int(os.getenv("TOKEN_TTL_HOURS", "48")))

    if source == "enterprise":
        # Enterprise: receiver is a user, stored in employee_id column for unified access
        db.execute(text("""
            INSERT INTO signature_requests (
                id, enterprise_receipt_id, employee_id, organization_id,
                token_hash, token_expires_at, status, document_source,
                issuer_ip, issuer_ua, requires_verification, issuer_user_id
            )
            VALUES (uuid_generate_v4(), :receipt_id, :employee_id, :org_id, :token_hash, :expires_at, 'pending', 'enterprise',
                    CAST(:ip AS inet), :ua, :requires_v, :issuer_uid)
        """), {
            "receipt_id": receipt_id,
            "employee_id": employee_id,
            "org_id": organization_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "ip": issuer_ip,
            "ua": issuer_ua[:500] if issuer_ua else None,
            "requires_v": True,  # Default to True for now
            "issuer_uid": issuer_user_id
        })
    else:
        # Legacy payroll: employee_id FK is valid
        db.execute(text("""
            INSERT INTO signature_requests (
                id, receipt_id, employee_id, organization_id,
                token_hash, token_expires_at, status, document_source,
                issuer_ip, issuer_ua, requires_verification, issuer_user_id
            )
            VALUES (uuid_generate_v4(), :receipt_id, :employee_id, :org_id, :token_hash, :expires_at, 'pending', 'payroll',
                    CAST(:ip AS inet), :ua, :requires_v, :issuer_uid)
        """), {
            "receipt_id": receipt_id,
            "employee_id": employee_id,
            "org_id": organization_id,
            "token_hash": token_hash,
            "expires_at": expires_at,
            "ip": issuer_ip,
            "ua": issuer_ua[:500] if issuer_ua else None,
            "requires_v": True,  # Default to True
            "issuer_uid": issuer_user_id
        })
    return {"token": token, "sign_url": f"/api/signature-requests/{token}", "expires_at": expires_at}
