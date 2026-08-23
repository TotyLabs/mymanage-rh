"""
services/pki_service.py

Minimal internal PKI for Dircom Payroll.
Functions for Root CA generation and signing certificate issuance via cryptography.
"""

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import config

def _save_pem(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)

def generate_root_ca():
    """Generates a long-lived self-signed Root CA (v3 Hardened)."""
    root_key_path = Path(config.ROOT_KEY_PATH)
    root_cert_path = Path(config.ROOT_CA_PATH)

    if root_cert_path.exists() and root_key_path.exists():
        return str(root_cert_path)

    # 1. Generate Private Key (4096 for Root)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    # 2. Structure Subject/Issuer
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Buenos Aires"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MyManageRH"),
        x509.NameAttribute(NameOID.COMMON_NAME, "MyManageRH Root CA"),
    ])

    # 3. Create Certificate with proper CA extensions
    now = datetime.now(timezone.utc)
    cert_builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(hours=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=True,
                crl_sign=True, encipher_only=False, decipher_only=False
            ),
            critical=True
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()), critical=False)
    )

    # Phase 5.2: Revocation Information (Self-referencing for Root)
    base_url = config.BASE_PUBLIC_URL
    cert_builder = cert_builder.add_extension(
        x509.CRLDistributionPoints([
            x509.DistributionPoint(
                full_name=[x509.UniformResourceIdentifier(f"{base_url}/pki/root_ca.crl")],
                relative_name=None,
                reasons=None,
                crl_issuer=None,
            )
        ]),
        critical=False
    )

    cert = cert_builder.sign(private_key, hashes.SHA256())

    # 4. Persistence — Root CA key MUST be encrypted. No fallback.
    root_key_password = config.X509_P12_PASSWORD.encode() if config.X509_P12_PASSWORD else None
    if not root_key_password:
        raise RuntimeError("Cannot generate Root CA: X509_P12_PASSWORD is not set. Set it in .env before PKI initialization.")
    _save_pem(root_key_path, private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(root_key_password),
    ))
    _save_pem(root_cert_path, cert.public_bytes(serialization.Encoding.PEM))

    return str(root_cert_path)

def generate_crl():
    """Generates a fresh CRL signed by the Root CA."""
    root_key_path = Path(config.ROOT_KEY_PATH)
    root_cert_path = Path(config.ROOT_CA_PATH)
    crl_path = Path(config.X509_CRL_PATH)

    if not root_key_path.exists() or not root_cert_path.exists():
        generate_root_ca()

    root_key_password = config.X509_P12_PASSWORD.encode() if config.X509_P12_PASSWORD else None
    with open(root_key_path, "rb") as f:
        root_key = serialization.load_pem_private_key(f.read(), password=root_key_password)
    with open(root_cert_path, "rb") as f:
        root_cert = x509.load_pem_x509_certificate(f.read())

    now = datetime.now(timezone.utc)
    crl_builder = x509.CertificateRevocationListBuilder()
    crl_builder = crl_builder.issuer_name(root_cert.subject)
    crl_builder = crl_builder.last_update(now)
    crl_builder = crl_builder.next_update(now + timedelta(days=30))
    # No revocations for now
    
    crl_builder = crl_builder.add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()),
        critical=False
    )
    
    crl = crl_builder.sign(root_key, hashes.SHA256())
    
    crl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(crl_path, "wb") as f:
        f.write(crl.public_bytes(serialization.Encoding.DER))
        
    return str(crl_path)

def issue_signing_cert():
    """Issues a sub-certificate signed by the Root CA and packages into P12."""
    root_key_path = Path(config.ROOT_KEY_PATH)
    root_cert_path = Path(config.ROOT_CA_PATH)
    p12_path = Path(config.X509_P12_PATH)
    
    # Ensure Root exists
    if not root_cert_path.exists():
        generate_root_ca()

    root_key_password = config.X509_P12_PASSWORD.encode() if config.X509_P12_PASSWORD else None
    with open(root_key_path, "rb") as f:
        root_key = serialization.load_pem_private_key(f.read(), password=root_key_password)
    with open(root_cert_path, "rb") as f:
        root_cert = x509.load_pem_x509_certificate(f.read())

    # 1. Generate Signer Key
    signer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # 2. Structure Signer Subject
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "AR"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Buenos Aires"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MyManageRH"),
        x509.NameAttribute(NameOID.COMMON_NAME, "MyManageRH Signer Entity"),
    ])

    # 3. Create Sub-Certificate with Adobe/PyHanko compliant extensions
    now = datetime.now(timezone.utc)
    base_url = config.BASE_PUBLIC_URL
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(root_cert.subject)
        .public_key(signer_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(hours=1))
        .not_valid_after(now + timedelta(days=1825))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=True,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False
            ),
            critical=True
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                x509.oid.ExtendedKeyUsageOID.EMAIL_PROTECTION,
                x509.ObjectIdentifier("1.3.6.1.5.5.7.3.3"),   # Code Signing
                x509.ObjectIdentifier("1.3.6.1.4.1.311.10.3.12"), # MS Doc Signing
                x509.ObjectIdentifier("1.2.840.113583.1.1.5"), # Adobe Doc Trust
            ]),
            critical=False
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(signer_key.public_key()), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(root_key.public_key()), critical=False)
        # Phase 5.2: Revocation Extensions
        .add_extension(
            x509.CRLDistributionPoints([
                x509.DistributionPoint(
                    full_name=[x509.UniformResourceIdentifier(f"{base_url}/pki/root_ca.crl")],
                    relative_name=None,
                    reasons=None,
                    crl_issuer=None,
                )
            ]),
            critical=False
        )
        .add_extension(
            x509.AuthorityInformationAccess([
                x509.AccessDescription(
                    x509.oid.AuthorityInformationAccessOID.OCSP,
                    x509.UniformResourceIdentifier(f"{base_url}/pki/ocsp")
                ),
                x509.AccessDescription(
                    x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                    x509.UniformResourceIdentifier(f"{base_url}/pki/root_ca.crt")
                )
            ]),
            critical=False
        )
        .sign(root_key, hashes.SHA256())
    )

    # 4. Generate P12 Bundle
    from cryptography.hazmat.primitives.serialization import pkcs12
    p12_password = config.X509_P12_PASSWORD.encode() if config.X509_P12_PASSWORD else None
    
    p12_data = pkcs12.serialize_key_and_certificates(
        b"MyManageRH Signer",
        signer_key,
        cert,
        [root_cert],
        serialization.BestAvailableEncryption(p12_password) if p12_password else serialization.NoEncryption()
    )
    
    # Save P12
    p12_path.parent.mkdir(parents=True, exist_ok=True)
    p12_path.write_bytes(p12_data)
    
    # Also save legacy PEMs for backward compat if config paths are different
    if str(config.CERT_PATH) != str(p12_path):
        _save_pem(config.CERT_PATH, cert.public_bytes(serialization.Encoding.PEM))
    if str(config.KEY_PATH) != str(p12_path):
        _save_pem(config.KEY_PATH, signer_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ))

    return str(p12_path)
