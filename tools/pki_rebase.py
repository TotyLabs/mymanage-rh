import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from pathlib import Path
import os

# Paths
BASE_DIR = Path(r'c:\Users\lenov\OneDrive\Desktop\dircom-payroll')
CERTS_DIR = BASE_DIR / "certs"

ROOT_CA_CERT_PATH = CERTS_DIR / "root_ca.crt"
ROOT_CA_KEY_PATH = CERTS_DIR / "root_key.pem"
SIGNER_P12_PATH = CERTS_DIR / "signer.p12"
# C-001 FIX: Password from environment, no hardcoded default
P12_PASSWORD = os.environ.get("X509_P12_PASSWORD", "").encode()
if not P12_PASSWORD:
    print("ERROR: X509_P12_PASSWORD env var is required.")
    import sys; sys.exit(1)

def rebase_pki():
    os.makedirs(CERTS_DIR, exist_ok=True)
    
    print("--- Phase 1: Generating Perfect Root CA ---")
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    
    root_subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"AR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Buenos Aires"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"MyManageRH"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"MyManageRH Root CA"),
    ])
    
    now = datetime.datetime.now(datetime.timezone.utc)
    
    root_cert = x509.CertificateBuilder().subject_name(
        root_subject
    ).issuer_name(
        root_subject # Self-signed
    ).public_key(
        root_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        now - datetime.timedelta(hours=1)
    ).not_valid_after(
        now + datetime.timedelta(days=3650) # 10 years
    ).add_extension(
        x509.BasicConstraints(ca=True, path_length=None),
        critical=True,
    ).add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True, # CRITICAL FOR CA
            crl_sign=True,      # CRITICAL FOR CA
            encipher_only=False,
            decipher_only=False,
        ),
        critical=True,
    ).add_extension(
        x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()),
        critical=False,
    ).sign(root_key, hashes.SHA256())
    
    # Save Root CA
    ROOT_CA_CERT_PATH.write_bytes(root_cert.public_bytes(serialization.Encoding.PEM))
    ROOT_CA_KEY_PATH.write_bytes(root_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ))
    print(f"SUCCESS: Root CA generated at {ROOT_CA_CERT_PATH}")

    print("\n--- Phase 2: Generating Perfect Signer EE Cert ---")
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    
    signer_subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"AR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Buenos Aires"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"MyManageRH"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"MyManageRH Signer Entity"),
    ])
    
    signer_cert = x509.CertificateBuilder().subject_name(
        signer_subject
    ).issuer_name(
        root_cert.subject
    ).public_key(
        signer_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        now - datetime.timedelta(hours=1)
    ).not_valid_after(
        now + datetime.timedelta(days=1825) # 5 years
    ).add_extension(
        x509.BasicConstraints(ca=False, path_length=None),
        critical=True,
    ).add_extension(
        x509.KeyUsage(
            digital_signature=True,
            content_commitment=True, # Non-repudiation
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
            x509.ObjectIdentifier("1.3.6.1.4.1.311.10.3.12"), # MS Document Signing
            x509.ObjectIdentifier("1.2.840.113583.1.1.5"), # Adobe Document Trust
        ]),
        critical=False,
    ).add_extension(
        x509.SubjectKeyIdentifier.from_public_key(signer_key.public_key()),
        critical=False,
    ).add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
        critical=False,
    ).sign(root_key, hashes.SHA256())
    
    print(f"Packaging into PKCS#12 bundle: {SIGNER_P12_PATH}...")
    p12_data = pkcs12.serialize_key_and_certificates(
        b"MyManageRH Signer",
        signer_key,
        signer_cert,
        [root_cert],
        serialization.BestAvailableEncryption(P12_PASSWORD)
    )
    
    SIGNER_P12_PATH.write_bytes(p12_data)
    print(f"SUCCESS: Signer bundle generated at {SIGNER_P12_PATH}")

if __name__ == "__main__":
    try:
        rebase_pki()
        print("\nPKI REBASE COMPLETE. ALL REQUIREMENTS MET.")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
