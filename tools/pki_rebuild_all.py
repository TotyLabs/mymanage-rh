import os
import datetime
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
CERTS_DIR = BASE_DIR / "certs"

P12_PASSWORD = os.environ.get("X509_P12_PASSWORD", "").encode()
if not P12_PASSWORD:
    raise RuntimeError("X509_P12_PASSWORD env var is required.")

def rebuild_all():
    print("Generating new Root CA...")
    root_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    root_subject = root_issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"AR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Buenos Aires"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"MyManageRH"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"MyManageRH Root CA"),
    ])
    
    root_cert = x509.CertificateBuilder().subject_name(
        root_subject
    ).issuer_name(
        root_issuer
    ).public_key(
        root_key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
    ).add_extension(
        x509.BasicConstraints(ca=True, path_length=None), critical=True
    ).add_extension(
        x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False
        ),
        critical=True
    ).add_extension(
        x509.SubjectKeyIdentifier.from_public_key(root_key.public_key()), critical=False
    ).sign(root_key, hashes.SHA256())
    
    # Save Root CA
    with open(CERTS_DIR / "root_key.pem", "wb") as f:
        f.write(root_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(P12_PASSWORD)
        ))
    with open(CERTS_DIR / "root_ca.crt", "wb") as f:
        f.write(root_cert.public_bytes(serialization.Encoding.PEM))
    
    print("Generating new end-entity signer cert...")
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signer_subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, u"AR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, u"Buenos Aires"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"MyManageRH"),
        x509.NameAttribute(NameOID.COMMON_NAME, u"MyManageRH Signing Entity"),
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
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1825)
    ).add_extension(
        x509.BasicConstraints(ca=False, path_length=None), critical=True
    ).add_extension(
        x509.KeyUsage(
            digital_signature=True, content_commitment=True, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False
        ),
        critical=True
    ).add_extension(
        x509.ExtendedKeyUsage([
            ExtendedKeyUsageOID.CLIENT_AUTH,
            ExtendedKeyUsageOID.EMAIL_PROTECTION,
            x509.ObjectIdentifier("1.3.6.1.5.5.7.3.3"),
            x509.ObjectIdentifier("1.3.6.1.4.1.311.10.3.12"),
            x509.ObjectIdentifier("1.2.840.113583.1.1.5"),
        ]),
        critical=False
    ).add_extension(
        x509.SubjectKeyIdentifier.from_public_key(signer_key.public_key()), critical=False
    ).add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False
    ).sign(root_key, hashes.SHA256())
    
    print("Packaging into PKCS#12 bundle...")
    p12_data = pkcs12.serialize_key_and_certificates(
        b"MyManageRH Signer",
        signer_key,
        signer_cert,
        [root_cert],
        serialization.BestAvailableEncryption(P12_PASSWORD)
    )
    with open(CERTS_DIR / "signer.p12", "wb") as f:
        f.write(p12_data)
        
    print("PKI Rebuild Complete.")

if __name__ == "__main__":
    rebuild_all()
