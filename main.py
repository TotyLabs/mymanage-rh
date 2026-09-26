"""
Dircom Payroll - Sistema de Firma Electr  nica de Recibos
Version: 4.2.3 (Optimized Routing & Debugging)
"""

from dotenv import load_dotenv
load_dotenv()

import os
from pathlib import Path
import asyncio
from datetime import timedelta
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.exception_handlers import http_exception_handler as default_http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from slowapi import _rate_limit_exceeded_handler
from fastapi.exceptions import RequestValidationError
from fastapi import status
import config
import uuid
from services import secure_temp

from payroll_core import (
    PRODUCTION,
    engine,
    get_db,
    limiter,
    utc_now,
    UI_DIR,
    logger,
    SessionLocal,
    STORAGE_ROOT,
    EmailSendFailedError,
)
from services.webhook_service import start_outbox_drain_loop
from services.legajo.job_worker import start_import_job_drain_loop
from metrics.middleware import MetricsMiddleware, start_periodic_metrics_flusher
from metrics.registry import metrics_registry
from metrics.exporter import MetricsExporter
from metrics.store import metrics_store
from metrics.setup_db import ensure_metrics_table

# Intentar importar Base de modelos
try:
    from models.base import Base
except ImportError:
    Base = None


# =============================================================================
# MIDDLEWARES
# =============================================================================

class DiagnosticLogoMiddleware(BaseHTTPMiddleware):
    """I-004 FIX: Sanitizes headers — strips cookies/authorization before logging."""
    SENSITIVE_HEADERS = {"cookie", "authorization", "x-forwarded-for", "set-cookie"}

    async def dispatch(self, request: Request, call_next):
        is_org_info = "/api/admin/organization" in request.url.path
        is_logo_upload = "/api/admin/upload-logo" in request.url.path or "/api/organizations" in request.url.path
        
        if is_org_info or is_logo_upload:
            # I-004 FIX: Only log safe headers (strip cookies, auth tokens)
            safe_headers = {k: v for k, v in request.headers.items() if k.lower() not in self.SENSITIVE_HEADERS}
            logger.info(f"DIAGNOSTIC: Request to {request.url.path}", extra={
                "method": request.method,
                "headers": safe_headers,
                "client": request.client.host if request.client else "unknown"
            })
        
        response = await call_next(request)
        return response

class FixJSMimeTypeMiddleware(BaseHTTPMiddleware):
    """Asegura que los archivos JS se sirvan con el tipo MIME correcto para evitar errores de carga en el UI"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.endswith('.js') or path.endswith('.mjs'):
            response.headers["content-type"] = "application/javascript; charset=utf-8"
        return response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Inyecta un request_id único en cada petición para correlación en logs y auditoría.
    El ID se propaga a través de request.state.request_id y un header de respuesta.
    """
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        
        # We also attempt to bind it to the db session if the session exists in request.state
        # (Though usually it's injected via Depends in routers)
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# =============================================================================
# APP CONFIGURATION
# =============================================================================

app = FastAPI(
    title="Dircom Payroll",
    version="4.2.3",
    docs_url=None if PRODUCTION else "/docs",
    openapi_url=None if PRODUCTION else "/openapi.json",
)

# Middlewares y Handlers de Rate Limit
app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)
# Restriction: Allow only the configured public URL in production, allow local/ngrok in dev
_base = getattr(config, "SYSTEM_PUBLIC_URL", None)
if PRODUCTION:
    origins = [_base] if _base else []
    allow_origin_regex = None
else:
    _base_dev = _base or "http://localhost:8000"
    _ngrok = config._detect_ngrok_url()
    origins = ["http://localhost:3000", "http://localhost:8000", _base_dev]
    if _ngrok:
        origins.append(_ngrok)
    allow_origin_regex = r"https?://(192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|127\.0\.0\.1|localhost).*|https?://.*\.ngrok-free\.(app|dev)"

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "ngrok-skip-browser-warning"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"REQ: {request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"RES: {response.status_code}")
    return response

class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection: checks for a custom header on state-changing requests,
    reinforced with Origin and Referer validation against allowed domains.
    Combined with SameSite=Strict cookies, this provides robust defense.
    Always enforced regardless of environment (dev/prod).
    """
    # Paths that skip CSRF (e.g., external webhook callbacks)
    CSRF_EXEMPT_PATHS = frozenset()

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.url.path.startswith("/api/"):
                if request.url.path not in self.CSRF_EXEMPT_PATHS:
                    xhr = request.headers.get("X-Requested-With")
                    if not xhr:
                        logger.warning("csrf.blocked: %s %s", request.method, request.url.path)
                        return JSONResponse(status_code=403, content={"detail": "csrf_protection_triggered"})
                    
                    # Double-submit Origin and Referer validation
                    origin = request.headers.get("Origin")
                    referer = request.headers.get("Referer")
                    allowed_base = getattr(config, "SYSTEM_PUBLIC_URL", "")
                    
                    if PRODUCTION:
                        if origin and allowed_base and not origin.startswith(allowed_base):
                            logger.warning("csrf.origin_blocked: got=%s expected=%s", origin, allowed_base)
                            return JSONResponse(status_code=403, content={"detail": "csrf_protection_triggered"})
                        if referer and allowed_base and not referer.startswith(allowed_base):
                            logger.warning("csrf.referer_blocked: got=%s expected=%s", referer, allowed_base)
                            return JSONResponse(status_code=403, content={"detail": "csrf_protection_triggered"})
                    else:
                        dev_allowed = ("localhost", "127.0.0.1", "192.168.", "10.", "172.", "ngrok-free.app", "ngrok-free.dev")
                        if allowed_base:
                            dev_allowed = dev_allowed + (allowed_base,)
                        if origin and not any(x in origin for x in dev_allowed):
                            logger.warning("csrf.origin_blocked_dev: got=%s", origin)
                            return JSONResponse(status_code=403, content={"detail": "csrf_protection_triggered"})
                        if referer and not any(x in referer for x in dev_allowed):
                            logger.warning("csrf.referer_blocked_dev: got=%s", referer)
                            return JSONResponse(status_code=403, content={"detail": "csrf_protection_triggered"})
        return await call_next(request)

app.add_middleware(CSRFProtectionMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(FixJSMimeTypeMiddleware)
app.add_middleware(DiagnosticLogoMiddleware)
app.add_middleware(MetricsMiddleware)

# =============================================================================
# ROUTERS (Importaci  n e Inclusi  n)
# =============================================================================

from api.verification import router as verification_router
from api.auth import router as auth_router
from api.receipts import router as receipts_router
from api.employees import router as employees_router
from api.admin import router as admin_router
from api.batches import router as batches_router
from modules.digital_signature import router as digital_signature_router
from api.signatures import router as signatures_router
from api.company_signers import router as company_signers_router
from api.tracking import router as tracking_router
from api.organizations import router as organizations_router
from api.pki import router as pki_router
from api.audit import router as audit_router
from api.legajo import router as legajo_router
from api.notifications import router as notifications_router
from api.documents import router as documents_router
from api.password_reset import router as password_reset_router

# Importante: Las rutas de API siempre deben ir ANTES que el montaje de archivos est !ticos
app.include_router(verification_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(organizations_router)
app.include_router(digital_signature_router)
app.include_router(receipts_router)
app.include_router(employees_router)
app.include_router(batches_router)
app.include_router(signatures_router)
app.include_router(company_signers_router)
app.include_router(tracking_router)
app.include_router(pki_router)
app.include_router(audit_router)
app.include_router(legajo_router)
app.include_router(notifications_router)
app.include_router(documents_router)
app.include_router(password_reset_router)


# --- Public Legacy Redirects ---
@app.get("/sign/{token}")
async def legacy_sign_redirect(token: str):
    return RedirectResponse(url=f"{config.BASE_PUBLIC_URL}/api/signature-requests/{token}")

# --- Public QR Verification Endpoint (FES Validation) ---
@app.get("/v/{seal_id}")
async def verify_seal_page(seal_id: str, db: Session = Depends(get_db)):
    from fastapi import HTTPException
    row = db.execute(text("""
        SELECT s.*, o.name as organization_name, o.logo_path
        FROM receipt_seals s
        JOIN organizations o ON o.id = s.organization_id
        WHERE s.seal_id = :sid
    """), {"sid": seal_id}).fetchone()

    if not row:
        return HTMLResponse(
            content="""
            <html>
                <head><title>Firma no encontrada</title></head>
                <body style="font-family: sans-serif; text-align: center; margin-top: 50px;">
                    <h2 style="color: #d9534f;">No se encontr&oacute; la firma</h2>
                    <p>El c&oacute;digo QR o enlace proporcionado no es v&aacute;lido o ha expirado.</p>
                </body>
            </html>
            """,
            status_code=404
        )

    html_content = f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Verificaci&oacute;n de Firma Electr&oacute;nica</title>
        <style>
            body {{ font-family: 'Inter', sans-serif; background-color: #f4f7f6; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
            .card {{ background: white; padding: 2rem; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); max-width: 400px; width: 100%; }}
            .header {{ text-align: center; border-bottom: 2px solid #e2e8f0; padding-bottom: 1rem; margin-bottom: 1rem; }}
            .header h1 {{ margin: 0; font-size: 1.5rem; color: #1e293b; }}
            .status {{ text-align: center; padding: 0.5rem; background-color: #def7ec; color: #03543f; border-radius: 6px; font-weight: bold; margin-bottom: 1.5rem; border: 1px solid #84e1bc; }}
            .field {{ margin-bottom: 0.8rem; }}
            .label {{ font-size: 0.85rem; color: #64748b; font-weight: 600; text-transform: uppercase; }}
            .value {{ font-size: 1rem; color: #0f172a; font-weight: 500; word-break: break-all; }}
            .footer {{ text-align: center; font-size: 0.75rem; color: #94a3b8; margin-top: 2rem; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h1>Firma Electr&oacute;nica Verificada</h1>
            </div>
            <div class="status">
                &#10004; Firma V&aacute;lida e Inalterada
            </div>
            <div class="field">
                <div class="label">Organizaci&oacute;n</div>
                <div class="value">{row.organization_name}</div>
            </div>
            <div class="field">
                <div class="label">Firmante</div>
                <div class="value">{row.signer_name} (DNI/CUIT: {row.signer_dni})</div>
            </div>
            <div class="field">
                <div class="label">Rol</div>
                <div class="value">{'Empleador' if row.signer_role == 'employer' else 'Empleado'}</div>
            </div>
            <div class="field">
                <div class="label">Fecha y Hora de Firma</div>
                <div class="value">{row.created_at.strftime('%d/%m/%Y %H:%M:%S')}</div>
            </div>
            <div class="field">
                <div class="label">ID de Sello</div>
                <div class="value">{row.seal_id}</div>
            </div>
            <div class="footer">
                Generado y validado criptogr&aacute;ficamente por Dircom Payroll Signature Engine.
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# --- Observability Endpoints (Phase 4 Hardening) ---

@app.get("/health")
async def health_check():
    """Simple liveness probe."""
    return {"status": "alive", "version": app.version}

@app.get("/metrics")
async def metrics_export(request: Request):
    """Operational metrics snapshot for local or private consumers."""
    client_host = request.client.host if request.client else ""
    if PRODUCTION and client_host not in {"127.0.0.1", "::1"}:
        return JSONResponse(status_code=403, content={"detail": "forbidden"})
    return {"status": "ok", "metrics": metrics_registry.export_worker_snapshot()}

@app.get("/api/admin/metrics")
async def admin_metrics(request: Request):
    """Consolidated metrics report for admin consumers."""
    client_host = request.client.host if request.client else ""
    if PRODUCTION and client_host not in {"127.0.0.1", "::1"}:
        return JSONResponse(status_code=403, content={"detail": "forbidden"})
    return MetricsExporter.get_full_consolidated_report()

# Simple in-memory cache for deep health check to prevent DDoS
_health_cache = {"data": None, "timestamp": 0}

@app.get("/health/deep")
async def deep_health_check(db: Session = Depends(get_db)):
    """Deep Readiness Probe + Metrics"""
    import time
    global _health_cache
    now = time.time()
    if _health_cache["data"] and (now - _health_cache["timestamp"] < 60):
        return _health_cache["data"]

    import shutil
    import psutil
    
    health = {"status": "ok", "metrics": {}}
    
    # 1. DB Check
    try:
        db.execute(text("SELECT 1"))
        health["metrics"]["database"] = "connected"
    except Exception as e:
        health["status"] = "degraded"
        health["metrics"]["database"] = f"error: {str(e)}"
        
    # 2. Disk Check
    try:
        total, used, free = shutil.disk_usage(STORAGE_ROOT)
        health["metrics"]["storage"] = {
            "total_gb": round(total / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "usage_percent": round((used / total) * 100, 2)
        }
        if (free / total) < 0.05: # Less than 5% free
             health["status"] = "warning"
             health["metrics"]["storage"]["status"] = "low_space"
    except Exception:
        health["metrics"]["storage"] = "unknown"

    # 3. Signature Pipeline Metrics
    try:
        # Check both tables
        zombies_ent = db.execute(text("""
            SELECT count(*) FROM receipts WHERE processing_signature = true AND is_deleted = false AND updated_at < :limit
        """), {"limit": utc_now() - timedelta(minutes=15)}).scalar()
        
        zombies_leg = db.execute(text("""
            SELECT count(*) FROM payroll_receipts WHERE processing_signature = true AND is_deleted = false AND updated_at < :limit
        """), {"limit": utc_now() - timedelta(minutes=15)}).scalar()
        
        active_ent = db.execute(text("""
            SELECT count(*) FROM receipts WHERE processing_signature = true AND is_deleted = false AND updated_at >= :limit
        """), {"limit": utc_now() - timedelta(minutes=15)}).scalar()

        active_leg = db.execute(text("""
            SELECT count(*) FROM payroll_receipts WHERE processing_signature = true AND is_deleted = false AND updated_at >= :limit
        """), {"limit": utc_now() - timedelta(minutes=15)}).scalar()
        
        health["metrics"]["signature_pipeline"] = {
            "zombie_count": (zombies_ent or 0) + (zombies_leg or 0),
            "active_processing": (active_ent or 0) + (active_leg or 0)
        }
    except Exception:
        health["metrics"]["signature_pipeline"] = "error"

    # 4. Redis health
    try:
        from services.redis_service import redis_service
        if redis_service and redis_service.ping():
            health["metrics"]["redis"] = "connected"
        else:
            health["metrics"]["redis"] = "unavailable"
            health["status"] = "degraded"
    except Exception as e:
        health["metrics"]["redis"] = f"error: {e}"
        health["status"] = "degraded"

    # 4b. Background import job queue health
    try:
        queued_jobs = db.execute(text("SELECT count(*) FROM import_jobs WHERE status = 'queued' OR status = 'processing' OR status = 'importing' ")).scalar()
        health["metrics"]["import_job_queue"] = {
            "queued_or_processing": queued_jobs,
            "status": "ok" if queued_jobs == 0 else "active"
        }
    except Exception as e:
        health["metrics"]["import_job_queue"] = f"error: {e}"
        health["status"] = "degraded"

    # 5. System Load
    health["metrics"]["system"] = {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent
    }
    
    # 6. Gap 12.4: PDF Engine Health (PyMuPDF)
    try:
        import fitz
        health["metrics"]["pdf_engine"] = {
            "library": "PyMuPDF",
            "version": fitz.version[0],
            "status": "operational"
        }
    except Exception as e:
        health["status"] = "degraded"
        health["metrics"]["pdf_engine"] = {"status": f"error: {e}"}
    
    # 6. Gap 12.4: PKI Certificate Health
    try:
        import config as _cfg
        from pathlib import Path as _P
        cert_status = {}
        for label, path_str in [("signer_cert", _cfg.X509_CERT_PATH), ("root_ca", _cfg.ROOT_CA_PATH), ("p12_bundle", _cfg.X509_P12_PATH)]:
            cert_status[label] = "present" if _P(path_str).exists() else "MISSING"
        health["metrics"]["pki"] = cert_status
        if "MISSING" in cert_status.values():
            health["status"] = "degraded"
    except Exception:
        health["metrics"]["pki"] = "check_failed"
    
    # 7. Gap 12.1: Worker Pool Telemetry
    try:
        from modules.digital_signature import _pdf_executor
        health["metrics"]["worker_pool"] = {
            "max_workers": _pdf_executor._max_workers,
            "threads_active": len([t for t in _pdf_executor._threads if t.is_alive()]) if hasattr(_pdf_executor, '_threads') else "N/A"
        }
    except Exception:
        health["metrics"]["worker_pool"] = "unavailable"
    
    _health_cache["data"] = health
    _health_cache["timestamp"] = time.time()
    return health



# Route to intercept /ui without slash to prevent Starlette's host-rewriting redirect
@app.get("/ui")
async def ui_redirect_no_slash():
    return RedirectResponse(url=f"{config.BASE_PUBLIC_URL}/ui/")

# Montaje de la interfaz de usuario (Frontend)
# Asegúrese de que UI_DIR sea la carpeta donde está tu index.html
if Path(UI_DIR).exists():
    app.mount("/ui", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
else:
    logger.warning(f"Advertencia: Directorio UI no encontrado en {UI_DIR}")

# (Startup logic moved to consolidated handler below)


# =============================================================================
# ERROR HANDLERS (Globales)
# =============================================================================

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"validation_error: {request.method} {request.url.path} - {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": exc.errors()}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    path = request.url.path
    accept_header = request.headers.get("accept", "").lower()
    accepts_html = "text/html" in accept_header
    accepts_pdf = "application/pdf" in accept_header
    is_navigation = request.headers.get("sec-fetch-mode") == "navigate"
    is_receipt_download = path.startswith("/api/receipts/") and path.endswith("/download")

    if is_receipt_download and exc.status_code in (401, 403) and (accepts_html or accepts_pdf or is_navigation):
        if exc.status_code == 401:
            title = "Iniciá sesión para ver este recibo"
            message = "Este documento está protegido. Ingresá con la cuenta de la empresa o del empleado al que pertenece."
            action = "Iniciar sesión"
        else:
            title = "Esta cuenta no tiene acceso"
            message = "El recibo no corresponde a la empresa ni al empleado con el que iniciaste sesión."
            action = "Cambiar de cuenta"

        content = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} | MyManageRH</title>
  <link rel="stylesheet" href="/ui/styles.css?v=68">
  <link rel="stylesheet" href="/ui/auth.css?v=1">
</head>
<body>
  <main class="auth-shell">
    <section class="card auth-card auth-card-main" role="alert">
      <div class="auth-header">
        <div class="auth-icon" aria-hidden="true">!</div>
        <h1 class="auth-title">{title}</h1>
        <p class="auth-subtitle">{message}</p>
      </div>
      <a class="btn btn-primary btn-lg w-full" href="/ui/#/select-role">{action}</a>
      <p class="auth-backlink"><a class="link" href="/ui/">Volver al inicio</a></p>
    </section>
  </main>
</body>
</html>"""
        return HTMLResponse(
            content=content,
            status_code=exc.status_code,
            headers={**(exc.headers or {}), "Cache-Control": "no-store"},
        )

    return await default_http_exception_handler(request, exc)

@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError):
    # Ya manejamos casos espec  ficos en auth.py, esto es un fallback
    return JSONResponse(status_code=409, content={"detail": "data_conflict", "msg": "Conflicto de integridad en la base de datos"})

@app.exception_handler(OperationalError)
async def db_down_handler(request: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={"detail": "database_unavailable"})

@app.exception_handler(SQLAlchemyError)
async def db_generic_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("database_error", extra={"path": request.url.path})
    return JSONResponse(status_code=503, content={"detail": "database_error"})

@app.exception_handler(EmailSendFailedError)
async def email_send_failed_handler(request: Request, exc: EmailSendFailedError):
    logger.error("email_send_failed_endpoint", extra={"path": request.url.path, "code": exc.code})
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Error en el servicio de notificaciones"}
    )

@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.exception("unhandled_error", extra={"path": request.url.path})
    return JSONResponse(status_code=500, content={"detail": "internal_error"})


# =============================================================================
# BASE ENDPOINTS
# =============================================================================

@app.get("/health")
async def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "timestamp": utc_now().isoformat(), "db": "connected"}
    except Exception:
        return JSONResponse(status_code=500, content={"status": "error", "detail": "database_error"})


@app.get("/")
async def root():
    """Redirige autom !ticamente a la interfaz de usuario"""
    return RedirectResponse(url=f"{config.BASE_PUBLIC_URL}/ui/")


# =============================================================================
# STARTUP & DEBUG
# =============================================================================

# M-004: Using @app.on_event for backward compat — lifespan migration deferred
# until all startup dependencies support async context managers.
@app.on_event("startup")
async def startup():
    # 0. Secure Temp Cleanup (Hardening)
    ensure_metrics_table()
    try:
        task = asyncio.create_task(start_periodic_metrics_flusher())
        logger.info(f"metrics.flusher_started: task={task}")
        try:
            metrics_store.flush_snapshot()
            logger.info("metrics.startup_snapshot_flushed")
        except Exception as e:
            logger.error(f"metrics.startup_snapshot_flush_failed: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"metrics.flusher_start_failed: {e}", exc_info=True)
    removed = secure_temp.cleanup_orphaned_temps()
    if removed > 0:
        logger.info(f"startup.secure_temp_cleanup removed={removed}")

    # 1. Automated Ngrok (pyngrok)
    display_url = config.BASE_PUBLIC_URL
    if not PRODUCTION and os.getenv("NGROK_AUTHTOKEN"):
        try:
            from pyngrok import ngrok, process
            # Use the token from .env
            ngrok.set_auth_token(os.getenv("NGROK_AUTHTOKEN"))
            
            # GAP-010: Cleanup previous sessions to avoid ERR_NGROK_334
            try:
                tunnels = ngrok.get_tunnels()
                for t in tunnels:
                    ngrok.disconnect(t.public_url)
            except:
                pass
                
            # Auto-detect or create tunnel on port 8000
            try:
                display_url = ngrok.connect(8000, host_header="localhost:8000").public_url
            except Exception as connect_error:
                # If it fails because it's already online, try to fetch it or use fallback
                if "already online" in str(connect_error):
                    tunnels = ngrok.get_tunnels()
                    if tunnels:
                        display_url = tunnels[0].public_url
                    else:
                        raise connect_error
                else:
                    raise connect_error
                
            logger.info(f"NGROK AUTOMATION ACTIVE: {display_url}")
        except Exception as e:
            logger.error(f"pyngrok failed to start: {e}")
            # Fallback to manual detection
            ngrok_url = config._detect_ngrok_url() if not PRODUCTION else None
            display_url = ngrok_url or config.BASE_PUBLIC_URL
    else:
        # Standard manual detection if no token or in production
        ngrok_url = config._detect_ngrok_url() if not PRODUCTION else None
        display_url = ngrok_url or config.BASE_PUBLIC_URL
    if display_url:
        config.BASE_PUBLIC_URL = display_url.rstrip("/")

    # 2. Server Operative Banner
    logger.info("=" * 80)
    logger.info(f"DIRCOM PAYROLL v{app.version} - SERVER OPERATIVE")
    logger.info(f"PUBLIC API URL: {display_url}")
    logger.info(f"UI ACCESS:     {display_url}/ui")
    logger.info("=" * 80)

    # 3. Debug routes (Optional but helpful for user)
    print("\n--- Rutas Cargadas ---")
    for route in app.routes:
        print(f"Path: {route.path} | Name: {route.name} | Methods: {getattr(route, 'methods', 'N/A')}")
    print("----------------------\n")

    # 3. Startup Checks (Resources, Tesseract, etc.)
    try:
        from modules.startup import run_startup_checks
        run_startup_checks(Base)
    except Exception as e:
        logger.critical(f"startup.checks_failed: {e}")
        import sys
        sys.exit(1)

    # 5. Background Tasks (Multi-Worker Safe via PostgreSQL Advisory Locks)
    #
    # With Gunicorn multi-worker, every worker executes this startup handler.
    # To avoid duplicate maintenance work, each background task uses
    # pg_try_advisory_lock(lock_id) — only one worker holds the lock at a time.
    # If the holding worker dies, PostgreSQL automatically releases the lock
    # and another worker picks it up on its next cycle.
    #
    # Lock IDs (arbitrary stable int8 constants):
    LOCK_MAINTENANCE = 900_001
    LOCK_WEBHOOK     = 900_002
    LOCK_STORAGE     = 900_003
    LOCK_IMPORT_JOB  = 900_004

    def _try_advisory_lock(db_session, lock_id: int) -> bool:
        """Attempt to acquire a PostgreSQL session-level advisory lock (non-blocking)."""
        try:
            result = db_session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": lock_id}
            ).scalar()
            return bool(result)
        except Exception as e:
            logger.debug(f"advisory_lock.attempt_failed lock={lock_id}: {e}")
            return False

    def _release_advisory_lock(db_session, lock_id: int):
        """Release a PostgreSQL session-level advisory lock."""
        try:
            db_session.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": lock_id}
            )
        except Exception:
            pass

    # --- 5a. Maintenance Supervisor (Zombies & OTP Ghost Users) ---
    async def _maintenance_supervisor():
        logger.info("maintenance.supervisor_started")
        while True:
            _db = None
            try:
                _db = SessionLocal()
                if not _try_advisory_lock(_db, LOCK_MAINTENANCE):
                    logger.debug("maintenance.skipped_no_lock")
                    await asyncio.sleep(900)
                    continue

                try:
                    # 1. Zombie Locks Cleanup (GAP-006)
                    zombie_threshold = utc_now() - timedelta(minutes=15)
                    cleared_ent = _db.execute(text("""
                        UPDATE receipts SET processing_signature = false 
                        WHERE processing_signature = true AND is_deleted = false AND updated_at < :limit
                    """), {"limit": zombie_threshold}).rowcount
                    cleared_leg = _db.execute(text("""
                        UPDATE payroll_receipts SET processing_signature = false 
                        WHERE processing_signature = true AND is_deleted = false AND updated_at < :limit
                    """), {"limit": zombie_threshold}).rowcount
                    
                    # 2. Ghost OTP Users Cleanup (GAP-010)
                    ghost_threshold = utc_now() - timedelta(days=30)
                    purged_ghosts = _db.execute(text("""
                        UPDATE users 
                        SET is_active = false, is_deleted = true, deleted_at = NOW()
                        WHERE user_status = 'otp_session' AND role = 'employee' AND created_at < :limit AND is_deleted = false
                    """), {"limit": ghost_threshold}).rowcount
                    
                    # 3. Session Garbage Collection (Audit/Fase 5)
                    purged_sessions = _db.execute(text("""
                        DELETE FROM user_sessions 
                        WHERE id IN (
                            SELECT id FROM user_sessions 
                            WHERE expires_at < NOW() 
                            LIMIT 1000
                        )
                    """)).rowcount

                    # 4. ZIP Temp Cleanup (Audit/Fase 5 - Defense in Depth)
                    import tempfile
                    import time
                    temp_dir = tempfile.gettempdir()
                    now_ts = time.time()
                    purged_zips = 0
                    for f in os.listdir(temp_dir):
                        if f.startswith("payroll_export_") and f.endswith(".zip"):
                            fpath = os.path.join(temp_dir, f)
                            if os.path.getmtime(fpath) < (now_ts - 7200):
                                try:
                                    os.remove(fpath)
                                    purged_zips += 1
                                except Exception:
                                    pass
                    
                    _db.commit()
                    
                    if cleared_ent or cleared_leg:
                        logger.warning("maintenance.zombie_locks_cleared", extra={
                            "cleared_enterprise": cleared_ent,
                            "cleared_legacy": cleared_leg,
                            "total_zombies_cleared": cleared_ent + cleared_leg
                        })
                    if purged_ghosts:
                        logger.info("maintenance.ghost_users_purged", extra={
                            "purged_count": purged_ghosts
                        })
                    if purged_sessions:
                        logger.info("maintenance.sessions_purged", extra={"count": purged_sessions})
                    if purged_zips:
                        logger.info("maintenance.temp_zips_purged", extra={"count": purged_zips})
                finally:
                    _release_advisory_lock(_db, LOCK_MAINTENANCE)
            except Exception as e:
                logger.error(f"maintenance.supervisor_failed: {e}")
            finally:
                if _db is not None:
                    _db.close()
            
            await asyncio.sleep(900)  # Sleep for 15 minutes

    app.state.maintenance_task = asyncio.create_task(_maintenance_supervisor())

    # --- 5b. Webhook Supervisor ---
    async def _webhook_supervisor():
        from services.webhook_service import start_outbox_drain_loop
        logger.info("webhook.supervisor_started")
        while True:
            _db = None
            try:
                _db = SessionLocal()
                if not _try_advisory_lock(_db, LOCK_WEBHOOK):
                    logger.debug("webhook.skipped_no_lock")
                    _db.close()
                    _db = None
                    await asyncio.sleep(60)
                    continue
                _release_advisory_lock(_db, LOCK_WEBHOOK)
                _db.close()
                _db = None

                # start_outbox_drain_loop manages its own DB sessions internally
                await start_outbox_drain_loop(SessionLocal)
                logger.info("webhook.supervisor_exiting_as_disabled")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"webhook.supervisor_worker_crashed: {e}. Restarting in 60s...")
                await asyncio.sleep(60)
            finally:
                if _db is not None:
                    _db.close()
    
    app.state.webhook_task = asyncio.create_task(_webhook_supervisor())

    # --- 5c. Import Job Queue Supervisor ---
    async def _import_job_supervisor():
        logger.info("import_job.supervisor_started")
        while True:
            _db = None
            try:
                _db = SessionLocal()
                if not _try_advisory_lock(_db, LOCK_IMPORT_JOB):
                    logger.debug("import_job.skipped_no_lock")
                    _db.close()
                    _db = None
                    await asyncio.sleep(60)
                    continue

                _release_advisory_lock(_db, LOCK_IMPORT_JOB)
                _db.close()
                _db = None

                await start_import_job_drain_loop(SessionLocal)
                logger.info("import_job.supervisor_exiting")
                break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"import_job.supervisor_worker_crashed: {e}. Restarting in 60s...")
                await asyncio.sleep(60)
            finally:
                if _db is not None:
                    _db.close()

    app.state.import_job_task = asyncio.create_task(_import_job_supervisor())

    # --- 5d. Storage Integrity Check ---
    async def _storage_integrity_loop():
        """Periodic check that DB references point to existing physical files."""
        logger.info("storage.integrity_check_started")
        while True:
            await asyncio.sleep(3600)  # Run every hour
            _db = None
            try:
                _db = SessionLocal()
                if not _try_advisory_lock(_db, LOCK_STORAGE):
                    logger.debug("storage.integrity_skipped_no_lock")
                    _db.close()
                    _db = None
                    continue

                try:
                    stale = _db.execute(text("""
                        SELECT id, file_path FROM receipts 
                        WHERE file_path IS NOT NULL AND status != 'deleted'
                        ORDER BY RANDOM() LIMIT 100
                    """)).fetchall()
                    stale_count = 0
                    for row in stale:
                        full = os.path.join(STORAGE_ROOT, row.file_path) if not os.path.isabs(row.file_path) else row.file_path
                        if not os.path.exists(full):
                            stale_count += 1
                            logger.warning(f"storage.integrity_missing: receipt={row.id} path={row.file_path}")
                    if stale_count:
                        logger.error(f"storage.integrity_report: {stale_count}/100 sampled files missing")
                    else:
                        logger.info("storage.integrity_ok: 100 sampled files verified")
                finally:
                    _release_advisory_lock(_db, LOCK_STORAGE)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"storage.integrity_check_error: {e}")
            finally:
                if _db is not None:
                    _db.close()
    
    app.state.storage_integrity_task = asyncio.create_task(_storage_integrity_loop())


@app.get("/health/ha")
async def high_availability_health(db: Session = Depends(get_db)):
    """Health endpoint focused on HA readiness and supervisor task state."""
    deep_health = await deep_health_check(db)

    supervisor_tasks = {
        "maintenance_supervisor": getattr(app.state, "maintenance_task", None),
        "webhook_supervisor": getattr(app.state, "webhook_task", None),
        "import_job_supervisor": getattr(app.state, "import_job_task", None),
        "storage_integrity_loop": getattr(app.state, "storage_integrity_task", None),
    }

    supervisors = {}
    overall_status = "ok"
    for name, task in supervisor_tasks.items():
        is_alive = bool(task and not task.done())
        supervisors[name] = "alive" if is_alive else "stopped"
        if not is_alive:
            overall_status = "degraded"

    return {
        "status": overall_status,
        "supervisors": supervisors,
        "deep_health": deep_health,
    }


# M-006 FIX: Single entry point is server.py. Removed duplicate __main__ block.
# Use `python server.py` to start the application.
