import re
import os
import pytesseract
from PIL import Image
import io
from datetime import datetime
from payroll_core import logger

# GAP-L2-3: Evita bombas de descompresiÃ³n (OOM DoS) limitando a ~10MP
Image.MAX_IMAGE_PIXELS = 10000000

# Windows Tesseract path configuration
if os.name == 'nt':
    tesseract_paths = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Tesseract-OCR", "tesseract.exe")
    ]
    for path in tesseract_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break

def extract_dni_data(image_bytes: bytes) -> dict:
    """
    Extracts typical Argentinian DNI fields (Front) using OCR and Regex.
    Expected fields: DNI number, First Name, Last Name, Birth Date.
    """
    try:
        image = Image.open(io.BytesIO(image_bytes))
        
        # Pre-processing: Convert to grayscale
        gray_image = image.convert('L')
        
        # OCR extraction
        # Using config to improve results for Argentinian DNI if possible
        raw_text = pytesseract.image_to_string(gray_image, lang='spa+eng')
        
        logger.info(f"OCR Raw Output: {raw_text[:200]}...")

        data = {
            "dni": None,
            "first_name": None,
            "last_name": None,
            "birth_date": None
        }

        # Regex patterns
        # DNI: Look for numbers between 7 and 8 digits, maybe with dots
        dni_match = re.search(r"(\d{1,2}[\.\s]?\d{3}[\.\s]?\d{3})", raw_text)
        if dni_match:
            data["dni"] = re.sub(r"\D", "", dni_match.group(1))

        # Birth Date: DD/MM/YYYY or DD-MM-YYYY
        dob_match = re.search(r"(\d{2}[/\-]\d{2}[/\-]\d{4})", raw_text)
        if dob_match:
            try:
                # Normalize to YYYY-MM-DD
                raw_dob = dob_match.group(1).replace("-", "/")
                dt = datetime.strptime(raw_dob, "%d/%m/%Y")
                data["birth_date"] = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # Names: This is harder. Look for lines in uppercase.
        # Usually DNI has "APELLIDO/SURNAME" then the value, then "NOMBRE/NAMES" then the value.
        lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
        
        for i, line in enumerate(lines):
            upper_line = line.upper()
            if "APELLIDO" in upper_line or "SURNAME" in upper_line:
                if i + 1 < len(lines):
                    data["last_name"] = lines[i+1].split()[0].upper() # Take first word to avoid noise
            if "NOMBRE" in upper_line or "NAME" in upper_line:
                if i + 1 < len(lines):
                    # Names might be multiple words
                    data["first_name"] = lines[i+1].upper()

        return data

    except Exception as e:
        logger.exception("OCR_PROCESSING_ERROR")
        return {
            "dni": None,
            "first_name": None,
            "last_name": None,
            "birth_date": None,
            "error": str(e)
        }
