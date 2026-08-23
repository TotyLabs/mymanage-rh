import asyncio
import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from services.email_service import EmailService
from payroll_core import EmailSendFailedError

async def run_test():
    recipient = os.getenv("SMTP_TEST_RECIPIENT", "scandrolifacundo2012@gmail.com")
    print("=========================================")
    print("SMTP INTEGRATION TEST")
    print(f"Host:     {config.SMTP_HOST}")
    print(f"Port:     {config.SMTP_PORT}")
    print(f"Security: {config.SMTP_SECURITY}")
    print(f"User:     {config.SMTP_USER}")
    print(f"To:       {recipient}")
    print("=========================================")

    email_svc = EmailService()
    # Force EMAIL_MODE to smtp for this test to ensure it tries real send
    email_svc.mode = "smtp"

    try:
        print("[*] Attempting to send test email asynchronously...")
        await email_svc.send_html(
            to=recipient,
            subject="Test YouCompare SES SMTP integration",
            body_html="<h3>SES Integration Working!</h3><p>This is a test notification from the new YouCompare Payroll backend integration via <b>aiosmtplib</b> with TLS.</p>"
        )
        print("[+] SUCCESS! Email sent successfully via Amazon SES SMTP.")
    except EmailSendFailedError as e:
        print(f"[-] FAILED! EmailSendFailedError raised.")
        print(f"    Code: {e.code}")
        print(f"    Details: {e}")
    except Exception as e:
        print(f"[-] FAILED! Unexpected exception: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
