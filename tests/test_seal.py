import os
from dotenv import load_dotenv
load_dotenv()

from modules.signature import SignatureEngine
from datetime import datetime, timezone
from pathlib import Path

def test_seal():
    engine = SignatureEngine()
    
    # Paths
    pdf_path = "test.pdf.pdf"
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found. Create a dummy pdf first.")
        return
        
    sig_path = "C:/Users/lenov/.gemini/antigravity/brain/d642190f-9f07-42c9-9dcb-c76c075d5c39/test_logo_1773702776994.png"
    if not os.path.exists(sig_path):
        print(f"Error: {sig_path} not found.")
        return

    with open(sig_path, "rb") as f:
        sig_bytes = f.read()

    output_pdf = "test_signed_seal.pdf"
    
    # Mock data
    ctx = {
        "signer_name": "Cardozo Garcia Jose",
        "signer_tax_id": "20-12345678-9",
        "verification_id": "FES-20260315-0FF4",
        "verification_url": "https://verify.mymanagerh.com/v/FES-20260315-0FF4"
    }

    print("Stamping seal...")
    result = engine.stamp_signature_from_bytes(
        pdf_path=pdf_path,
        signature_bytes=sig_bytes,
        role="employee",
        output_path=output_pdf,
        signer_name=ctx["signer_name"],
        signer_tax_id=ctx["signer_tax_id"],
        timestamp=datetime.now(timezone.utc),
        verification_url=ctx["verification_url"]
    )
    
    print(f"Result: {result['signed_pdf_path']}")
    print(f"Signature ID: {result['signature_id']}")
    print("Test complete. Please check test_signed_seal.pdf manually.")

if __name__ == "__main__":
    test_seal()
