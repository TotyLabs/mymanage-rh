import os
from pathlib import Path

certs_dir = Path(r'c:\Users\lenov\OneDrive\Desktop\dircom-payroll\certs')
print(f"Inspecting: {certs_dir}")

files = os.listdir(certs_dir)
for f in files:
    p = certs_dir / f
    status = "???"
    try:
        exists = p.exists()
        is_file = p.is_file()
        size = p.stat().st_size if exists else -1
        print(f"FILE: {f!r} | EXISTS: {exists} | ISFILE: {is_file} | SIZE: {size}")
    except Exception as e:
        print(f"FILE: {f!r} | ERROR: {e}")
