from sqlalchemy.orm import Session
from .email import NotificationEmailService
from typing import Optional, Dict, Any
import logging
import config
from sqlalchemy import text
from datetime import datetime, timezone

logger = logging.getLogger("dircom.notifications")

class NotificationService:
    def __init__(self):
        self.email_service = NotificationEmailService()

    async def send_signature_pending_notification(
        self,
        receipt_id: str,
        organization_id: str,
        employee_id: str,
        employee_token: str
    ):
        """
        Background task to orchestrate sending a signature pending notification.
        This follows the pattern expected by FastAPI BackgroundTasks.
        """
        from payroll_core import SessionLocal
        db = SessionLocal()
        try:
            # 1. Fetch needed data using centralized repository
            from services.document_repository import DocumentRepository
            doc = DocumentRepository.get_document(db, receipt_id)
            
            if not doc:
                logger.error(f"notification.error: document_not_found id={receipt_id}")
                return

            employee_email = doc.get("email")
            if not employee_email:
                logger.warning(f"notification.skip: no_email_for_employee doc_id={receipt_id}")
                return

            # 2. Build secure link
            _base = config._detect_ngrok_url() or config.BASE_PUBLIC_URL
            sign_url = f"{_base}/ui/#/sign/{employee_token}"
            
            # 3. Extract metadata
            employee_name = doc.get("full_name") or "Empleado"
            org_name = doc.get("organization_name") or "Empresa"
            org_email = doc.get("organization_email") # DocumentRepository fetches this
            period = doc.get("metadata", {}).get("periodo") or ""

            # 4. Record event (audit)
            try:
                db.execute(text("""
                    INSERT INTO email_events (receipt_id, employee_id, email, status, sent_at)
                    VALUES (:rid, :eid, :email, 'sent', :now)
                """), {
                    "rid": receipt_id,
                    "eid": employee_id,
                    "email": employee_email,
                    "now": datetime.now(timezone.utc)
                })
                db.commit()
            except Exception as audit_err:
                logger.warning(f"notification.audit_failed: {audit_err}")

            # 5. Send Email
            await self.email_service.send_receipt_pending_signature(
                employee_email=employee_email,
                employee_name=employee_name,
                organization_name=org_name,
                signature_link=sign_url,
                tracking_token=None, # Tracking handled by EmailService internal pixel if needed
                company_email=org_email,
                period=period
            )
            
            logger.info(f"notification.sent: signature_pending doc_id={receipt_id} to={employee_email}")

        except Exception as e:
            logger.exception(f"notification.failed: {str(e)} doc_id={receipt_id}")
        finally:
            db.close()

    @staticmethod
    def get_instance():
        """Singleton-like access for background tasks."""
        if not hasattr(NotificationService, "_instance"):
            NotificationService._instance = NotificationService()
        return NotificationService._instance
