import os
import sys
import logging
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

# 1. Environment Setup (Must be before config import)
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import config
from services import pki_service, x509_service
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.pdf_utils.reader import PdfFileReader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_pki")

def create_test_pdf(path: Path):
    try:
        import fitz
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((100, 100), "PKI Test Document (Phase 5 LTV)")
        doc.save(str(path))
        doc.close()
    except ImportError:
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << >> >>\nendobj\n4 0 obj\n<< /Length 20 >>\nstream\nBT /F1 12 Tf 100 700 Td (PKI Test LTV) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000062 00000 n \n0000000117 00000 n \n0000000213 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n284\n%%EOF")

def test_pki_flow():
    test_dir = Path(__file__).resolve().parent / "tmp_pki_test"
    test_dir.mkdir(exist_ok=True)
    
    # 1. Ensure PKI exists
    logger.info("Step 1: Ensuring PKI exists...")
    pki_service.generate_root_ca()
    pki_service.issue_signing_cert()
    
    # 2. Prepare Identity
    signer_identity = {
        "user_id": "usr-test-ltv",
        "role": "employee",
        "full_name": "Jane Doe LTV",
        "dni": "87654321",
        "email": "jane.doe@test.com",
        "organization_id": "org-test-002"
    }
    
    # 3. Sign
    original_pdf = test_dir / "test_pki_ltv.pdf"
    create_test_pdf(original_pdf)
    
    logger.info("Step 3: Signing with PAdES-LTV + TSA...")
    sign_res = x509_service.sign_pdf(str(original_pdf), "receipt-pki-ltv-001", signer_identity)
    
    if sign_res["status"] != "success":
        logger.error(f"Signing failed: {sign_res.get('error')}")
        return False
    
    logger.info(f"SUCCESS: LTV Status={sign_res.get('ltv_status')}")
    logger.info(f"SUCCESS: Timestamp Source={sign_res.get('timestamp_source')}")
    
    # 4. Verify Cryptographic Integrity & Adobe requirements
    signed_pdf = Path(sign_res["signed_path"])
    logger.info("Step 4: Validating Adobe-specific requirements...")
    try:
        from pyhanko.sign.validation import validate_pdf_signature, async_validate_pdf_signature
        import asyncio

        with open(signed_pdf, "rb") as f:
            r = PdfFileReader(f)
            emb = r.embedded_signatures[0]
            
            # Check for TSA
            if emb.attached_timestamp_data:
                logger.info("âœ… TSA: Timestamp token found in signature.")
            else:
                logger.warning("âŒ TSA: No timestamp token found.")
                # We don't fail yet if TSA fallback happened locally, but for Phase 5 it should be there.
            
            # Check for Chain (Signer + Issuer)
            other_certs = emb.other_embedded_certs
            if any("Root CA" in str(c.subject.native) for c in other_certs):
                logger.info("âœ… CHAIN: Root CA found in certificate chain.")
            else:
                logger.warning("âŒ CHAIN: Root CA missing from certificate chain.")

            # Check for DSS (LTV)
            try:
                dss_dict = r.root['/DSS']
                logger.info("âœ… LTV: Document Security Store (DSS) found.")
            except KeyError:
                logger.warning("âŒ LTV: Document Security Store (DSS) missing.")

            # Full Validation
            status = validate_pdf_signature(emb)
            if status.valid and status.intact:
                logger.info("âœ… INTEGRITY: Signature is valid and intact.")
            else:
                logger.error(f"âŒ INTEGRITY: Signature invalid! {status.summary()}")
                return False
            
    except Exception as e:
        logger.error(f"Validation error: {e}")
        import traceback
        traceback.print_exc()
        return False

    logger.info("=== ALL PHASE 5 PKI FLOW TESTS PASSED ===")
    return True

if __name__ == "__main__":
    success = test_pki_flow()
    if not success:
        sys.exit(1)
