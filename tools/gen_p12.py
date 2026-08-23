from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography import x509
from pathlib import Path
import os
import sys

certs_dir = Path(r'c:\Users\lenov\OneDrive\Desktop\dircom-payroll\certs')
p12_path = certs_dir / 'bundle.p12'

print(f"Reading from: {certs_dir}")

try:
    cert_bytes = (certs_dir / 'root_ca.crt').read_bytes()
    key_bytes = (certs_dir / 'root_ca.key').read_bytes()
    
    cert = x509.load_pem_x509_certificate(cert_bytes)
    key = serialization.load_pem_private_key(key_bytes, None)
    
    # C-001 FIX: Password MUST come from environment
    p12_pass = os.environ.get("X509_P12_PASSWORD", "")
    if not p12_pass:
        print("ERROR: X509_P12_PASSWORD env var is required. Set it before running.")
        sys.exit(1)
    p12_data = pkcs12.serialize_key_and_certificates(
        b'MyManageRH', 
        key, 
        cert, 
        None, 
        serialization.BestAvailableEncryption(p12_pass.encode())
    )
    
    p12_path.write_bytes(p12_data)
    print(f"SUCCESS: P12 bundle created at {p12_path}")
except Exception as e:
    print(f"FAILED: {e}")
