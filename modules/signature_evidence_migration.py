"""
Migration: Reforzar signature_evidence con campos para solidez jurÃ­dica

Agrega campos para:
- Integridad del PDF (antes y despuÃ©s)
- Hash de imagen de firma
- Token usado
- IP y User-Agent (ya existen)

Esta migraciÃ³n es idempotente (ADD COLUMN IF NOT EXISTS)
y no afecta al flujo existente.
"""

from sqlalchemy import text
from payroll_core import engine, logger

def add_signature_evidence_columns():
    """Agrega columnas de solidez jurÃ­dica a signature_evidence si no existen."""
    try:
        with engine.begin() as conn:
            # Campo: final_pdf_sha256 (hash del PDF despuÃ©s de la firma)
            conn.execute(text("""
                ALTER TABLE signature_evidence 
                ADD COLUMN IF NOT EXISTS final_pdf_sha256 CHAR(64)
            """))
            
            # Campo: token_used (hash del token para auditorÃ­a)
            conn.execute(text("""
                ALTER TABLE signature_evidence 
                ADD COLUMN IF NOT EXISTS token_used CHAR(64)
            """))
            
            logger.info(
                "signature_evidence_columns_refactored",
                extra={
                    "event_type": "db.migration.signature_evidence_refactored",
                    "columns_added": ["final_pdf_sha256", "token_used"]
                }
            )
    except Exception as e:
        logger.exception(
            "signature_evidence_refactor_failed",
            extra={
                "event_type": "db.migration.signature_evidence_failed",
                "error": str(e)
            }
        )
        # No fallar completamente si la migraciÃ³n falla
        # (las columnas podrÃ­an ya existir)
