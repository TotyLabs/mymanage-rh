"""
SmsService: envío de SMS con modo sandbox.

- SMS_MODE = "console" -> logea el SMS, no envía nada.
- SMS_MODE = "twilio"  -> usa Twilio SMS API (sin dependencia pip, usa urllib).
"""

import json
import base64
import urllib.request
import urllib.parse
from typing import Optional

from payroll_core import logger
import config


class SmsSendFailedError(Exception):
    """Lanzada cuando falla el envío de un SMS."""
    pass


class SmsService:
    def __init__(self):
        self.mode = getattr(config, "SMS_MODE", "console")
        self.account_sid = getattr(config, "TWILIO_ACCOUNT_SID", "")
        self.auth_token = getattr(config, "TWILIO_AUTH_TOKEN", "")
        self.from_number = getattr(config, "TWILIO_PHONE_NUMBER", "")

    def _log_sms(self, to: str, body: str):
        logger.info(
            f"sms.console | TO: {to} | BODY: {body}"
        )

    def send_otp(self, to: str, code: str, org_name: str = "MyManageRH"):
        """
        Envía un código OTP por SMS.
        Dev: imprime en consola. Prod: envía vía Twilio.
        """
        body = f"[{org_name}] Tu código de verificación es: {code}. Válido por 10 minutos."

        if self.mode == "console":
            self._log_sms(to, body)
            return

        if self.mode == "twilio":
            self._send_twilio(to, body)
            return

        # Fallback: console
        self._log_sms(to, body)

    def _send_twilio(self, to: str, body: str):
        """
        Envía SMS via Twilio REST API usando urllib (sin dependencia pip).
        POST https://api.twilio.com/2010-04-01/Accounts/{SID}/Messages.json
        """
        if not self.account_sid or not self.auth_token or not self.from_number:
            logger.error("sms.twilio_not_configured")
            raise SmsSendFailedError("Twilio credentials not configured")

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

        data = urllib.parse.urlencode({
            "To": to,
            "From": self.from_number,
            "Body": body,
        }).encode("utf-8")

        # Basic Auth: base64(account_sid:auth_token)
        credentials = base64.b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode()

        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Basic {credentials}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                sid = result.get("sid", "unknown")
                logger.info(f"sms.twilio_sent: sid={sid} to={to[:4]}***")
        except Exception as e:
            logger.error(f"sms.twilio_failed: {e}")
            raise SmsSendFailedError(str(e))
