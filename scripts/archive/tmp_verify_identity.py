import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from payroll_core import normalize_dni, validate_dni
from services.legajo.cuil_validator import validate_cuil, normalize_cuil

def test_normalization():
    print("Testing Normalization...")
    # Standard
    assert normalize_dni("12.345.678") == "12345678"
    # Leading Zero
    assert normalize_dni("08.123.456") == "08123456"
    # Guard against garbage
    try:
        normalize_dni("123456789012")
        print("FAIL: normalize_dni didn't catch garbage")
    except Exception as e:
        print(f"PASS: Caught garbage: {e}")

def test_cuil_harmonization():
    print("Testing CUIL Harmonization...")
    # standard
    v, m = validate_cuil("20-12345678-3")
    assert v is True
    # with spaces/dots
    v, m = validate_cuil("20 12345678.3")
    assert v is True, f"Failed spaces/dots: {m}"
    
    assert normalize_cuil("20-12345678-3") == "20123456783"

if __name__ == "__main__":
    try:
        test_normalization()
        test_cuil_harmonization()
        print("\nUnit Tests Passed Locally!")
    except AssertionError as e:
        print(f"\nAssertion error: {e}")
    except Exception as e:
        print(f"\nError: {e}")
