#!/usr/bin/env python3
import os
import sys
import platform
import subprocess

# Usamos una ruta relativa pero la convertimos a absoluta y normalizamos barras
CERT_RELATIVE_PATH = "certs/root_ca.crt"

def install_ca():
    if not os.path.exists(CERT_RELATIVE_PATH):
        print(f"❌ Root CA no encontrada en: {CERT_RELATIVE_PATH}")
        sys.exit(1)

    system = platform.system()
    # Normalizamos la ruta para el OS actual
    abs_cert_path = os.path.abspath(CERT_RELATIVE_PATH)

    if system == "Windows":
        print(f"Instalando en Windows (Solicitando UAC)...")
        
        # Escapamos las comillas internas para PowerShell de forma más segura
        # Usamos una sola cadena de argumentos y dejamos que PowerShell la maneje
        args = f'-addstore Root "{abs_cert_path}"'
        ps_command = f'Start-Process certutil -ArgumentList \'{args}\' -Verb RunAs -Wait'
        
        try:
            # Ejecutamos con shell=True para asegurar que el comando pase limpio
            subprocess.run(["powershell", "-Command", ps_command], check=True)
            print("✅ El proceso de instalación ha finalizado.")
            print("Nota: Si aceptaste el cartel de UAC, el certificado ya debería estar en el almacén 'Root'.")
        except subprocess.CalledProcessError as e:
            print(f"❌ Error al intentar elevar privilegios: {e}")
            
    elif system == "Darwin":
        print("Instalando en macOS...")
        subprocess.run(["sudo", "security", "add-trusted-cert", "-d", "-r", "trustRoot", "-k", "/Library/Keychains/System.keychain", abs_cert_path])
        
    elif system == "Linux":
        print("Instalando en Linux...")
        dest = "/usr/local/share/ca-certificates/ca_root_install.crt"
        subprocess.run(["sudo", "cp", abs_cert_path, dest])
        subprocess.run(["sudo", "update-ca-certificates"])

if __name__ == "__main__":
    install_ca()