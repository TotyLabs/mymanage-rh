import os
import sys
import asyncio
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography import x509
from asn1crypto import x509 as asn1_x509
from pyhanko.sign import signers
from pyhanko.sign.general import SigningError

def diagnose_p12(p12_path, password):
    print(f"--- Diagnosing PKCS#12: {p12_path} ---")
    
    # 0. Root CA Inspection
    root_ca_path = "certs/root_ca.crt"
    if os.path.exists(root_ca_path):
        print("\n[Root CA Inspection]")
        with open(root_ca_path, 'rb') as f:
            root_bytes = f.read()
        root_cert_crypt = x509.load_pem_x509_certificate(root_bytes)
        print(f"Subject: {root_cert_crypt.subject}")
        try:
            ku = root_cert_crypt.extensions.get_extension_for_class(x509.KeyUsage).value
            print(f"Key Usage: cert_sign={ku.key_cert_sign}, crl_sign={ku.crl_sign}, digital_signature={ku.digital_signature}")
        except Exception:
            print("Key Usage: NOT FOUND")
        try:
            bc = root_cert_crypt.extensions.get_extension_for_class(x509.BasicConstraints).value
            print(f"Basic Constraints: ca={bc.ca}, path_len={bc.path_length}")
        except Exception:
            print("Basic Constraints: NOT FOUND")
    
    if not os.path.exists(p12_path):
        print(f"ERROR: File {p12_path} not found.")
        return

    try:
        with open(p12_path, 'rb') as f:
            p12_data = f.read()
            
        # 1. Inspect using cryptography
        private_key, cert, chain = pkcs12.load_key_and_certificates(p12_data, password.encode())
        
        print("\n[Cryptography Inspection]")
        print(f"Subject: {cert.subject}")
        print(f"Issuer: {cert.issuer}")
        print(f"Serial: {cert.serial_number}")
        
        # Key Usage
        try:
            ku = cert.extensions.get_extension_for_class(x509.KeyUsage).value
            print(f"Key Usage: digital_signature={ku.digital_signature}, content_commitment={ku.content_commitment}, key_encipherment={ku.key_encipherment}")
        except x509.ExtensionNotFound:
            print("Key Usage: NOT FOUND")
            
        # Extended Key Usage
        try:
            eku = cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
            print(f"Extended Key Usage: {[oid._name for oid in eku]}")
        except x509.ExtensionNotFound:
            print("Extended Key Usage: NOT FOUND")

        # 2. Inspect using asn1crypto (what pyHanko uses)
        asn1_cert = asn1_x509.Certificate.load(cert.public_bytes(serialization.Encoding.DER))
        print("\n[asn1crypto Inspection]")
        
        ku_ext = asn1_cert.key_usage_value
        if ku_ext:
            print(f"Key Usage (native): {ku_ext.native}")
        else:
            print("Key Usage (native): NOT FOUND")
            
        eku_ext = asn1_cert.extended_key_usage_value
        if eku_ext:
            print(f"Extended Key Usage (native): {eku_ext.native}")
        else:
            print("Extended Key Usage (native): NOT FOUND")

        # 3. Test pyHanko Signer
        print("\n[pyHanko Test]")
        try:
            signer = signers.SimpleSigner.load_pkcs12(p12_path, passphrase=password.encode())
            print(f"SUCCESS: SimpleSigner.load_pkcs12 loaded successfully. Serial: {signer.signing_cert.serial_number}")
            
            # Check usages from signer object itself
            sign_cert = signer.signing_cert
            print(f"Signer Cert Key Usage: {sign_cert.key_usage_value.native}")
            
            # 4. Full PdfSigner test with ValidationContext (replicate x509_service.py)
            print("\n[pyHanko PdfSigner Test]")
            from pyhanko_certvalidator import ValidationContext
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            from pyhanko.pdf_utils.generic import pdf_name
            import io
            
            root_ca_path = "certs/root_ca.crt"
            if os.path.exists(root_ca_path):
                from cryptography import x509 as crypto_x509
                with open(root_ca_path, 'rb') as f:
                    root_ca_bytes = f.read()
                cert_crypt = crypto_x509.load_pem_x509_certificate(root_ca_bytes)
                root_der = cert_crypt.public_bytes(serialization.Encoding.DER)
                root_cert = asn1_x509.Certificate.load(root_der)
                vc = ValidationContext(trust_roots=[root_cert], allow_fetching=True)
                print("SUCCESS: ValidationContext initialized with Root CA.")
                
                async def test_pdf_sign():
                    try:
                        # Use an existing valid PDF
                        pdf_path = "storage/test_base.pdf"
                        if not os.path.exists(pdf_path):
                            print(f"ERROR: {pdf_path} not found for PDF test.")
                            return
                            
                        with open(pdf_path, 'rb') as f:
                            w = IncrementalPdfFileWriter(f)
                            sig_meta = signers.PdfSignatureMetadata(
                                field_name="Sig_Test",
                                validation_context=vc,
                                embed_validation_info=False,
                                signer_key_usage=None
                            )
                            pdf_signer = signers.PdfSigner(
                                signer=signer,
                                signature_meta=sig_meta
                            )
                            
                            out = io.BytesIO()
                            await pdf_signer.async_sign_pdf(w, output=out)
                            print("SUCCESS: PdfSigner.async_sign_pdf completed without error.")
                    except SigningError as e:
                        print(f"ERROR: PdfSigner SigningError: {e}")
                        import traceback
                        traceback.print_exc()
                        if e.__cause__:
                            print(f"  CAUSE: {type(e.__cause__).__name__}: {e.__cause__}")
                            # Recursive cause printing
                            curr = e.__cause__
                            while curr.__cause__:
                                curr = curr.__cause__
                                print(f"  ROOT CAUSE: {type(curr).__name__}: {curr}")
                    except Exception as e:
                        print(f"ERROR: PdfSigner unexpected error: {type(e).__name__}: {e}")
                        import traceback
                        traceback.print_exc()

                asyncio.run(test_pdf_sign())
            else:
                print("SKIPPED: Root CA not found for validation context test.")

        except SigningError as e:
            print(f"ERROR: pyHanko SigningError: {e}")
        except Exception as e:
            print(f"ERROR: Unexpected error during pyHanko test: {e}")
            import traceback
            traceback.print_exc()

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Import serialization here to avoid top-level issues if something is weird
    from cryptography.hazmat.primitives import serialization
    
    p12_path = "certs/signer.p12"
    # C-001 FIX: Password from environment, no hardcoded default
    password = os.environ.get("X509_P12_PASSWORD", "")
    if not password:
        print("WARNING: X509_P12_PASSWORD env var not set. Pass password as arg 2 or set env var.")
    
    if len(sys.argv) > 1:
        p12_path = sys.argv[1]
    if len(sys.argv) > 2:
        password = sys.argv[2]
        
    diagnose_p12(p12_path, password)
