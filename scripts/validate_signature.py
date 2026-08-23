from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.pdf_utils.reader import PdfFileReader

with open("Viana__Julio_Cesar_e2747fed_47.pdf", "rb") as f:
    reader = PdfFileReader(f)
    sig = reader.embedded_signatures[0]

    status = validate_pdf_signature(sig)

    print(status.pretty_print_details())
