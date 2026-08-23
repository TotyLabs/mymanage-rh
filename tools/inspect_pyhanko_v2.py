import inspect
from pyhanko.sign import signers

print("PdfSigner.__init__ signature:")
print(inspect.signature(signers.PdfSigner.__init__))

print("\nPdfSigner.sign_pdf signature:")
print(inspect.signature(signers.PdfSigner.sign_pdf))

print("\nIncrementalPdfFileWriter.__init__ signature:")
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
print(inspect.signature(IncrementalPdfFileWriter.__init__))
