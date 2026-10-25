import os
import smtplib
import ssl
from email.message import EmailMessage


def main() -> None:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    sender = os.getenv("EMAIL_FROM")
    recipient = os.getenv("AWS_SES_TEST_RECIPIENT")

    if not all((host, username, password, sender, recipient)):
        raise SystemExit("Configure SMTP_HOST, SMTP_USER, SMTP_PASSWORD, EMAIL_FROM and AWS_SES_TEST_RECIPIENT.")

    message = EmailMessage()
    message["Subject"] = "Prueba de correo MyManageRH"
    message["From"] = sender
    message["To"] = recipient
    message.set_content("Este es un correo de prueba de la configuración SMTP.")

    with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=15) as server:
        server.login(username, password)
        server.send_message(message)

    print("Correo de prueba enviado correctamente.")


if __name__ == "__main__":
    main()
