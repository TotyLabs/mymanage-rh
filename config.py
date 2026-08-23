"""
config.py

Configuraci\u00f3n centralizada del sistema Dircom Payroll.
Define constantes, rutas, y par\u00e1metros de operaci\u00f3n que antes estaban dispersos.

Evita hardcodes, permite overrides via env vars, y documenta el comportamiento esperado.
"""

import os
from pathlib import Path


# =============================================================================
# BASE CONFIG
# =============================================================================

PRODUCTION = os.getenv("PRODUCTION", "false").lower() == "true"
LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING" if PRODUCTION else "INFO")
DATABASE_URL = os.getenv("DATABASE_URL")
BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "ui"
SYSTEM_NAME = os.getenv("SYSTEM_NAME", "MyManageRH")

# =============================================================================
# DATABASE POOL (wired to .env, consumed by payroll_core.py)
# =============================================================================
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10" if PRODUCTION else "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "15" if PRODUCTION else "5"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "15"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "300"))
DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

# =============================================================================
# REDIS / CACHE CONFIGURATION
# =============================================================================

REDIS_URL = os.getenv("REDIS_URL")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "mymanagerh")
REDIS_DEFAULT_TIMEOUT = int(os.getenv("REDIS_DEFAULT_TIMEOUT", "5"))

# =============================================================================
# EXTERNAL ACCESS CONFIGURATION (Ngrok / Production)
# =============================================================================

SYSTEM_PUBLIC_URL = os.getenv("SYSTEM_PUBLIC_URL")

def _detect_ngrok_url():
    """Auto-detect active ngrok tunnel URL via local API (http://127.0.0.1:4040)."""
    try:
        import urllib.request, json
        resp = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2)
        data = json.loads(resp.read())
        for tunnel in data.get("tunnels", []):
            public_url = tunnel.get("public_url", "")
            if public_url.startswith("https://"):
                return public_url
            if public_url.startswith("http://"):
                return public_url
    except Exception as e:
        import urllib.error
        import logging
        is_expected = False
        if isinstance(e, urllib.error.URLError):
            reason = getattr(e, "reason", None)
            if reason:
                if isinstance(reason, ConnectionRefusedError) or "Connection refused" in str(reason) or "[Errno 111]" in str(reason) or "timed out" in str(reason):
                    is_expected = True
        if not is_expected:
            logging.getLogger("dircom.payroll.config").debug(f"Ngrok detection error: {e}")
        # No logging here to avoid flooding if ngrok isn't used
        pass
    return None

# Prioridad: SYSTEM_PUBLIC_URL (fijo) > ngrok auto-detect > NGROK_PUBLIC_URL (env) > localhost
if SYSTEM_PUBLIC_URL:
    BASE_PUBLIC_URL = SYSTEM_PUBLIC_URL.rstrip("/")
else:
    _ngrok_auto = _detect_ngrok_url() if not PRODUCTION else None
    _ngrok_env = os.getenv("NGROK_PUBLIC_URL") if not PRODUCTION else None
    
    if _ngrok_auto:
        BASE_PUBLIC_URL = _ngrok_auto.rstrip("/")
        import logging
        logging.getLogger("dircom.payroll.config").info(
            f"NGROK AUTO-DETECTED: {BASE_PUBLIC_URL}"
        )
    elif _ngrok_env:
        BASE_PUBLIC_URL = _ngrok_env.rstrip("/")
    else:
        BASE_PUBLIC_URL = "http://localhost:8000"

# =============================================================================
# ENVIRONMENT BINARIES (PostgreSQL, etc)
# =============================================================================

POSTGRES_BIN_PATH = os.getenv("POSTGRES_BIN_PATH", "") # Si vac\u00edo, usa PATH


# =============================================================================
# STORAGE CONFIGURATION
# =============================================================================

STORAGE_PATH = os.getenv("STORAGE_PATH", "./storage")
ALLOWED_STORAGE_DIR = os.path.abspath(STORAGE_PATH)
STORAGE_ROOT = Path(ALLOWED_STORAGE_DIR)


# File size: reads MB from env, converts to bytes. Falls back to legacy BYTES env.
_max_upload_mb = os.getenv("MAX_UPLOAD_SIZE_MB")
if _max_upload_mb:
    MAX_FILE_SIZE = int(_max_upload_mb) * 1024 * 1024
else:
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_BYTES", str(50 * 1024 * 1024)))

# Signature storage subdirectory
SIGNATURE_STORAGE_PATH = os.path.join(STORAGE_PATH, "signatures")

# General uploads and DNI storage
UPLOAD_DIR = os.path.join(STORAGE_PATH, "uploads")
DNI_STORAGE_PATH = os.path.join(UPLOAD_DIR, "dni")


# =============================================================================
# SIGNATURE CONFIGURATION
# =============================================================================

# VersiÃ³n del motor de firma:
# - "v1": Firma manuscrita (PNG) + Sello lateral
# - "v2": Formal Signature Seal (QR + Info) - SIN firma manuscrita
SIGNATURE_VERSION = os.getenv("SIGNATURE_VERSION", "v1")
SIGNATURE_MODE = os.getenv("SIGNATURE_MODE", "hybrid")
ALLOW_V1_FALLBACK = os.getenv("ALLOW_V1_FALLBACK", "false").lower() == "true"

# Coordenadas fallback para estampado de firma (si no se encuentra texto o mode=coordinates_only)
# Formato: {"rol": {"x": pixels_desde_izquierda, "y": pixels_desde_arriba}}
SIGNATURE_POSITIONS = {
    "employer": {
        "x": int(os.getenv("SIGNATURE_EMPLOYER_X", "150")),
        "y": int(os.getenv("SIGNATURE_EMPLOYER_Y", "700")),
    },
    "employee": {
        "x": int(os.getenv("SIGNATURE_EMPLOYEE_X", "350")),
        "y": int(os.getenv("SIGNATURE_EMPLOYEE_Y", "700")),
    },
}

# Tiempos de vida de tokens de firma (en horas)
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "48"))

# M\u00e1ximo n\u00famero de intentos de firma antes de expirar el token
MAX_SIGNATURE_ATTEMPTS = int(os.getenv("MAX_SIGNATURE_ATTEMPTS", "3"))


# =============================================================================
# AUTHENTICATION & SESSION
# =============================================================================

SESSION_TTL_HOURS = int(os.getenv("SESSION_TTL_HOURS", "168"))
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Password Reset
PASSWORD_RESET_TTL_MINUTES = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "20"))


# =============================================================================
# OTP / VERIFICATION
# =============================================================================
OTP_EXPIRATION_MINUTES = int(os.getenv("OTP_EXPIRATION_MINUTES", "10"))
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))

# Soft-match validation for frictionless signature (v2)
SOFT_MATCH_IP_PREFIX_LENGTH = 24
SOFT_MATCH_REQUIRE_SAME_DEVICE = True


# =============================================================================
# SMTP & EMAIL CONFIGURATION
# =============================================================================

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").lower()

# EMAIL_MODE: "sandbox" (log only) or "production" (real send)
EMAIL_MODE = os.getenv("EMAIL_MODE", "console")
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip() or None


# =============================================================================
# SMS CONFIGURATION (Twilio)
# =============================================================================

# SMS_MODE: "console" (log only, dev) or "twilio" (real send, prod)
SMS_MODE = os.getenv("SMS_MODE", "twilio")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")  # e.g. +5411...



# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================

SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    # Phase 2 Fix: Removed insecure default fallback. 
    # SECRET_KEY is MANDATORY for all environments to prevent token forgery.
    raise RuntimeError("CRITICAL: SECRET_KEY env var is REQUIRED. Set it in .env.")


# =============================================================================
# APPLICATION-LEVEL ENVELOPE ENCRYPTION
# =============================================================================

# Feature flag for sensitive file encryption. Production deployments that handle
# real payroll data should set this to true after the migration is applied.
APP_ENCRYPTION_ENABLED = os.getenv("APP_ENCRYPTION_ENABLED", "false").lower() == "true"

# Provider options: aws, gcp, local. Local is for development/testing only.
APP_ENCRYPTION_PROVIDER = os.getenv("APP_ENCRYPTION_PROVIDER", "local").lower()
APP_ENCRYPTION_KMS_KEY_ID = os.getenv("APP_ENCRYPTION_KMS_KEY_ID", "")
APP_ENCRYPTION_AWS_REGION = os.getenv("APP_ENCRYPTION_AWS_REGION", "")

# Required only for APP_ENCRYPTION_PROVIDER=local. Must be base64 for 32 bytes.
APP_ENCRYPTION_LOCAL_MASTER_KEY = os.getenv("APP_ENCRYPTION_LOCAL_MASTER_KEY", "")

if PRODUCTION and APP_ENCRYPTION_ENABLED and APP_ENCRYPTION_PROVIDER == "local":
    raise RuntimeError("CRITICAL: local encryption provider is not allowed in production.")



# =============================================================================
# REGEX PATTERNS
# =============================================================================

import re

TOKEN_REGEX = re.compile(r"^[a-zA-Z0-9\-_]{32,128}$")
CUIL_REGEX = re.compile(r"(\d{2}[-.\s]?\d{8}[-.\s]?\d|\d{11})")


# =============================================================================
# SIGNATURE TYPE RULES
# =============================================================================

# Tipos de firma soportados:
# - empresa (employer): Siempre autom\u00e1tica, mediante PNG placeholder o real
# - empleado (employee): Siempre manual/electr\u00f3nica via canvas frontend
SIGNATURE_TYPES = {
    "employer": {
        "support_automatic": True,      # Puede firmarse autom\u00e1ticamente
        "support_manual": False,        # No permite manual
        "storage_subdir": "employer",
        "default_storage": True,        # Guarda firma autom\u00e1tica en storage
    },
    "employee": {
        "support_automatic": False,     # No permite autom\u00e1tica
        "support_manual": True,         # Debe ser manual
        "storage_subdir": "employee",
        "default_storage": True,
    },
}


# =============================================================================
# PDF STAMPING CONFIGURATION
# =============================================================================

# Hardening limits
MAX_PDF_PAGES = int(os.getenv("MAX_PDF_PAGES", "1000"))
PDF_PROCESSING_TIMEOUT = float(os.getenv("PDF_PROCESSING_TIMEOUT", "30.0"))

# Tama\u00f1o de firma estampada (en puntos del PDF)

SIGNATURE_STAMP_WIDTH = int(os.getenv("SIGNATURE_STAMP_WIDTH", "144"))
SIGNATURE_STAMP_HEIGHT = int(os.getenv("SIGNATURE_STAMP_HEIGHT", "60"))

# Margen desde el borde de la p\u00e1gina (en puntos)
SIGNATURE_STAMP_MARGIN = int(os.getenv("SIGNATURE_STAMP_MARGIN", "20"))

# Dimensiones del sello de validaci  n (Seal) - Industrial Standard
SIGNATURE_SEAL_WIDTH = int(os.getenv("SIGNATURE_SEAL_WIDTH", "270"))
SIGNATURE_SEAL_HEIGHT = int(os.getenv("SIGNATURE_SEAL_HEIGHT", "50"))

# SYSTEM_NAME is now sourced from env (line ~23, section 1)

# Signature Image Defaults (Phase 23 Refinement - "Golden Ratio")
SIGNATURE_MAX_WIDTH = 100
SIGNATURE_MIN_WIDTH = 70
SIGNATURE_HEIGHT = 34
SIGNATURE_WIDTH_RATIO = 0.65 # Balance ideal entre texto y espacio

# Informaci\u00f3n adicional a incluir en la firma (metadata)
INCLUDE_SIGNER_NAME_IN_STAMP = os.getenv("INCLUDE_SIGNER_NAME_IN_STAMP", "true").lower() == "true"
INCLUDE_TIMESTAMP_IN_STAMP = os.getenv("INCLUDE_TIMESTAMP_IN_STAMP", "true").lower() == "true"


# =============================================================================
# AUDIT & EVIDENCE CONFIGURATION
# =============================================================================

# Campos obligatorios a registrar en signature_evidence al firmar empleado
SIGNATURE_EVIDENCE_FIELDS = [
    "receipt_id",
    "employee_id",
    "organization_id",
    "timestamp",
    "ip_address",
    "user_agent",
    "hash_pdf_before",
    "hash_pdf_after",
    "hash_signature_image",
    "token_used",
]

# Evitar doble firma
PREVENT_DOUBLE_SIGNING = os.getenv("PREVENT_DOUBLE_SIGNING", "true").lower() == "true"


# =============================================================================
# VALIDATION CONFIGURATION
# =============================================================================

# Tama\u00f1o m\u00ednimo aceptado para una imagen de firma (bytes)
MIN_SIGNATURE_IMAGE_SIZE = 200

# Tama\u00f1o m\u00e1ximo para una imagen de firma (bytes)
MAX_SIGNATURE_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


# =============================================================================
# ERROR HANDLING
# =============================================================================

# Mensajes de error est\u00e1ndar (sin exponer detalles internos)
ERROR_MESSAGES = {
    "signature_already_exists": "El recibo ya fue firmado por el empleado",
    "signature_not_found": "Firma no encontrada",
    "pdf_integrity_failed": "Integridad del PDF comprometida",
    "invalid_signature_image": "Imagen de firma inv\u00e1lida",
    "signature_too_small": "Imagen de firma demasiado peque\u00f1a",
    "pdf_not_found": "PDF no encontrado",
}


# =============================================================================
# X.509 DIGITAL SIGNATURE CONFIGURATION
# =============================================================================
# X.509 Configuration (Standard & Phase 3 PKI)
# Using absolute resolved paths to avoid CWD issues on Windows/OneDrive
X509_CERT_PATH = os.getenv("X509_CERT_PATH", str((BASE_DIR / "certs" / "signer_cert.crt").resolve()))
X509_KEY_PATH = os.getenv("X509_KEY_PATH", str((BASE_DIR / "certs" / "root_key.pem").resolve()))
ROOT_CA_PATH = os.getenv("ROOT_CA_PATH", str((BASE_DIR / "certs" / "root_ca.crt").resolve()))
ROOT_KEY_PATH = os.getenv("ROOT_KEY_PATH", str((BASE_DIR / "certs" / "root_key.pem").resolve()))

# Adobe-Compliant .p12 Bundle (Hierarchical PKI)
X509_P12_PATH = os.getenv("X509_P12_PATH", str((BASE_DIR / "certs" / "signer.p12").resolve()))
X509_CRL_PATH = os.getenv("X509_CRL_PATH", str((BASE_DIR / "certs" / "root_ca.crl").resolve()))
X509_P12_PASSWORD = os.getenv("X509_P12_PASSWORD", "")
if not X509_P12_PASSWORD and PRODUCTION:
    raise RuntimeError("CRITICAL: X509_P12_PASSWORD env var is REQUIRED in production. Set it in .env.")

STRICT_REVOCATION_CHECK = os.getenv("STRICT_REVOCATION_CHECK", "true").lower() == "true"

# HSM / KMS Storage Configuration (PKCS#11 compliance)
HSM_ENABLED = os.getenv("HSM_ENABLED", "false").lower() == "true"
HSM_LIB_PATH = os.getenv("HSM_LIB_PATH", "/usr/lib/libsofthsm2.so")
HSM_SLOT = int(os.getenv("HSM_SLOT", "0"))
HSM_PIN = os.getenv("HSM_PIN", "")
if HSM_ENABLED and not HSM_PIN:
    raise RuntimeError("CRITICAL: HSM_PIN is required when HSM_ENABLED=true. Set it in .env.")

CERT_PATH = Path(X509_CERT_PATH)
KEY_PATH = Path(X509_KEY_PATH)

TSA_URL = os.getenv("TSA_URL", "http://timestamp.digicert.com")
CONTACT_INFO = os.getenv("CONTACT_INFO", "mymanagerh.payroll@gmail.com")

# =============================================================================
# VALIDATION & SANITY CHECK
# =============================================================================

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL no definida")

if SIGNATURE_MODE not in ("hybrid", "coordinates_only"):
    raise ValueError(f"SIGNATURE_MODE inv\u00e1lido: {SIGNATURE_MODE}")


# =============================================================================
# EMAIL FALLBACK CONFIGURATION
# =============================================================================

EMAIL_FALLBACK_ENABLED = os.getenv("EMAIL_FALLBACK_ENABLED", "true").lower() == "true"

GMAIL_FALLBACK_HOST = os.getenv("GMAIL_FALLBACK_HOST", "smtp.gmail.com")
GMAIL_FALLBACK_PORT = int(os.getenv("GMAIL_FALLBACK_PORT", "587"))
GMAIL_FALLBACK_SECURITY = os.getenv("GMAIL_FALLBACK_SECURITY", "starttls").lower()
GMAIL_FALLBACK_USER = os.getenv("GMAIL_FALLBACK_USER")
GMAIL_FALLBACK_PASSWORD = os.getenv("GMAIL_FALLBACK_PASSWORD")
