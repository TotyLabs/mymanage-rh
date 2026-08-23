"""
Diagnostic: Dump the exact layout of signature-relevant elements on the receipt page.
Shows text blocks, drawing lines, and rectangles in the signature zone.
"""
import os, sys
os.environ['DATABASE_URL'] = 'postgresql://x:x@localhost/x'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fitz

pdf_path = os.path.join(os.path.dirname(__file__), "test.pdf")
doc = fitz.open(pdf_path)

# Check page 0 (first page with receipts)
page = doc.load_page(0)
pw = page.rect.width
ph = page.rect.height
print(f"Page size: {pw:.0f} x {ph:.0f}")
print(f"Mid X: {pw/2:.0f}")
print()

# Only show bottom 40% of the page (signature area)
zone_y = ph * 0.6
print(f"=== TEXT BLOCKS in bottom 40% (y > {zone_y:.0f}) ===")
words = page.get_text("words")
for w in sorted(words, key=lambda x: (x[1], x[0])):
    x0, y0, x1, y1, text = w[:5]
    if y0 < zone_y:
        continue
    side = "LEFT" if (x0 + x1) / 2 < pw / 2 else "RIGHT"
    print(f"  [{side}] ({x0:.1f}, {y0:.1f}) - ({x1:.1f}, {y1:.1f}) [{x1-x0:.0f}x{y1-y0:.0f}] \"{text}\"")

print(f"\n=== DRAWINGS (rects/lines) in bottom 40% ===")
for draw in page.get_drawings():
    r = draw["rect"]
    if r.y0 < zone_y:
        continue
    side = "LEFT" if (r.x0 + r.x1) / 2 < pw / 2 else "RIGHT"
    
    for item in draw["items"]:
        if item[0] == "l":  # line
            p1, p2 = item[1], item[2]
            is_horiz = abs(p1.y - p2.y) <= 2
            length = abs(p2.x - p1.x) if is_horiz else abs(p2.y - p1.y)
            kind = "HORIZ" if is_horiz else "VERT"
            print(f"  [{side}] LINE {kind} ({p1.x:.1f},{p1.y:.1f})-({p2.x:.1f},{p2.y:.1f}) len={length:.0f}")
        elif item[0] == "re":  # rect
            ri = item[1]
            print(f"  [{side}] RECT ({ri.x0:.1f},{ri.y0:.1f})-({ri.x1:.1f},{ri.y1:.1f}) [{ri.width:.0f}x{ri.height:.0f}]")
    
    # Also show the overall rect
    if r.width > 50 and r.height > 15:
        print(f"  [{side}] DRAW_RECT ({r.x0:.1f},{r.y0:.1f})-({r.x1:.1f},{r.y1:.1f}) [{r.width:.0f}x{r.height:.0f}] *** POTENTIAL BOX ***")

print(f"\n=== SPECIFIC SEARCH: 'firma' keywords ===")
for w in words:
    text = w[4].lower()
    if "firma" in text or "empleado" in text or "empleador" in text or "observ" in text:
        x0, y0, x1, y1 = w[:4]
        side = "LEFT" if (x0 + x1) / 2 < pw / 2 else "RIGHT"
        print(f"  [{side}] ({x0:.1f}, {y0:.1f}) - ({x1:.1f}, {y1:.1f}) \"{w[4]}\"")

# Check what the detection engine finds
print(f"\n=== ENGINE DETECTION ===")
from modules.signature import SignatureEngine, SIGNATURE_CONTRACT
engine = SignatureEngine()

for role in ["employer", "employee"]:
    positions = engine.detect_signature_positions(page, role)
    if positions:
        pos = positions[0]
        print(f"\n{role}:")
        print(f"  mode: {pos.get('mode')}")
        print(f"  kind: {pos.get('anchor_kind')}")
        print(f"  score: {pos.get('score', 0):.0f}")
        print(f"  center_x: {pos.get('target_x_center', 0):.1f}")
        print(f"  baseline_y: {pos.get('target_baseline_y', 0):.1f}")
        if pos.get('bbox'):
            print(f"  label bbox: {pos['bbox']}")
        if pos.get('box_bbox'):
            print(f"  box bbox: {pos['box_bbox']}")
        if pos.get('line_bbox'):
            print(f"  line bbox: {pos['line_bbox']}")
        print(f"  text: {pos.get('text', '')}")
        
        # Compute where it would actually stamp 
        contract = SIGNATURE_CONTRACT.copy()
        sig_rect = engine._compute_signature_rect(pos, contract)
        print(f"  STAMP RECT: ({sig_rect.x0:.1f}, {sig_rect.y0:.1f}) - ({sig_rect.x1:.1f}, {sig_rect.y1:.1f})")
    else:
        print(f"\n{role}: NO POSITION FOUND")

doc.close()
