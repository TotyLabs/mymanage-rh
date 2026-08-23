import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
load_dotenv()

from services.pki_vault import SecureKeyVault
from payroll_core import SessionLocal
import config

def provision_vault():
    print("Industrial PKI Vault Provisioning (CRT-003)")
    print("-" * 40)
    
    db = SessionLocal()
    vault = SecureKeyVault(config.MASTER_ENCRYPTION_KEY)
    
    certs_dir = Path(config.BASE_DIR) / "certs"
    
    # 1. Signer P12
    p12_path = certs_dir / "signer.p12"
    if p12_path.exists():
        print(f"[*] Importing {p12_path} ...")
        p12_data = p12_path.read_bytes()
        vault.store_new_key(db, "signer_p12", p12_data)
        print("[+] Success: signer_p12")
    else:
        print(f"[!] Warning: {p12_path} not found.")

    # 2. Root CA
    root_ca_path = certs_dir / "root_ca.crt"
    if root_ca_path.exists():
        print(f"[*] Importing {root_ca_path} ...")
        root_ca_data = root_ca_path.read_bytes()
        vault.store_new_key(db, "root_ca", root_ca_data)
        print("[+] Success: root_ca")
    else:
        print(f"[!] Warning: {root_ca_path} not found.")

    db.commit()
    db.close()
    print("-" * 40)
    print("Provisioning Complete.")

if __name__ == "__main__":
    provision_vault()
