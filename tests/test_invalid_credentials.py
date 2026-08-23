import asyncio
import os
import sys
import logging
from io import StringIO
from dotenv import load_dotenv
load_dotenv()

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
# Temporary patch config.SMTP_PASSWORD to test masking filter
DUMMY_BAD_PASSWORD = "SUPER_SECRET_BAD_PASSWORD_1234_ABCDE"
config.SMTP_PASSWORD = DUMMY_BAD_PASSWORD

from services.email_service import EmailService
from payroll_core import EmailSendFailedError, pii_filter

async def test_auth_failure_and_masking():
    print("=========================================")
    print("TEST INVALID CREDENTIALS & PASSWORD MASKING")
    print("=========================================")

    # Setup memory log capture
    log_capture = StringIO()
    sh = logging.StreamHandler(log_capture)
    sh.setLevel(logging.DEBUG)
    sh.addFilter(pii_filter) # Apply our PII/Password filter
    
    # Get root logger and add handler
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    # Clear handlers and add capture
    for h in original_handlers:
        root_logger.removeHandler(h)
    root_logger.addHandler(sh)
    
    email_svc = EmailService()
    # Ensure it uses the patched bad password and tries to connect
    email_svc.mode = "smtp"
    email_svc.smtp_password = DUMMY_BAD_PASSWORD
    
    raised_expected = False
    error_code = None
    raised_msg = ""
    
    try:
        print("[*] Sending email with bad credentials...")
        await email_svc.send_html(
            to="test-failure@example.com",
            subject="Test authentication failure",
            body_html="Should fail."
        )
    except EmailSendFailedError as e:
        raised_expected = True
        error_code = e.code
        raised_msg = str(e)
        print(f"[+] Caught expected EmailSendFailedError: {e} (Code: {e.code})")
    except Exception as e:
        print(f"[-] FAILED: Unexpected exception raised: {type(e).__name__}: {e}")
    
    # Restore original handlers
    root_logger.removeHandler(sh)
    for h in original_handlers:
        root_logger.addHandler(h)
        
    captured_logs = log_capture.getvalue()
    
    # Assertions
    assert raised_expected, "EmailSendFailedError was not raised!"
    assert error_code == "SMTP_AUTH_FAILED", f"Expected SMTP_AUTH_FAILED code, got: {error_code}"
    
    # Check that DUMMY_BAD_PASSWORD is NOT in any of the outputs
    assert DUMMY_BAD_PASSWORD not in raised_msg, "Password leaked in exception message!"
    assert DUMMY_BAD_PASSWORD not in captured_logs, "Password leaked in captured log outputs!"
    
    print("[+] SUCCESS! Raised SMTP_AUTH_FAILED and confirmed password was redacted.")
    print("Log verification passed: password was not found in traceback or messages.")
    print("=========================================")

if __name__ == "__main__":
    asyncio.run(test_auth_failure_and_masking())
