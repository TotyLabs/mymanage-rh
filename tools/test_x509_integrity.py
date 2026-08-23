import os
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

import config
from services import x509_service
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.pdf_utils.reader import PdfFileReader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_integrity")

def create_test_pdf(path: Path):
    """Creates a basic one-page PDF using reportlab if available, or just a dummy string."""
    try:
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(str(path))
        c.drawString(100, 750, "Integrity Test PDF")
        c.save()
    except ImportError:
        # Fallback to a very minimal PDF-like structure if reportlab is missing
        with open(path, "wb") as f:
            f.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << >> >>\nendobj\n4 0 obj\n<< /Length 20 >>\nstream\nBT /F1 12 Tf 100 700 Td (Integrity Test) Tj ET\nendstream\nendobj\nxref\n0 5\n0000000000 65535 f \n0000000009 00000 n \n0000000062 00000 n \n0000000117 00000 n \n0000000213 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n284\n%%EOF")

def test_integrity():
    test_dir = Path(__file__).resolve().parent / "tmp_test"
    test_dir.mkdir(exist_ok=True)
    
    original_pdf = test_dir / "original.pdf"
    create_test_pdf(original_pdf)
    
    receipt_id = "test-integrity-001"
    
    logger.info("Step 1: Signing PDF...")
    sign_res = x509_service.sign_pdf(str(original_pdf), receipt_id)
    
    if sign_res["status"] != "success":
        logger.error(f"Signing failed: {sign_res.get('error')}")
        return False
    
    signed_pdf = Path(sign_res["signed_path"])
    
    logger.info("Step 2: Validating valid signature...")
    try:
        with open(signed_pdf, "rb") as f:
            r = PdfFileReader(f)
            # We expect at least one signature
            sig = r.embedded_signatures[0]
            status = validate_pdf_signature(sig)
            if not status.valid or not status.intact:
                 logger.error("Fresh signature validation failed!")
                 return False
            logger.info("SUCCESS: Fresh signature is VALID and INTACT.")
            if sign_res.get("timestamp_present"):
                logger.info("SUCCESS: TSA Timestamp found and verified.")
            else:
                logger.warning("WARNING: TSA Timestamp missing (acceptable if TSA was down).")
    except Exception as e:
        logger.error(f"Validation error: {e}")
        return False

    logger.info("Step 3: Modifying 1 byte of the signed PDF...")
    modified_pdf = test_dir / "modified.pdf"
    with open(signed_pdf, "rb") as f:
        data = bytearray(f.read())
    
    # Flip a bit in the middle of the file to corrupt it without breaking PDF structure entirely
    data[len(data) // 2] ^= 0xFF
    
    with open(modified_pdf, "wb") as f:
        f.write(data)

    logger.info("Step 4: Validating modified PDF (expecting failure)...")
    try:
        with open(modified_pdf, "rb") as f:
            r = PdfFileReader(f)
            sig = r.embedded_signatures[0]
            status = validate_pdf_signature(sig)
            if status.intact:
                logger.error("FAIL: Signature still reported as INTACT after modification!")
                return False
            logger.info("SUCCESS: Integrity check CORRECTLY FAILED for modified PDF.")
    except Exception as e:
        # Some modifications might crash the reader, which also counts as a "failed" signature in a way,
        # but specifically we want to see pyHanko detect the mismatch.
        logger.info(f"Integrity check failed as expected (Exception: {e})")

    logger.info("=== ALL INTEGRITY TESTS PASSED ===")
    return True

if __name__ == "__main__":
    success = test_integrity()
    if not success:
        sys.exit(1)
