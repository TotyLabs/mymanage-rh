import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.getcwd())

from dotenv import load_dotenv
load_dotenv()

from modules.signature import get_signature_engine
import fitz

def test_anchor_detection():
    engine = get_signature_engine()
    
    # Use a sample PDF from storage
    sample_pdf = "storage/receipts/receipt_37f2aa33-af34-4fa6-83f4-8629f3ea1ea8_1.pdf"
    if not os.path.exists(sample_pdf):
        print(f"Sample PDF not found: {sample_pdf}")
        return

    doc = fitz.open(sample_pdf)
    page = doc[0]
    
    print(f"Testing PDF: {sample_pdf}")
    print("-" * 30)
    
    for role in ["employer", "employee"]:
        print(f"Detecting position for: {role}")
        pos = engine.detect_signature_position(page, role)
        if pos:
            print(f"  SUCCESS: Found at x={pos['x']:.2f}, y={pos['y']:.2f}")
        else:
            print("  FAILED: No anchor found, using fallback (if any)")
    
    doc.close()

if __name__ == "__main__":
    test_anchor_detection()
