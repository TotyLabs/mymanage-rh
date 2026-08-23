"""
TXT Fixed-Width Export Specification V1.

Source of truth: IMPORTACION MODELO LEG
  - Row 3 (0-indexed) = start positions
  - Row 4 (0-indexed) = field lengths
  - Row 5 (0-indexed) = field names
  - Total modeled width: 578 characters (pos 566 + len 12)

Each field has:
  - canonical_field: path into CanonicalEmployeeRecord
  - start: 1-based start position in the fixed-width line
  - length: number of characters
  - align: 'left' or 'right'
  - fill: padding character (' ' for text, '0' for numeric/codes)
  - null_fill: what to emit when value is None
  - formatter: optional callable name for special formatting
"""

from dataclasses import dataclass
from typing import Optional

SPEC_VERSION = "1"
TOTAL_LINE_WIDTH = 577


@dataclass(frozen=True)
class TxtFieldSpec:
    canonical_field: str
    start: int          # 1-based
    length: int
    align: str          # 'left' | 'right'
    fill: str           # padding character
    null_fill: str      # what to write if value is None
    formatter: Optional[str] = None  # 'date_ddmmyyyy' etc.


# â”€â”€â”€ Spec built from the real XLS IMPORTACION MODELO LEG â”€â”€â”€â”€â”€â”€
# Positions and lengths extracted directly from Row 3 and Row 4

TXT_577_SPEC_V1: list[TxtFieldSpec] = [
    TxtFieldSpec("payroll.legajo_number",                   1,    6, "right", "0", "0" * 6),
    TxtFieldSpec("payroll.card_number",                     7,    6, "right", "0", "0" * 6),
    TxtFieldSpec("identity.last_name",                      13,  20, "left",  " ", " " * 20),
    TxtFieldSpec("identity.first_name",                     33,  20, "left",  " ", " " * 20),
    TxtFieldSpec("address.street",                          53,  25, "left",  " ", " " * 25),
    TxtFieldSpec("address.street_number",                   78,   6, "right", "0", "0" * 6),
    TxtFieldSpec("address.floor",                           84,   2, "right", "0", "0" * 2),
    TxtFieldSpec("address.apartment",                       86,   5, "left",  " ", " " * 5),
    TxtFieldSpec("address.tower",                           91,  10, "left",  " ", " " * 10),
    TxtFieldSpec("address.postal_code",                    101,  10, "left",  " ", " " * 10),
    TxtFieldSpec("address.city",                           111,  25, "left",  " ", " " * 25),
    TxtFieldSpec("address.paraje",                         136,  25, "left",  " ", " " * 25),
    TxtFieldSpec("address.province_code",                  161,   2, "right", "0", "0" * 2),
    TxtFieldSpec("address.country",                        163,  20, "left",  " ", " " * 20),
    TxtFieldSpec("address.phone",                          183,  30, "left",  " ", " " * 30),
    TxtFieldSpec("address.email",                          213,  40, "left",  " ", " " * 40),
    TxtFieldSpec("identity.marital_status_code",            253,   2, "right", "0", "0" * 2),
    TxtFieldSpec("identity.nationality_code",              255,   4, "right", "0", "0" * 4),
    TxtFieldSpec("identity.document_type_code",            259,   2, "right", "0", "0" * 2),
    TxtFieldSpec("identity.dni",                           261,  10, "right", "0", "0" * 10),
    TxtFieldSpec("_skip_anses_issue_place",                271,   4, "right", "0", "0" * 4),
    TxtFieldSpec("identity.sex_code",                      275,   1, "right", "0", "0"),
    TxtFieldSpec("_birth_date",                            276,  10, "left",  " ", " " * 10, "date_ddmmyyyy"),
    TxtFieldSpec("_skip_edad",                             286,   2, "right", "0", "0" * 2),
    TxtFieldSpec("employment.category_code",               288,   4, "right", "0", "0" * 4),
    TxtFieldSpec("employment.section_code",                292,   6, "right", "0", "0" * 6),
    TxtFieldSpec("employment.task_code",                   298,   6, "right", "0", "0" * 6),
    TxtFieldSpec("employment.position_code",               304,  10, "right", "0", "0" * 10),
    TxtFieldSpec("_skip_cost_center",                      314,   6, "right", "0", "0" * 6),
    TxtFieldSpec("social_security.retirement_regime_code", 320,   6, "right", "0", "0" * 6),
    TxtFieldSpec("employment.hire_date",                   326,  10, "left",  " ", " " * 10, "date_ddmmyyyy"),
    TxtFieldSpec("_skip_seniority",                        336,   4, "right", "0", "0" * 4),
    TxtFieldSpec("_skip_prior_seniority",                  340,   4, "right", "0", "0" * 4),
    TxtFieldSpec("employment.termination_date",            344,  10, "left",  " ", " " * 10, "date_ddmmyyyy"),
    TxtFieldSpec("_skip_anses_baja",                       354,   4, "right", "0", "0" * 4),
    TxtFieldSpec("employment.activity_code",               358,   6, "right", "0", "0" * 6),
    TxtFieldSpec("employment.labor_condition_code",        364,   4, "right", "0", "0" * 4),
    TxtFieldSpec("employment.contract_mode_code",          368,   6, "right", "0", "0" * 6),
    TxtFieldSpec("employment.hazardous_task_code",         374,   6, "right", "0", "0" * 6),
    TxtFieldSpec("employment.afip_revista_status_code",    380,   4, "right", "0", "0" * 4),
    TxtFieldSpec("employment.afip_locality_province_code", 384,   4, "right", "0", "0" * 4),
    TxtFieldSpec("payroll.payroll_concept_group_code",     388,   4, "right", "0", "0" * 4),
    TxtFieldSpec("banking.bank_code",                      392,   6, "right", "0", "0" * 6),
    TxtFieldSpec("banking.bank_account_number",            398,  20, "right", "0", "0" * 20),
    TxtFieldSpec("banking.bank_account_type_code",         418,   8, "right", "0", "0" * 8),
    TxtFieldSpec("banking.cbu",                            426,  25, "right", "0", "0" * 25),
    TxtFieldSpec("payroll.payment_method_code",            451,   4, "right", "0", "0" * 4),
    TxtFieldSpec("social_security.health_insurance_code",  455,   7, "right", "0", "0" * 7),
    TxtFieldSpec("identity.cuil",                          462,  13, "right", "0", "0" * 13),
    TxtFieldSpec("social_security.union_code",             475,   4, "right", "0", "0" * 4),
    TxtFieldSpec("_skip_baja_trans",                       479,   1, "right", "0", "0"),
    TxtFieldSpec("_skip_baja_def",                         480,   1, "right", "0", "0"),
    TxtFieldSpec("payroll.remuneration_type_code",         481,   1, "right", "0", "0"),
    TxtFieldSpec("social_security.agreement_type_code",    482,   1, "right", "0", "0"),
    TxtFieldSpec("employment.assigned_monthly_hours",      483,   6, "right", "0", "0" * 6),
    TxtFieldSpec("_skip_grossing_up",                      489,   1, "right", "0", "0"),
    TxtFieldSpec("_skip_zona_desfav",                      490,   1, "right", "0", "0"),
    TxtFieldSpec("payroll.salary_amount",                  491,  11, "right", "0", "0" * 11),
    TxtFieldSpec("_skip_afecta_est",                       502,   1, "right", "0", "0"),
    TxtFieldSpec("social_security.union_agreement_code",   503,   6, "right", "0", "0" * 6),
    TxtFieldSpec("_skip_siniestrado",                      509,   2, "right", "0", "0" * 2),
    TxtFieldSpec("payroll.payment_place_code",             511,   4, "right", "0", "0" * 4),
    TxtFieldSpec("_skip_aguinaldo_base",                   515,   9, "right", "0", "0" * 9),
    TxtFieldSpec("social_security.union_member_number",    524,  20, "right", "0", "0" * 20),
    TxtFieldSpec("social_security.unemployment_fund_account", 544, 22, "right", "0", "0" * 22),
    TxtFieldSpec("payroll.ieric_number",                   566,  12, "right", "0", "0" * 12),
]


def verify_spec_integrity():
    """Sanity check: verify the spec covers exactly TOTAL_LINE_WIDTH characters with no gaps."""
    covered = set()
    for f in TXT_577_SPEC_V1:
        for pos in range(f.start, f.start + f.length):
            assert pos not in covered, f"Overlap at position {pos} ({f.canonical_field})"
            covered.add(pos)
    expected = set(range(1, TOTAL_LINE_WIDTH + 1))
    missing = expected - covered
    extra = covered - expected
    assert not missing, f"Missing positions: {sorted(missing)}"
    assert not extra, f"Extra positions: {sorted(extra)}"
    return True
