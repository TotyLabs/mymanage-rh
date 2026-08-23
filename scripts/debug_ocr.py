import fitz
import re
import os
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("debug")

DNI_PATTERN = re.compile(r"(?:\D|^)(\d{7,8})(?:\D|$)") # 7-8 digits not part of larger number
CUIL_PATTERN = re.compile(r"(\d{2}[-.\s]?\d{7,8}[-.\s]?\d)")
DNI_CONTEXT_PATTERN = re.compile(r"(DNI|DOCUMENTO|DOC|D\.N\.I|CUIL|CUIT)\s*[:.-]?\s*(\d{7,8})", re.IGNORECASE)

def normalize_dni(dni: str) -> str:
    if not dni:
        return ""
    clean = re.sub(r"\D", "", str(dni))
    if len(clean) == 11:
        return clean[2:10]
    return clean

def extract_dni_from_page(page):
    blocks = page.get_text("blocks")
    candidates = []
    all_text = page.get_text().strip()
    if not all_text:
        return "SCAN_REQUIRED"
    for b in blocks:
        y0 = b[1]
        raw_text = b[4].strip()
        cuil_match = CUIL_PATTERN.search(raw_text)
        dni = None
        score = 0
        if cuil_match:
            dni = normalize_dni(cuil_match.group(1))
            score += 60
        else:
            match = DNI_CONTEXT_PATTERN.search(raw_text)
            if match:
                dni = normalize_dni(match.group(2))
                score += 50
            else:
                match = DNI_PATTERN.search(raw_text)
                if match:
                    dni = normalize_dni(match.group(1))
                    score += 10
        if dni:
            if y0 < 100:
                score -= 50
            if "\n" in raw_text:
                score += 25
            candidates.append({"dni": dni, "score": score, "text": raw_text})
    if not candidates:
        return None
    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]
    if best["score"] < 0 and len(candidates) > 1:
        if candidates[1]["score"] > best["score"]:
             best = candidates[1]
    return best["dni"]

def debug_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    print(f"PDF: {pdf_path}")
    print(f"Pages: {len(doc)}")
    
    for i in range(min(3, len(doc))):
        page = doc[i]
        dni = extract_dni_from_page(page)
        print(f"Page {i+1} Match: {dni}")

if __name__ == "__main__":
    pdf = "c:/Users/lenov/OneDrive/Desktop/dircom-payroll/storage/batches/batch_20260225_174819_test.pdf"
    if os.path.exists(pdf):
        debug_pdf(pdf)
    else:
        print("File not found.")
