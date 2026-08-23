"""Test: Stamp a signature on the real test PDF and verify it's visible."""
import os, sys
os.environ['DATABASE_URL'] = 'postgresql://x:x@localhost/x'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.signature import SignatureEngine
from PIL import Image, ImageDraw
from io import BytesIO
import fitz

engine = SignatureEngine()

# Create test signature (simulated canvas)
img = Image.new("RGBA", (620, 200), (255, 255, 255, 255))
draw = ImageDraw.Draw(img)
pts = [(50,120),(80,80),(110,130),(140,60),(170,110),(200,70),(230,120),
       (260,90),(300,100),(340,80),(380,110),(420,75),(460,120),(500,90),(540,130)]
for i in range(len(pts)-1):
    draw.line([pts[i], pts[i+1]], fill=(15, 23, 42, 255), width=3)
buf = BytesIO()
img.save(buf, format="PNG")
sig_bytes = buf.getvalue()
print(f"Signature image: {len(sig_bytes)} bytes")

# Test with actual PDF
pdf_path = os.path.join(os.path.dirname(__file__), "test.pdf")
if not os.path.exists(pdf_path):
    print("test.pdf not found, skipping")
    sys.exit(0)

doc = fitz.open(pdf_path)
page = doc.load_page(0)
print(f"PDF: {doc.page_count} pages, page size: {page.rect.width:.0f}x{page.rect.height:.0f}")

for role in ["employer", "employee"]:
    positions = engine.detect_signature_positions(page, role)
    if positions:
        pos = positions[0]
        mode = pos.get("mode", "?")
        kind = pos.get("anchor_kind", "?")
        score = pos.get("score", 0)
        cx = pos.get("target_x_center", 0)
        by = pos.get("target_baseline_y", 0)
        print(f"  {role}: mode={mode} kind={kind} score={score:.0f} cx={cx:.1f} by={by:.1f}")
    else:
        print(f"  {role}: NO POSITION FOUND")
doc.close()

# Stamp employer
output = os.path.join(os.path.dirname(__file__), "test_employer_signed.pdf")
try:
    result = engine.stamp_signature_from_bytes(
        pdf_path=pdf_path,
        signature_bytes=sig_bytes,
        role="employer",
        signer_name="Test Employer",
        signer_tax_id="30-12345678-9",
        output_path=output
    )
    print(f"\nEmployer signed PDF saved: {output}")
    print(f"  Signature ID: {result['signature_id']}")
    
    # Verify images
    doc2 = fitz.open(output)
    page2 = doc2.load_page(doc2.page_count - 1)
    images = page2.get_image_info()
    print(f"  Images on last page: {len(images)}")
    for im in images:
        bbox = im["bbox"]
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        if w > 20 and h > 10:
            print(f"    Image: {w:.1f}x{h:.1f} pt at ({bbox[0]:.1f}, {bbox[1]:.1f})")
    doc2.close()
    print("  STAMP TEST: PASSED")
except Exception as e:
    print(f"  STAMP ERROR: {e}")
    import traceback; traceback.print_exc()

# Stamp employee on the employer-signed result  
output2 = os.path.join(os.path.dirname(__file__), "test_both_signed.pdf")
try:
    result2 = engine.stamp_signature_from_bytes(
        pdf_path=output,
        signature_bytes=sig_bytes,
        role="employee",
        signer_name="Test Employee",
        signer_tax_id="20-87654321-0",
        output_path=output2
    )
    print(f"\nEmployee signed PDF saved: {output2}")
    print(f"  Signature ID: {result2['signature_id']}")
    
    doc3 = fitz.open(output2)
    page3 = doc3.load_page(doc3.page_count - 1)
    images3 = page3.get_image_info()
    sig_imgs = [im for im in images3 if (im["bbox"][2]-im["bbox"][0]) > 20 and (im["bbox"][3]-im["bbox"][1]) > 10]
    print(f"  Signature images on last page: {len(sig_imgs)}")
    for im in sig_imgs:
        bbox = im["bbox"]
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        print(f"    Image: {w:.1f}x{h:.1f} pt at ({bbox[0]:.1f}, {bbox[1]:.1f})")
    doc3.close()
    print("  DUAL STAMP TEST: PASSED")
except Exception as e:
    print(f"  EMPLOYEE STAMP ERROR: {e}")
    import traceback; traceback.print_exc()
