"""Cryptographic chain validation - verifies the signer cert is ACTUALLY signed by Root CA."""
import os, sys
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.asymmetric import padding
import config

def validate_chain():
    p12_path = Path(config.X509_P12_PATH)
    root_path = Path(config.ROOT_CA_PATH)
    
    print(f"P12: {p12_path}")
    print(f"Root CA: {root_path}")
    print()
    
    # Load P12
    p12_data = p12_path.read_bytes()
    pw = config.X509_P12_PASSWORD.encode()
    _, signer_cert, chain = pkcs12.load_key_and_certificates(p12_data, pw)
    
    # Load Root CA from disk
    root_cert = x509.load_pem_x509_certificate(root_path.read_bytes())
    
    print("=== SIGNER CERTIFICATE ===")
    print(f"  Subject: {signer_cert.subject.rfc4514_string()}")
    print(f"  Issuer:  {signer_cert.issuer.rfc4514_string()}")
    print(f"  Serial:  {signer_cert.serial_number}")
    print(f"  Valid:    {signer_cert.not_valid_before_utc} â†’ {signer_cert.not_valid_after_utc}")
    
    print()
    print("=== ROOT CA ===")
    print(f"  Subject: {root_cert.subject.rfc4514_string()}")
    print(f"  Issuer:  {root_cert.issuer.rfc4514_string()}")
    print(f"  Serial:  {root_cert.serial_number}")
    
    # Check 1: Subject â‰  Issuer on signer cert
    subj = signer_cert.subject.rfc4514_string()
    iss = signer_cert.issuer.rfc4514_string()
    print()
    if subj == iss:
        print("âŒ FAIL: Signer is SELF-SIGNED (Subject == Issuer)")
    else:
        print("âœ… PASS: Signer is NOT self-signed (Subject â‰  Issuer)")
    
    # Check 2: Signer's Issuer matches Root CA's Subject
    root_subj = root_cert.subject.rfc4514_string()
    if iss == root_subj:
        print("âœ… PASS: Signer's Issuer matches Root CA Subject")
    else:
        print(f"âŒ FAIL: Issuer mismatch\n  Signer Issuer: {iss}\n  Root Subject:  {root_subj}")
    
    # Check 3: Cryptographic verification (verify signer cert was signed by Root CA's key)
    try:
        root_cert.public_key().verify(
            signer_cert.signature,
            signer_cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            signer_cert.signature_hash_algorithm,
        )
        print("âœ… PASS: Signature VERIFIED â€” Root CA's key signed the signer cert")
    except Exception as e:
        print(f"âŒ FAIL: Signature verification failed â€” {e}")
    
    # Check 4: Chain in P12
    if chain:
        print(f"âœ… PASS: P12 contains {len(chain)} additional cert(s) in chain")
        for i, c in enumerate(chain):
            print(f"  [{i}] {c.subject.rfc4514_string()}")
    else:
        print("âŒ FAIL: P12 has NO chain certificates")
    
    # Check 5: KeyUsage
    try:
        ku = signer_cert.extensions.get_extension_for_class(x509.KeyUsage).value
        print(f"âœ… KeyUsage: digitalSignature={ku.digital_signature}, contentCommitment={ku.content_commitment}, keyCertSign={ku.key_cert_sign}")
        if ku.key_cert_sign:
            print("  âš ï¸ WARNING: keyCertSign should be False for end-entity cert")
    except x509.ExtensionNotFound:
        print("âŒ FAIL: No KeyUsage extension")
    
    # Check 6: BasicConstraints
    try:
        bc = signer_cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        if bc.ca:
            print("âŒ FAIL: basicConstraints ca=True (should be False for signer)")
        else:
            print("âœ… PASS: basicConstraints ca=False")
    except x509.ExtensionNotFound:
        print("âŒ FAIL: No BasicConstraints extension")

if __name__ == "__main__":
    validate_chain()
