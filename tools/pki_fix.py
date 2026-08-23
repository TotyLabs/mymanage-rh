import os
import datetime
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from dotenv import load_dotenv

# Paths (dynamic resolution)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
CERTS_DIR = BASE_DIR / "certs"

ROOT_CA_CERT = CERTS_DIR / "root_ca.crt"
ROOT_CA_KEY = CERTS_DIR / "root_key.pem"
SIGNER_P12 = CERTS_DIR / "signer.p12"

# C-001 FIX: Password from environment, no hardcoded default
P12_PASSWORD = os.environ.get("X509_P12_PASSWORD", "").encode()
if not P12_PASSWORD:
    print("ERROR: X509_P12_PASSWORD env var is required.")
    import sys; sys.exit(1)

def generate_signing_cert():
    print(f"Loading Root CA from {ROOT_CA_CERT}...")
    root_cert = x509.load_pem_x509_certificate(ROOT_CA_CERT.read_bytes())
    root_key = serialization.load_pem_private_key(ROOT_CA_KEY.read_bytes(), None)

    print("Generating new key for end-entity signer...")
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"AR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Buenos Aires"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"MyManageRH"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"MyManageRH Signing Entity"),
    ])

    print("Creating signing certificate...")
    signer_cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        root_cert.subject
    ).public_key(
        signer_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        # 5 year validity
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1825)
    ).add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=True,
            key_encipherment=True,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=False,
            crl_sign=False,
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    ).add_extension(
        x509.ExtendedKeyUsage([
            ExtendedKeyUsageOID.CLIENT_AUTH,
            ExtendedKeyUsageOID.EMAIL_PROTECTION,
            x509.ObjectIdentifier("1.3.6.1.5.5.7.3.3"),   # Code Signing
            x509.ObjectIdentifier("1.3.6.1.4.1.311.10.3.12"), # Microsoft Document Signing
            x509.ObjectIdentifier("1.2.840.113583.1.1.5"), # Adobe Authentic Documents Trust
        ]),
        critical=False,
    ).sign(root_key, hashes.SHA256())

    print(f"Packaging into PKCS#12 bundle: {SIGNER_P12}...")
    p12_data = pkcs12.serialize_key_and_certificates(
        b"MyManageRH Signer",
        signer_key,
        signer_cert,
        [root_cert],
        serialization.BestAvailableEncryption(P12_PASSWORD)
    )

    SIGNER_P12.write_bytes(p12_data)
    print("SUCCESS: PKI Rectification complete.")
    print(f"Bundle: {SIGNER_P12}")

if __name__ == "__main__":
    try:
        generate_signing_cert()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
