"""
Startup logic and database migrations/backfills.
Extracted from main.py to keep the entry point clean.
"""
import logging
from sqlalchemy import text, engine

from payroll_core import (
    engine,
    normalize_org_name,
    ALLOWED_STORAGE_DIR,
    ensure_storage_dirs,
    UI_DIR,
    logger
)

def run_startup_checks(Base=None):
    """
    Run all startup checks. Schema generation should be purely done with Alembic.
    """
    ensure_storage_dirs()

    # Automatically apply v5 receipt snapshot migration if not already applied
    try:
        with engine.connect() as conn:
            # Check if columns are already added
            res = conn.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_name = 'payroll_receipts' AND column_name = 'snapshot_employee_name'
            """)).scalar()
            if res == 0:
                logger.info("db.migration_v5_running")
                migration_file = '/root/Downloads/MyManageRH-Payroll-Backup/migrations/v5_receipt_snapshots.sql'
                with open(migration_file, 'r') as f:
                    sql_script = f.read()
                conn.execute(text(sql_script))
                logger.info("db.migration_v5_completed")
            else:
                logger.info("db.migration_v5_already_applied")
    except Exception as e:
        logger.error(f"db.migration_v5_failed: {e}")

    # Verify UI
    if not UI_DIR.is_dir():
        msg = f"UI directory not found: {UI_DIR}. Create a 'ui' folder with an 'index.html' file."
        logger.critical("app.ui_missing", extra={"event_type": "app.ui_missing", "path": str(UI_DIR)})
        raise RuntimeError(msg)

    # Verify fitz (PyMuPDF) dependency
    try:
        import fitz
        logger.info("dependency.fitz_verified")
    except ImportError:
        logger.critical("dependency.fitz_missing", extra={"event_type": "dependency.fitz_missing"})
        raise RuntimeError("PyMuPDF (fitz) is required for PDF processing. Please install it.")

    # Verify DB Connection & Sync Sequence
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            # Sync the audit_log sequence defensively on startup
            try:
                conn.execute(text("""
                    SELECT setval('audit_log_id_seq', COALESCE((SELECT MAX(id) FROM audit_log), 0) + 1, false)
                """))
                logger.info("db.audit_log_sequence_synced_on_startup")
            except Exception as seq_err:
                logger.warning(f"db.audit_log_sequence_sync_on_startup_failed: {seq_err}")
        logger.info("db.connected", extra={"event_type": "db.connected"})
    except Exception as e:
        logger.critical("db.connection_failed", extra={"event_type": "db.connection_failed", "error": str(e)})
        raise
    # 4. Chain of Trust Verification (Phase 6 Hardening)
    import config
    from pathlib import Path
    import requests
    
    logger.info("pki.chain_of_trust_check_started")
    
    # 4.1 Certs Verification
    critical_certs = [
        ("X509_CERT_PATH", config.X509_CERT_PATH),
        ("ROOT_CA_PATH", config.ROOT_CA_PATH),
        ("X509_P12_PATH", config.X509_P12_PATH)
    ]
    
    for label, path_str in critical_certs:
        p = Path(path_str)
        if not p.exists():
            if config.PRODUCTION:
                logger.critical(f"pki.cert_missing: {label}={path_str}")
                # We don't crash dev, but we DO crash production
                raise RuntimeError(f"CRITICAL: Required cryptographic asset missing: {label} at {path_str}")
            else:
                logger.warning(f"pki.cert_missing: {label}={path_str} (Non-fatal in DEV)")

    # 4.2 TSA Connectivity Check (Optional but recommended)
    if config.TSA_URL:
        try:
            # We just check for a 200/4xx response to see if it's reachable (TSA endpoints often return 405 on GET)
            response = requests.get(config.TSA_URL, timeout=5)
            logger.info(f"pki.tsa_reachable: {config.TSA_URL}")
        except Exception as e:
            logger.warning(f"pki.tsa_unreachable: {config.TSA_URL} - {e}")
            if config.PRODUCTION:
                 # In production, we might want to warn loudly as LTV signatures will lack external timestamps
                 logger.error("pki.tsa_offline_warning: Signatures will lack external TSA backing.")

    logger.info("pki.chain_of_trust_verified")
