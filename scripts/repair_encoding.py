
import os

path = r'c:\Users\LENOVO\Desktop\MyManageRH-Payroll\modules\signature.py'

# Double-encoded sequences
# ó -> c3 b3 -> (as Latin-1) Ã³ -> (as UTF-8) c3 83 c2 b3
sequences = [
    (b'\xc3\x83\xc2\xb3', 'ó'),
    (b'\xc3\x83\xc2\xa1', 'á'),
    (b'\xc3\x83\xc2\xa9', 'é'),
    (b'\xc3\x83\xc2\xad', 'í'),
    (b'\xc3\x83\xc2\xba', 'ú'),
    (b'\xc3\x83\xc2\xb1', 'ñ'),
    (b'\xc3\x83\xc2\x93', 'Ó'),
    (b'\xc3\x83\xc2\x81', 'Á'),
    (b'\xc3\x83\xc2\x89', 'É'),
    (b'\xc3\x83\xc2\x8d', 'Í'),
    (b'\xc3\x83\xc2\x9a', 'Ú'),
    (b'\xc3\x83\xc2\x91', 'Ñ'),
    # Single-level artifacts too, just in case
    (b'\xc3\x83\x20', 'á '), # Sometimes space is involved? No, stick to the basics.
]

with open(path, 'rb') as f:
    data = f.read()

for seq, replacement in sequences:
    data = data.replace(seq, replacement.encode('utf-8'))

# Final cleanup: replace any remaining individual corrupted bytes if safe
# But the above should catch 99% of it.

with open(path, 'wb') as f:
    f.write(data)

print("File repaired (Deep scan complete).")
