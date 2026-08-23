import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# 1. Fuerza la carga del archivo .env que está en el mismo directorio
env_path = Path('.') / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)
    print("✅ Archivo .env cargado correctamente.")
else:
    print("❌ ERROR: No se encuentra el archivo .env en la ruta actual.")
    sys.exit(1)

# 2. Validación crítica de variables antes de importar servicios
required_vars = ["SECRET_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"]
for var in required_vars:
    if not os.getenv(var):
        print(f"❌ ERROR: La variable {var} no está definida en .env")
        sys.exit(1)
    else:
        print(f"✅ {var} encontrada.")

# 3. Intenta la importación y prueba
try:
    from services.email_service import EmailService
    import asyncio

    async def run_test():
        svc = EmailService()
        print("🚀 Intentando conexión asíncrona con Amazon SES...")
        # Cambia esto por un correo tuyo real
        await svc._send_smtp_async(
            to="tu_correo_personal@ejemplo.com",
            subject="Test de Conectividad Final",
            body_html="<h1>Prueba Exitosa</h1><p>El backend ahora puede enviar emails.</p>"
        )
        print("✨ ¡Correo enviado correctamente!")

    asyncio.run(run_test())

except Exception as e:
    print(f"\n⚠️ Ocurrió un error durante la ejecución:")
    print(str(e))