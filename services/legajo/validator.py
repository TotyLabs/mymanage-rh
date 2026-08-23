"""
Legajo Validator — enforces business rules and data integrity.

Tiers:
1. Row validation (Critical errors: missing DNI/CUIL, invalid CUIL checksum).
2. Warning validation (Suspicious data: hire_date < 18 years from birth).
3. Batch validation (Duplicates in the same file).
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

from .canonical import CanonicalEmployeeRecord
from .cuil_validator import validate_cuil
from .mapping import COLUMNS_CONFIG
from .schema_manager import SchemaManager

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    level: str             # 'error' | 'warning'
    code: str              # e.g. 'MISSING_DNI'
    message: str
    field_path: Optional[str] = None  # e.g. 'identity.dni'

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "code": self.code,
            "message": self.message,
            "field": self.field_path
        }


class Validator:
    def __init__(self, schema_manager: SchemaManager = None):
        self.schema_manager = schema_manager
        # Mapping of Path -> (Friendly Name, Is Core?)
        self.rules = {
            "identity.dni": ("DNI", True),
            "identity.last_name": ("Apellido", False),
            "employment.hire_date": ("Fecha de Ingreso", False),
        }

    def validate_row(self, record: CanonicalEmployeeRecord, 
                     is_manual: bool = False) -> List[ValidationIssue]:
        issues = []
        
        logger.debug(f"Validator: record.db_fields keys: {list(record.db_fields.keys())}")
        if self.schema_manager:
            logger.debug(f"Validator: schema columns: {self.schema_manager.columns[:5]}... (total {len(self.schema_manager.columns)})")
        
        # 1. -- Dynamic Mandatory Fields --
        if self.schema_manager:
            for path, (friendly, is_core) in self.rules.items():
                col = self.schema_manager.get_column_for_path(path)
                
                # Rule: Only enforce if column exists in the actual DB
                if col in self.schema_manager.columns:
                    val = record.db_fields.get(col)
                    if not val:
                        # Phase 39: hire_date is warning even in manual if not core
                        is_crit = is_core or (is_manual and path != "employment.hire_date")
                        level = "error" if is_crit else "warning"
                        issues.append(ValidationIssue(
                            level=level, code=f"MISSING_{col.upper()}",
                            message=f"El '{friendly}' es obligatorio.", 
                            field_path=path
                        ))

        # 2. -- Specific Format Validations (If present) --
        
        # DNI Format
        dni = record.db_fields.get("dni")
        if dni:
            if not (dni.isdigit() and 7 <= len(dni) <= 9):
                issues.append(ValidationIssue(
                    level="error", code="INVALID_DNI_FORMAT",
                    message=f"DNI inválido: '{dni}'. Debe ser numérico y tener 7-9 dígitos.",
                    field_path="identity.dni"
                ))

        # CUIL format & Checksum
        cuil = record.db_fields.get("cuil")
        if cuil:
            if not (cuil.isdigit() and len(cuil) == 11):
                issues.append(ValidationIssue(
                    level="error", code="INVALID_CUIL_FORMAT",
                    message="El CUIL debe ser numérico y tener 11 dígitos.",
                    field_path="identity.cuil"
                ))
            else:
                is_valid, msg = validate_cuil(cuil)
                if not is_valid:
                    issues.append(ValidationIssue(
                        level="error", code="INVALID_CUIL_CHECKSUM",
                        message=msg, field_path="identity.cuil"
                    ))

        # 3. -- Email Validation --
        email = record.db_fields.get("email")
        if email:
            if "@" not in email:
                level = "error" if is_manual else "warning"
                issues.append(ValidationIssue(
                    level=level, code="INVALID_EMAIL",
                    message="El email debe contener '@'.", field_path="address.email"
                ))
            else:
                email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_regex, email):
                    issues.append(ValidationIssue(
                        level="warning", code="SUSPICIOUS_EMAIL",
                        message="El formato del email parece inusual.", field_path="address.email"
                    ))

        # 4. -- CBU Validation --
        cbu = record.db_fields.get("cbu")
        if cbu:
            clean_cbu = re.sub(r'\D', '', str(cbu))
            if len(clean_cbu) != 22:
                issues.append(ValidationIssue(
                    level="error" if is_manual else "warning", code="INVALID_CBU_LENGTH",
                    message=f"El CBU debe tener 22 dígitos (tiene {len(clean_cbu)}).",
                    field_path="bank.cbu"
                ))

        # 5. -- Phone Validation --
        phone = record.db_fields.get("phone")
        if phone:
            clean_phone = re.sub(r'\D', '', str(phone))
            if len(clean_phone) < 6 or len(clean_phone) > 15:
                issues.append(ValidationIssue(
                    level="warning", code="SUSPICIOUS_PHONE",
                    message=f"El teléfono tiene {len(clean_phone)} dígitos (esperado 6-15).",
                    field_path="contact.phone"
                ))

        # 5b. -- Address Number Validation (length only; allows 504A, S/N, Km 42, etc.)
        address_number = record.db_fields.get("address_number")
        if address_number:
            clean_num = re.sub(r'\s+', ' ', str(address_number).strip())
            max_len = COLUMNS_CONFIG.get("address.address_number", {}).get("max_length", 30)
            if len(clean_num) > max_len:
                issues.append(ValidationIssue(
                    level="warning", code="LONG_ADDRESS_NUMBER",
                    message=f"El número de domicilio excede {max_len} caracteres.",
                    field_path="address.address_number"
                ))

        # 6. -- Name Length Validation --
        for name_field in ["first_name", "last_name"]:
            name_val = record.db_fields.get(name_field)
            if name_val and len(str(name_val)) > 100:
                issues.append(ValidationIssue(
                    level="warning", code=f"LONG_{name_field.upper()}",
                    message=f"El campo '{name_field}' excede 100 caracteres.",
                    field_path=f"identity.{name_field}"
                ))

        # 7. -- Logic Checks (Warnings) --
        
        # Future Hire (max 2 years)
        if record.employment.hire_date:
            if record.employment.hire_date > date.today() + timedelta(days=730):
                issues.append(ValidationIssue(
                    level="warning", code="FUTURE_HIRE",
                    message="La fecha de ingreso es superior a 2 años en el futuro.",
                    field_path="employment.hire_date"
                ))
            # Historical limit
            if record.employment.hire_date < date(1900, 1, 1):
                issues.append(ValidationIssue(
                    level="error", code="INVALID_HIRE_DATE",
                    message="La fecha de ingreso es anterior a 1900.",
                    field_path="employment.hire_date"
                ))

        # Underage check
        birth_date = record.identity.birth_date
        if birth_date and record.employment.hire_date:
            age_at_hire = (record.employment.hire_date - birth_date).days / 365.25
            if age_at_hire < 16:
                issues.append(ValidationIssue(
                    level="warning", code="UNDERAGE",
                    message=f"La edad al ingreso es sospechosa ({age_at_hire:.1f} años).",
                    field_path="identity.birth_date"
                ))

        return issues

    def validate_batch(self, records: List[CanonicalEmployeeRecord]) -> List[ValidationIssue]:
        batch_issues = []
        dni_map = {}
        for record in records:
            dni = record.identity.dni
            if dni:
                dni_map[dni] = dni_map.get(dni, 0) + 1

        for dni, count in dni_map.items():
            if count > 1:
                batch_issues.append(ValidationIssue(
                    level="error", code="DUPLICATE_DNI_BATCH",
                    message=f"El DNI {dni} está duplicado {count} veces en el archivo.",
                    field_path="identity.dni"
                ))

        return batch_issues
