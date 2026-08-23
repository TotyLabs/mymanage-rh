import fitz

from services.receipt_service import extract_single_page_pdf_bytes


def test_extract_single_page_pdf_bytes_returns_pdf_bytes():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello")

    page_bytes = extract_single_page_pdf_bytes(doc, 0)

    assert page_bytes.startswith(b"%PDF")
    assert len(page_bytes) > 0
