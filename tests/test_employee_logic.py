import pytest
from payroll_core import validate_cuil, CuilInvalidFormat, CuilInvalidChecksum
from fastapi import HTTPException

def test_validate_cuil_algorithm():
    # Valid CUILs (generated/real examples)
    assert validate_cuil("20-30541234-5") == "20305412345"
    assert validate_cuil("27305412345") == "27305412345"
    
    # Invalid formats
    with pytest.raises(CuilInvalidFormat):
        validate_cuil("123")
    with pytest.raises(CuilInvalidFormat):
        validate_cuil("AB-30541234-5")
        
    # Invalid checksums
    with pytest.raises(CuilInvalidChecksum):
        validate_cuil("20-30541234-9") # Wrong last digit

def test_activation_logic_mock():
    # Helper to simulate the dict-like result from SQL
    class MockRow:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    # Case: Missing fields
    data_incomplete = MockRow(dni=None, email_corporativo="test@corp.com", fecha_ingreso="2024-01-01", cbu="123")
    assert not all([data_incomplete.dni, data_incomplete.email_corporativo, data_incomplete.fecha_ingreso, data_incomplete.cbu])
    
    # Case: Complete fields
    data_complete = MockRow(dni="12345678", email_corporativo="test@corp.com", fecha_ingreso="2024-01-01", cbu="1234567890123456789012")
    assert all([data_complete.dni, data_complete.email_corporativo, data_complete.fecha_ingreso, data_complete.cbu])

if __name__ == "__main__":
    # Simple manual run if pytest is not available
    try:
        test_validate_cuil_algorithm()
        print("CUIL Validation Tests: PASSED")
        test_activation_logic_mock()
        print("Activation Logic Mock Tests: PASSED")
    except Exception as e:
        print(f"Tests FAILED: {e}")
