
import os
from payroll_core import ALLOWED_STORAGE_DIR

print(f"ALLOWED_STORAGE_DIR: '{ALLOWED_STORAGE_DIR}'")

# Test a fake path
test_path = os.path.abspath(os.path.join(ALLOWED_STORAGE_DIR, "test.pdf"))
print(f"Test Path: '{test_path}'")
print(f"Starts with? {test_path.startswith(ALLOWED_STORAGE_DIR)}")

# Test with different case drive letter
if ALLOWED_STORAGE_DIR and len(ALLOWED_STORAGE_DIR) > 1:
    wrong_case = ALLOWED_STORAGE_DIR[0].swapcase() + ALLOWED_STORAGE_DIR[1:]
    print(f"Wrong Case: '{wrong_case}'")
    print(f"Starts with (wrong case)? {test_path.startswith(wrong_case)}")
