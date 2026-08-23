import inspect
from pyhanko.sign import signers
sig = inspect.signature(signers.SimpleSigner.load_pkcs12)
print("Signature:", sig)
