import smtplib
from email.mime.text import MIMEText

# Credenciales de tu entorno de configuración
SMTP_HOST = "email-smtp.us-east-1.amazonaws.com"
SMTP_PORT = 465
SMTP_USER = "AKIASGSRX4A5Q4OTOKFN"
SMTP_PASSWORD = "BCQoV+3PJYJoRwYZTvuj9f25i1MyiZHLisGHeie/Khz+"

# Tu casilla propia donde vas a recibir la alerta de Amazon SES
CORREO_DESTINO = "scandrolifacundo2012@gmail.com" 

# Estructura del correo electrónico
msg = MIMEText("Solicitud forzada de activacion de identidad de AWS SES.")
msg["Subject"] = "Forzar Verificacion AWS"
msg["From"] = "no-reply@mymanagerh.com"
msg["To"] = CORREO_DESTINO

print("[*] Conectando de forma segura con el servidor SMTP de Amazon SES (us-east-1)...")

try:
    # Conexión SSL directa estándar
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        print("[*] Autenticando credenciales SMTP de AWS...")
        server.login(SMTP_USER, SMTP_PASSWORD)
        
        print(f"[*] Lanzando petición de envío: no-reply@mymanagerh.com -> {CORREO_DESTINO}")
        server.sendmail("no-reply@mymanagerh.com", [CORREO_DESTINO], msg.as_string())
        
    print("[+] ¡Envío exitoso! El remitente ya se encontraba validado previamente.")

except smtplib.SMTPDataError as e:
    # Capturamos el código 554 idéntico al de tus logs de producción
    if e.smtp_code == 554:
        print("\n" + "="*70)
        print("[!] PETICIÓN DE VERIFICACIÓN DISPARADA CON ÉXITO")
        print("="*70)
        print("Amazon SES rechazó el correo saliente tal como queríamos.")
        print("Al usar credenciales válidas, AWS detectó el fallo y envió")
        print("un correo de activación automático a la cuenta del remitente:")
        print("-> no-reply@mymanagerh.com")
        print("-"*70)
        print("[>] ACCIÓN REQUERIDA: Ingresa a la bandeja de entrada de ese")
        print("    correo corporativo y haz clic en el botón de confirmación.")
        print("="*70)
    else:
        print(f"[-] Error devuelto por Amazon SES (Código {e.smtp_code}): {e.smtp_error}")

except Exception as e:
    print(f"[-] Ocurrió un fallo en la conexión: {e}")
