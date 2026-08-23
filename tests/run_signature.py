import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# Set up logging to file and console
log_path = BASE_DIR / "signature_flow.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_path, mode="w"),
        logging.StreamHandler(sys.stdout)
    ]
)

import config
from services import x509_service

def create_sample_pdf(path: Path):
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((100, 100), "Sample Document for Signature (LTV Validation)")
    doc.save(str(path))
    doc.close()

if __name__ == "__main__":
    logger = logging.getLogger("signature_flow")
    logger.info("Generating a sample document...")
    
    input_pdf = BASE_DIR / "sample_doc.pdf"
    create_sample_pdf(input_pdf)
    
    identity = {
        "user_id": "usr-123",
        "role": "employee",
        "full_name": "Test User",
        "organization_id": "org-321"
    }
    
    logger.info("Executing X509 Digital Signature Flow with LTV...")
    try:
        result = x509_service.sign_pdf(str(input_pdf), "receipt-test-123", identity)
        if result["status"] == "success":
            logger.info("=== SIGNATURE SUCCESS ===")
            logger.info(f"Target file: {result['signed_path']}")
            logger.info(f"Algorithm: {result['signature_algorithm']}")
            logger.info(f"Fingerprint: {result['fingerprint']}")
            logger.info(f"LTV Status: {result['ltv_status']}")
            logger.info(f"TSA Applied: {result['timestamp_source']}")
            logger.info(f"OCSP Validation: {result['ocsp_status']}")
        else:
            logger.error("=== SIGNATURE FAILED ===")
            logger.error(f"Error details: {result.get('error')}")
    except Exception as e:
        logger.exception("Catastrophic failure in signature flow")
