"""
Diagnostic script: Validates the full signature rendering pipeline
after the FIX-PRINT changes (stroke thickening + larger stamp rect).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageChops, ImageFilter
from io import BytesIO

def simulate_canvas_signature():
    """Create a synthetic canvas signature similar to what the browser produces."""
    img = Image.new("RGBA", (620, 200), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    points = [
        (50, 120), (80, 80), (110, 130), (140, 60), (170, 110),
        (200, 70), (230, 120), (260, 90), (300, 100), (340, 80),
        (380, 110), (420, 75), (460, 120), (500, 90), (540, 130)
    ]
    for i in range(len(points) - 1):
        draw.line([points[i], points[i+1]], fill=(15, 23, 42, 255), width=3)
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_prepare_signature_image(image_bytes):
    """Simulate the FIXED _prepare_signature_image pipeline."""
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    
    # 1. White-to-Alpha (threshold 230)
    datas = img.getdata()
    new_data = []
    visible_count = 0
    for item in datas:
        if item[0] > 230 and item[1] > 230 and item[2] > 230:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
            visible_count += 1
    img.putdata(new_data)
    
    total_pixels = img.size[0] * img.size[1]
    ink_ratio = visible_count / max(1, total_pixels)
    
    print(f"  White-to-Alpha: {visible_count} visible pixels ({ink_ratio*100:.2f}% ink)")
    
    # 2. Stroke Thickening
    if ink_ratio < 0.10 and img.size[0] > 200:
        alpha = img.split()[3]
        ink_mask = alpha.point(lambda p: 255 if p > 128 else 0)
        dilated = ink_mask.filter(ImageFilter.MaxFilter(size=5))
        
        ink_layer = Image.new("RGBA", img.size, (15, 23, 42, 255))
        ink_layer.putalpha(dilated)
        ink_layer.paste(img, mask=img.split()[3])
        img = ink_layer
        
        # Count new visible pixels
        new_visible = sum(1 for p in img.getdata() if p[3] > 0)
        print(f"  Stroke Thickening: {visible_count} -> {new_visible} visible pixels ({new_visible/total_pixels*100:.2f}%)")
        print(f"  Thickening factor: {new_visible/max(1,visible_count):.1f}x")
    
    # 3. Autocrop
    bg = Image.new(img.mode, img.size, (255, 255, 255, 0))
    diff = ImageChops.difference(img, bg)
    diff = ImageChops.add(diff, diff, 1.5, -50)
    bbox = diff.getbbox()
    
    if bbox:
        bbox = (max(0, bbox[0]-6), max(0, bbox[1]-6), 
                min(img.size[0], bbox[2]+6), min(img.size[1], bbox[3]+6))
        img = img.crop(bbox)
    
    print(f"  Autocrop: {img.size}")
    
    out_io = BytesIO()
    img.save(out_io, format="PNG")
    return out_io.getvalue(), img


def compare_stamp_sizes():
    """Compare OLD vs NEW stamp sizes."""
    print("\n" + "=" * 60)
    print("STAMP SIZE COMPARISON")
    print("=" * 60)
    
    configs = [
        ("OLD (broken)", 90, 45),
        ("NEW (fixed)", 160, 65),
    ]
    
    for name, w, h in configs:
        scale_x = w / 620
        scale_y = h / 200
        min_scale = min(scale_x, scale_y)
        eff_stroke = 3 * min_scale
        
        print(f"\n  [{name}]")
        print(f"    Stamp: {w}x{h} pt = {w/72*25.4:.1f}x{h/72*25.4:.1f} mm")
        print(f"    Scale: X={scale_x:.3f}, Y={scale_y:.3f}")
        print(f"    Effective stroke (3px canvas): {eff_stroke:.2f} pt = {eff_stroke/72*25.4:.2f} mm")
        
        # With thickening (MaxFilter 5 = +2px each side = 7px effective)
        eff_thick = 7 * min_scale
        print(f"    After thickening (7px effective): {eff_thick:.2f} pt = {eff_thick/72*25.4:.2f} mm")
        
        if eff_stroke < 0.5:
            print(f"    STATUS: INVISIBLE at print (sub-pixel)")
        elif eff_stroke < 1.0:
            print(f"    STATUS: BARELY VISIBLE")
        else:
            print(f"    STATUS: CLEARLY VISIBLE")


def test_with_real_pdf():
    """Test signature detection on the actual test PDF if available."""
    test_pdf = os.path.join(os.path.dirname(__file__), "test.pdf")
    if not os.path.exists(test_pdf):
        print("\n[SKIP] test.pdf not found")
        return
    
    try:
        import fitz
    except ImportError:
        print("\n[SKIP] PyMuPDF not available")
        return
    
    print("\n" + "=" * 60)
    print("REAL PDF TEST")
    print("=" * 60)
    
    try:
        # Need config to be importable
        from modules.signature import SignatureEngine
        engine = SignatureEngine()
        
        doc = fitz.open(test_pdf)
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            
            for role in ["employer", "employee"]:
                positions = engine.detect_signature_positions(page, role)
                if positions:
                    pos = positions[0]
                    print(f"\n  Page {page_num}, Role: {role}")
                    print(f"    Mode: {pos.get('mode')}")
                    print(f"    Kind: {pos.get('anchor_kind')}")
                    print(f"    Score: {pos.get('score', 0):.0f}")
                    print(f"    Center X: {pos.get('target_x_center', 0):.1f}")
                    print(f"    Baseline Y: {pos.get('target_baseline_y', 0):.1f}")
                    
                    if pos.get('box_bbox'):
                        box = pos['box_bbox']
                        print(f"    Box: {box}")
                else:
                    print(f"\n  Page {page_num}, Role: {role}: NO POSITION FOUND")
        
        doc.close()
    except Exception as e:
        print(f"\n  Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("SIGNATURE RENDERING DIAGNOSTIC (POST-FIX)")
    print("=" * 60)
    
    print("\n--- Canvas Simulation ---")
    raw = simulate_canvas_signature()
    print(f"  Canvas PNG: {len(raw)} bytes")
    
    print("\n--- Fixed Pipeline ---")
    result_bytes, result_img = run_prepare_signature_image(raw)
    print(f"  Output PNG: {len(result_bytes)} bytes")
    
    compare_stamp_sizes()
    test_with_real_pdf()
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
