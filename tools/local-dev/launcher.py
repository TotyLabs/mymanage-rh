from pyngrok import ngrok
import uvicorn
import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# DefiniciÃ³n de puerto
PORT = 8000

def start_launcher():
    print("\nInitializing MyManageRH Infrastructure...")
    
    try:
        # 0. Configurar Auth Token si existe
        auth_token = os.getenv("NGROK_AUTHTOKEN")
        if auth_token:
            print(f"Configuring Ngrok Auth Token (starts with {auth_token[:5]}...)")
            ngrok.set_auth_token(auth_token)
        else:
            print("[WARNING] NGROK_AUTHTOKEN not found in .env. Some features might be restricted.")

        # 1. Asegurar que no haya tÃºneles previos
        print("Cleaning up old tunnels...")
        ngrok.kill()

        # 2. Crear nuevo tÃºnel para el puerto 8000
        print(f"Creating Ngrok tunnel for port {PORT}...")
        tunnel = ngrok.connect(PORT)
        public_url = tunnel.public_url

        # 3. Mostrar informaciÃ³n formateada al usuario
        print("\n" + "="*40)
        print("   MyManageRH Server")
        print("="*40)
        print(f"   Local:  http://localhost:{PORT}")
        print(f"   Public: {public_url}")
        print("="*40 + "\n")

        # 4. Exportar la URL pÃºblica para que config.py la reconozca
        os.environ["NGROK_PUBLIC_URL"] = public_url

        # 5. Lanzar el servidor FastAPI usando uvicorn
        # Importante: Usamos 'main:app' porque el objeto FastAPI estÃ¡ en main.py
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=PORT,
            reload=False
        )
        
    except Exception as e:
        print(f"\n[ERROR] Failed to start infrastructure: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    start_launcher()
