"""
CUIL/CUIT Validator â€” check-digit verification.

Algorithm: standard MÃ³dulo 11 used by AFIP/ANSES.
Input: string of 11 digits (no dashes).
Output: True/False.

The workbook 'Modelo Legajo Ingreso 2012_Merida.xls' embeds this same
algorithm in cells R70:AC73 of the LEGAJO sheet.
"""

import re

# Coefficients for CUIL/CUIT mÃ³dulo 11
_WEIGHTS = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]


def validate_cuil(cuil: str | None) -> tuple[bool, str]:
    """
    Validates a CUIL/CUIT string.

    Returns:
        (is_valid, message)
    """
    if not cuil:
        return False, "CUIL vacío"

    # Strip dashes, spaces
    clean = re.sub(r"[\s\-]", "", str(cuil).strip())

    if not clean.isdigit():
        return False, "CUIL contiene caracteres no numéricos"

    if len(clean) != 11:
        return False, f"CUIL debe tener 11 dígitos, tiene {len(clean)}"

    # Prefix validation (20, 23, 24, 27, 30, 33, 34)
    prefix = clean[:2]
    valid_prefixes = {"20", "23", "24", "27", "30", "33", "34"}
    if prefix not in valid_prefixes:
        return False, f"Prefijo CUIL inválido: {prefix}"

    # Check digit calculation
    digits = [int(d) for d in clean]
    weighted_sum = sum(d * w for d, w in zip(digits[:10], _WEIGHTS))
    remainder = weighted_sum % 11
    check = 11 - remainder

    if check == 11:
        check = 0
    elif check == 10:
        check = 9  # Some implementations use 9 as fallback

    if digits[10] != check:
        return False, f"Dígito verificador incorrecto: esperado {check}, encontrado {digits[10]}"

    return True, "CUIL válido"


def normalize_cuil(cuil: str | None) -> str | None:
    """
    Strips dashes/spaces from a CUIL and returns clean 11-digit string.
    Returns None if input is empty/invalid format.
    """
    if not cuil:
        return None
    clean = re.sub(r"[\s\-]", "", str(cuil).strip())
    if len(clean) == 11 and clean.isdigit():
        return clean
    return None
