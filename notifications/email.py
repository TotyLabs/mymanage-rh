from typing import Optional
from services.email_service import EmailService
import config

class NotificationEmailService:
    def __init__(self):
        self.email_svc = EmailService()

    async def send_receipt_pending_signature(
        self,
        employee_email: str,
        employee_name: str,
        organization_name: str,
        signature_link: str,
        tracking_token: str,
        company_email: Optional[str] = None,
        period: Optional[str] = None
    ):
        """
        Wrapper to send the pending signature email to an employee.
        """
        await self.email_svc.send_signature_email(
            employee_email=employee_email,
            employee_name=employee_name,
            signature_link=signature_link,
            organization_name=organization_name,
            tracking_token=tracking_token,
            company_email=company_email,
            period=period
        )
