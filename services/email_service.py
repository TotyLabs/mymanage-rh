"""
EmailService: envío de correos con modo sandbox, SMTP principal asíncrono
y fallback opcional a Gmail.

EMAIL_MODE = "console" -> logea el correo, no envía nada.
EMAIL_MODE = "smtp"    -> usa SMTP real.

SES recomendado por soporte:
SMTP_PORT=465
SMTP_SECURITY=ssl

Gmail fallback:
GMAIL_FALLBACK_PORT=587
GMAIL_FALLBACK_SECURITY=starttls
"""

from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, Optional, List, Union

import aiosmtplib

from payroll_core import logger, EmailSendFailedError
from metrics.registry import metrics_registry
import config


class EmailService:
    def __init__(self):
        self.mode = getattr(config, "EMAIL_MODE", "console").lower()

        self.smtp_host = getattr(config, "SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
        self.smtp_port = int(getattr(config, "SMTP_PORT", 465))
        self.smtp_user = getattr(config, "SMTP_USER", None)
        self.smtp_password = getattr(config, "SMTP_PASSWORD", None)
        self.smtp_security = getattr(config, "SMTP_SECURITY", "ssl").lower()

        self.fallback_enabled = bool(getattr(config, "EMAIL_FALLBACK_ENABLED", True))
        self.fallback_host = getattr(config, "GMAIL_FALLBACK_HOST", "smtp.gmail.com")
        self.fallback_port = int(getattr(config, "GMAIL_FALLBACK_PORT", 587))
        self.fallback_user = getattr(config, "GMAIL_FALLBACK_USER", None)
        self.fallback_password = getattr(config, "GMAIL_FALLBACK_PASSWORD", None)
        self.fallback_security = getattr(config, "GMAIL_FALLBACK_SECURITY", "starttls").lower()

        self.from_address = getattr(config, "EMAIL_FROM", None) or self.fallback_user or "no-reply@mymanagerh.com"

        if self.mode == "smtp" and not self._has_primary_config():
            logger.error("email.smtp_not_configured")

        if self.mode == "smtp" and self.from_address is None:
            logger.error("email.from_address_not_configured")

        if self.mode == "smtp" and self.fallback_enabled and not self._has_fallback_config():
            logger.warning("email.gmail_fallback_not_configured")

    def _has_primary_config(self) -> bool:
        return bool(self.smtp_host and self.smtp_port and self.smtp_user and self.smtp_password)

    def _has_fallback_config(self) -> bool:
        return bool(
            self.fallback_host
            and self.fallback_port
            and self.fallback_user
            and self.fallback_password
        )

    def _build_message(
        self,
        to: str,
        subject: str,
        body_html: str,
        reply_to: Optional[str] = None,
        from_address: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Union[MIMEText, MIMEMultipart]:
        body_html = body_html.encode("utf-8", errors="replace").decode("utf-8")

        if attachments:
            msg = MIMEMultipart()
            msg.attach(MIMEText(body_html, "html", "utf-8"))
            for attachment in attachments:
                part = MIMEApplication(
                    attachment["content"],
                    _subtype=attachment.get("subtype", "octet-stream"),
                )
                part.add_header("Content-Disposition", "attachment", filename=attachment["filename"])
                msg.attach(part)
        else:
            msg = MIMEText(body_html, "html", "utf-8")
        msg["Subject"] = Header(subject, "utf-8").encode()
        msg["From"] = from_address or self.from_address
        msg["To"] = to

        if reply_to:
            msg["Reply-To"] = reply_to

        return msg

    def _log_email(self, to: str, subject: str, body_html: str):
        logger.info(
            "email.console",
            extra={
                "event_type": "email.console",
                "to": to,
                "subject": subject,
                "body_preview": body_html[:200],
            },
        )

    async def send_html(
        self,
        to: str,
        subject: str,
        body_html: str,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ):
        if self.mode == "console":
            self._log_email(to, subject, body_html)
            return

        if self.mode != "smtp":
            self._log_email(to, subject, body_html)
            return

        await self._send_smtp_async(to, subject, body_html, reply_to, attachments)

    def send_html_sync(
        self,
        to: str,
        subject: str,
        body_html: str,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ):
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                raise RuntimeError(
                    "send_html_sync() fue llamado dentro de un event loop activo. "
                    "Usá await send_html()."
                )
        except RuntimeError as e:
            if "event loop activo" in str(e):
                raise

        asyncio.run(self.send_html(to, subject, body_html, reply_to, attachments))

    async def _send_smtp_async(
        self,
        to: str,
        subject: str,
        body_html: str,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ):
        if not self._has_primary_config():
            logger.error(
                "email.primary_smtp_not_configured",
                extra={"to": to, "subject": subject},
            )
            raise EmailSendFailedError("SMTP principal no configurado", "SMTP_NOT_CONFIGURED")

        try:
            await self._attempt_send(
                host=self.smtp_host,
                port=self.smtp_port,
                user=self.smtp_user,
                password=self.smtp_password,
                security=self.smtp_security,
                to=to,
                subject=subject,
                body_html=body_html,
                reply_to=reply_to,
                from_address=self.from_address,
                attachments=attachments,
            )
            logger.info("email.sent.primary", extra={"to": to, "subject": subject})
            metrics_registry.record_email(sent=True)
            return

        except Exception as primary_error:
            logger.exception(
                f"email.primary_smtp_failed: {primary_error}",
                extra={"to": to, "subject": subject},
            )   

            if not self.fallback_enabled:
                raise EmailSendFailedError(str(primary_error), "SMTP_PRIMARY_FAILED")

            if not self._has_fallback_config():
                raise EmailSendFailedError(
                    "SMTP principal falló y fallback Gmail no está configurado",
                    "SMTP_FALLBACK_NOT_CONFIGURED",
                )

            try:
                await self._attempt_send(
                    host=self.fallback_host,
                    port=self.fallback_port,
                    user=self.fallback_user,
                    password=self.fallback_password,
                    security=self.fallback_security,
                    to=to,
                    subject=subject,
                    body_html=body_html,
                    reply_to=reply_to,
                    from_address=self.fallback_user,
                    attachments=attachments,
                )
                logger.info(
                    "email.sent.fallback",
                    extra={
                        "to": to,
                        "subject": subject,
                        "fallback_host": self.fallback_host,
                        "fallback_user": self.fallback_user,
                    },
                )
                metrics_registry.record_email(sent=True)
                return

            except Exception as fallback_error:
                logger.exception(
                    "email.fallback_failed",
                    extra={"to": to, "subject": subject, "error": str(fallback_error)},
                )
                metrics_registry.record_email(sent=False)
                raise EmailSendFailedError(
                    f"SMTP principal y fallback fallaron: {fallback_error}",
                    "SMTP_ALL_FAILED",
                )

    async def _attempt_send(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        security: str,
        to: str,
        subject: str,
        body_html: str,
        reply_to: Optional[str],
        from_address: Optional[str],
        attachments: Optional[List[Dict[str, Any]]] = None,
    ):
        security = (security or "ssl").lower()

        if security not in {"ssl", "starttls", "none"}:
            raise ValueError(f"SMTP_SECURITY inválido: {security}")

        msg = self._build_message(
            to=to,
            subject=subject,
            body_html=body_html,
            reply_to=reply_to,
            from_address=from_address,
            attachments=attachments,
        )

        use_tls = security == "ssl"
        start_tls = security == "starttls"

        client = aiosmtplib.SMTP(
            hostname=host,
            port=port,
            use_tls=use_tls,
            start_tls=start_tls,
            timeout=20.0,
        )

        async with client:
            await client.login(user, password)
            await client.send_message(msg)

    async def send_signature_email(
        self,
        employee_email: str,
        employee_name: str,
        signature_link: str,
        organization_name: str,
        tracking_token: str,
        company_email: Optional[str] = None,
        period: Optional[str] = None,
    ):
        subject = "Firma pendiente — Recibo de sueldo"

        _base = config._detect_ngrok_url() or config.BASE_PUBLIC_URL
        pixel_url = f"{_base}/api/mail/open/{tracking_token}"
        pixel_tag = f'<img src="{pixel_url}" width="1" height="1" style="display:none;"/>'

        period_line = f'<p style="margin:4px 0;"><strong>Periodo:</strong> {period}</p>' if period else ""

        body_html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <p style="font-size: 16px;">Hola {employee_name},</p>
            <p>Tienes un recibo de sueldo pendiente de firma.</p>

            <div style="background: #f8f9fa; border-left: 4px solid #2563eb; padding: 12px 16px; border-radius: 4px; margin: 16px 0;">
                <p style="margin:4px 0;"><strong>Empresa:</strong> {organization_name}</p>
                {period_line}
            </div>

            <p>Accede al siguiente enlace para revisarlo y firmarlo:</p>

            <p style="text-align: center; margin: 24px 0;">
                <a href="{signature_link}" style="display: inline-block; padding: 12px 28px; background-color: #2563eb; color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600;">👉 Firmar Recibo</a>
            </p>

            <p style="font-size: 13px; color: #666;">Alternativamente, copia y pega este enlace en tu navegador:<br>
            <span style="color: #2563eb;">{signature_link}</span></p>

            <p style="font-size: 13px; color: #888; margin-top: 16px;">Este enlace es personal, seguro y expira automáticamente.</p>

            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #999;">
                Sistema: <strong>{config.SYSTEM_NAME}</strong>
            </p>
            {pixel_tag}
        </body>
        </html>
        """

        await self.send_html(
            to=employee_email,
            subject=subject,
            body_html=body_html,
            reply_to=company_email,
        )

    async def send_verification_otp_email(self, to: str, code: str, organization_name: str):
        subject = f"Código de verificación — {organization_name}"

        body_html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 24px;">
                <h2 style="color: #1d4ed8; margin: 0;">Verificación de Identidad</h2>
                <p style="color: #666; font-size: 14px;">{organization_name}</p>
            </div>

            <p>Hola,</p>
            <p>Has solicitado un código de verificación para acceder a la firma de tu recibo de sueldo.</p>

            <div style="background: #f1f5f9; border-radius: 8px; padding: 24px; text-align: center; margin: 24px 0;">
                <span style="font-family: monospace; font-size: 32px; font-weight: bold; letter-spacing: 4px; color: #0f172a;">{code}</span>
            </div>

            <p style="font-size: 14px; color: #666;">Este código es válido por 10 minutos. No lo compartas con nadie.</p>

            <p style="font-size: 13px; color: #888; margin-top: 32px;">Si no has solicitado este código, puedes ignorar este mensaje.</p>

            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="font-size: 12px; color: #94a3b8; text-align: center;">
                Sistema: <strong>{config.SYSTEM_NAME}</strong>
            </p>
        </body>
        </html>
        """

        await self.send_html(to=to, subject=subject, body_html=body_html)

    async def send_company_notification_alert(
        self,
        to_emails: List[str],
        organization_name: str,
        sender_name: str,
        message_preview: str,
    ):
        subject = f"Nueva notificación de {sender_name} - {organization_name}"

        valid_emails = [email for email in to_emails if email]
        if not valid_emails:
            logger.warning("email.notification.no_recipients", extra={"org": organization_name})
            return

        body_html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <p style="font-size: 16px;">Hola,</p>
            <p><strong>{sender_name}</strong> ha enviado una nueva notificación a la empresa <strong>{organization_name}</strong> a través de {config.SYSTEM_NAME}.</p>

            <div style="background: #f8f9fa; border-left: 4px solid #2563eb; padding: 12px 16px; border-radius: 4px; margin: 16px 0;">
                <p style="margin:0; font-style: italic; color: #555;">"{message_preview}..."</p>
            </div>

            <p>Por favor, ingresá al dashboard de la empresa para ver el mensaje completo y los archivos adjuntos si los hubiera.</p>

            <p style="text-align: center; margin: 24px 0;">
                <a href="{config.BASE_PUBLIC_URL}/ui/#/empresa/dashboard" style="display: inline-block; padding: 12px 28px; background-color: #2563eb; color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600;">Ver Notificación</a>
            </p>

            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #999;">
                Sistema: <strong>{config.SYSTEM_NAME}</strong>
            </p>
        </body>
        </html>
        """

        for email in valid_emails:
            await self.send_html(to=email, subject=subject, body_html=body_html)

    async def send_employee_notification_alert(
        self,
        to_email: str,
        organization_name: str,
        sender_name: str,
        message_preview: str,
    ):
        subject = f"Nueva notificación de {sender_name} - {organization_name}"

        body_html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <p style="font-size: 16px;">Hola,</p>
            <p><strong>{sender_name}</strong> te ha enviado una nueva notificación a través de {config.SYSTEM_NAME}.</p>

            <div style="background: #f8f9fa; border-left: 4px solid #2563eb; padding: 12px 16px; border-radius: 4px; margin: 16px 0;">
                <p style="margin:0; font-style: italic; color: #555;">"{message_preview}..."</p>
            </div>

            <p>Ingresá al dashboard de empleado para ver el mensaje completo y los archivos adjuntos si los hubiera.</p>

            <p style="text-align: center; margin: 24px 0;">
                <a href="{config.BASE_PUBLIC_URL}/ui/#/empleado/recibos" style="display: inline-block; padding: 12px 28px; background-color: #2563eb; color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600;">Ver Notificación</a>
            </p>

            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #999;">
                Sistema: <strong>{config.SYSTEM_NAME}</strong>
            </p>
        </body>
        </html>
        """

        await self.send_html(to=to_email, subject=subject, body_html=body_html)

    async def send_password_reset_otp_email(self, to: str, code: str):
        ttl = getattr(config, "OTP_EXPIRATION_MINUTES", 10)
        subject = f"Código para restablecer contraseña — {config.SYSTEM_NAME}"

        body_html = f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="text-align: center; margin-bottom: 24px;">
                <h2 style="color: #1d4ed8; margin: 0;">Restablecer contraseña</h2>
                <p style="color: #666; font-size: 14px;">{config.SYSTEM_NAME}</p>
            </div>

            <p>Hola,</p>
            <p>Recibimos una solicitud para restablecer tu contraseña. Ingresá el siguiente código de seguridad en la pantalla de recuperación:</p>

            <div style="background: #f1f5f9; border-radius: 8px; padding: 24px; text-align: center; margin: 24px 0;">
                <span style="font-family: monospace; font-size: 32px; font-weight: bold; letter-spacing: 4px; color: #0f172a;">{code}</span>
            </div>

            <div style="background: #fef3cd; border-left: 4px solid #f59e0b; padding: 12px 16px; border-radius: 4px; margin: 16px 0;">
                <p style="margin: 0; font-size: 13px; color: #92400e;">
                    ⏱️ Este código es válido por <strong>{ttl} minutos</strong> y solo puede usarse una vez.
                </p>
            </div>

            <p style="font-size: 13px; color: #888; margin-top: 24px;">
                ⚠️ <strong>Si no solicitaste este restablecimiento, ignorá este correo.</strong>
                Tu contraseña no será modificada.
            </p>

            <hr style="border: 0; border-top: 1px solid #e2e8f0; margin: 24px 0;">
            <p style="font-size: 12px; color: #94a3b8; text-align: center;">
                Sistema: <strong>{config.SYSTEM_NAME}</strong>
            </p>
        </body>
        </html>
        """

        await self.send_html(to=to, subject=subject, body_html=body_html)