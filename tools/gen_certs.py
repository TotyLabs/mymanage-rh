"""
Utility to generate self-signed X.509 certificates for Phase 1.
Usage: python tools/gen_certs.py
"""
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

def generate_self_signed_cert(cert_dir: Path):
    os.makedirs(cert_dir, exist_ok=True)
    
    cert_path = cert_dir / "cert.crt"
    key_path = cert_dir / "key.pem"

    if cert_path.exists() or key_path.exists():
        print(f"ERROR: Certificates already exist in {cert_dir}. Move them if you want to regenerate.")
        return

    print("Generating RSA 2048 private key...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    print("Creating self-signed certificate...")
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Buenos Aires"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "CABA"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Dircom SRL"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Dircom Payroll Root CA"),
    ])
    
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        private_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.now(timezone.utc)
    ).not_valid_after(
        # 10 years validity
        datetime.now(timezone.utc) + timedelta(days=3650)
    ).add_extension(
        x509.SubjectAlternativeName([x509.DNSName("localhost")]),
        critical=False,
    ).sign(private_key, hashes.SHA256())

    # Write private key
    with open(key_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
    
    # Surgical Adjustment: Set permissions to 600 (owner-only)
    try:
        os.chmod(key_path, 0o600)
        print(f"Set permissions 600 on {key_path}")
    except Exception as e:
        print(f"Warning: Could not set permissions on {key_path}: {e}")

    # Write certificate
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"SUCCESS: Generated {cert_path} and {key_path}")

if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent.parent
    certs_dir = BASE_DIR / "certs"
    generate_self_signed_cert(certs_dir)
