import os
from datetime import datetime
from PIL import Image
from modules.signature import SignatureEngine

def generate_test_image():
    img = Image.new("RGBA", (150, 50), color=(255, 255, 255, 0))
    img.save("storage/test_sig.png", "PNG")
    with open("storage/test_sig.png", "rb") as f:
        return f.read()

def generate_test_pdf():
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Testing Signature Seal", fontsize=12)
    pdf_path = "storage/test_blank.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path

def main():
    engine = SignatureEngine()
    
    # Ensure dirs exist
    os.makedirs("storage", exist_ok=True)
    
    # Create blank pdf and mock signature png
    pdf_path = generate_test_pdf()
    sig_bytes = generate_test_image()
    
    output_path = "storage/test_sealed.pdf"
    
    print("Stamping signature...")
    engine.stamp_signature_from_bytes(
        pdf_path=pdf_path,
        signature_bytes=sig_bytes,
        role="employee",
        signer_name="John Doe",
        timestamp=datetime.now(),
        output_path=output_path
    )
    
    print(f"Success! Generated {output_path}")

if __name__ == "__main__":
    main()
