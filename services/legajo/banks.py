"""
Banco Master — tabla maestra de bancos para ISIS Payroll.

Referencia exacta: imagen "FACU BANCOS" (tabla enviada por el usuario).
Cada banco tiene: código, descripción, sucursal, cód tipo cuenta, tipo cuenta.

NO IMPROVISAR: estos datos provienen directamente de la referencia del usuario.
"""

from dataclasses import dataclass
from typing import List, Optional
import unicodedata
import re


@dataclass(frozen=True)
class BankRecord:
    code: str           # Código numérico (ej: "1", "14")
    name: str           # Descripción (ej: "Banco Credicoop")
    branch: str         # Sucursal default (ej: "001")
    account_type_code: str  # Código tipo cuenta (ej: "2")
    account_type: str   # Desc tipo cuenta (ej: "Cuenta", "Caja")


# ---------------------------------------------------------------
# TABLA MAESTRA — Referencia directa de la imagen del usuario
# ---------------------------------------------------------------
BANK_MASTER: List[BankRecord] = [
    BankRecord("1",  "Banco Ciudad",           "00000", "2", "Cuenta"),
    BankRecord("2",  "Banco Boston",           "00000", "2", "Cuenta"),
    BankRecord("3",  "Nación",                 "00000", "2", "Cuenta"),
    BankRecord("4",  "Banco Patagonia AFJP",   "00000", "0", "Sin"),
    BankRecord("5",  "Banco Galicia",          "0007",  "2", "Cuenta"),
    BankRecord("6",  "Provincia de Bs. As.",   "00000", "2", "Cuenta"),
    BankRecord("7",  "Citibank",               "00000", "2", "Cuenta"),
    BankRecord("8",  "Río",                    "767",   "2", "Cuenta"),
    BankRecord("9",  "Itaú",                   "00000", "2", "Cuenta"),
    BankRecord("10", "BNL",                    "00000", "2", "Cuenta"),
    BankRecord("11", "Bisel",                  "00000", "2", "Cuenta"),
    BankRecord("12", "Banco Frances",          "00000", "2", "Cuenta"),
    BankRecord("13", "Banco BNP Paribas",      "00000", "2", "Cuenta"),
    BankRecord("14", "Banco Credicoop",        "001",   "2", "Cuenta"),
    BankRecord("15", "Otros Bancos",           "0",     "1", "Caja"),
    BankRecord("16", "Banco Credicoop 1",      "004",   "1", "Caja"),
    BankRecord("17", "Banco ICBC",             "543",   "1", "Caja"),
    BankRecord("18", "Banco Credicoop 2",      "136",   "1", "Caja"),
]

# Fast lookup by code
_BY_CODE = {b.code: b for b in BANK_MASTER}

# Fuzzy matching keywords → code
_KEYWORDS = {
    "ciudad":     "1",
    "boston":      "2",
    "nacion":     "3",
    "patagonia":  "4",
    "galicia":    "5",
    "provincia":  "6",
    "citibank":   "7",
    "citi":       "7",
    "rio":        "8",
    "itau":       "9",
    "bnl":        "10",
    "bisel":      "11",
    "frances":    "12",
    "bbva":       "12",
    "bnp":        "13",
    "paribas":    "13",
    "credicoop":  "14",
    "icbc":       "17",
    "hsbc":       "15",  # fallback → Otros
    "santander":  "15",  # fallback → Otros
    "macro":      "15",  # fallback → Otros
    "supervielle":"15",  # fallback → Otros
}


def _normalize(s: str) -> str:
    """Lowercase, remove accents, strip non-alpha."""
    s = str(s).lower().strip()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    return s


def get_bank_by_code(code: str) -> Optional[BankRecord]:
    """Exact lookup by code."""
    return _BY_CODE.get(str(code))


def detect_bank(raw_bank_name: str) -> Optional[BankRecord]:
    """
    Attempts to match a raw bank string (from Excel/parser) to the master table.
    Returns BankRecord if matched, None otherwise.
    NEVER raises — fallback is manual selection.
    """
    if not raw_bank_name:
        return None

    norm = _normalize(raw_bank_name)

    # 1. Exact code match (e.g. parser already resolved to "5")
    if norm.isdigit():
        return _BY_CODE.get(norm)

    # 2. Keyword contain match (best effort)
    for keyword, code in _KEYWORDS.items():
        if keyword in norm:
            return _BY_CODE[code]

    return None


def list_banks() -> List[dict]:
    """Returns the full master list as dicts for API consumption."""
    return [
        {
            "code": b.code,
            "name": b.name,
            "branch": b.branch,
            "account_type_code": b.account_type_code,
            "account_type": b.account_type,
        }
        for b in BANK_MASTER
    ]
