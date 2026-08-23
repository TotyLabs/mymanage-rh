
import os

path = r'c:\Users\LENOVO\Desktop\MyManageRH-Payroll\modules\signature.py'

with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

count = 0
for i, line in enumerate(lines):
    if '"""' in line:
        occ = line.count('"""')
        count += occ
        print(f"Line {i+1}: contains {occ} triple-quotes. Cumulative: {count}")

if count % 2 != 0:
    print("\nUNBALANCED TRIPLE QUOTES DETECTED!")
