import os
import sys
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))
# 1. Environment Setup (Must be before config import)
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import config

def inspect_p12():
    p12_path = Path(config.X509_P12_PATH)
    password = config.X509_P12_PASSWORD.encode()
    
    if not p12_path.exists():
        print(f"ERROR: P12 not found at {p12_path}")
        return

    print(f"Inspecting: {p12_path}")
    with open(p12_path, "rb") as f:
        p12_data = f.read()
        
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        p12_data, password
    )

    print("\n--- SIGNER CERTIFICATE ---")
    print(f"Subject: {certificate.subject}")
    print(f"Issuer: {certificate.issuer}")
    print(f"Not Before: {certificate.not_valid_before_utc}")
    print(f"Not After: {certificate.not_valid_after_utc}")

    print("\nExtensions:")
    for ext in certificate.extensions:
        print(f"- {ext.oid._name}: {ext.value}")

    if additional_certificates:
        print("\n--- ADDITIONAL CERTIFICATES (CHAIN) ---")
        for i, cert in enumerate(additional_certificates):
            print(f"[{i}] Subject: {cert.subject}")
            print(f"    Issuer: {cert.issuer}")

if __name__ == "__main__":
    inspect_p12()
