import fitz
doc = fitz.open("test.pdf")
text = doc[0].get_text()
with open("pdf_page1.txt", "w", encoding="utf-8") as f:
    f.write(text)
