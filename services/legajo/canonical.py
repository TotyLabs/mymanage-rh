"""
Canonical Employee Record — the single internal representation.
Updated to match high-fidelity semantic mapping and Employee model.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Any, Dict, List
from datetime import date


@dataclass
class IdentityBlock:
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    dni: Optional[str] = None
    cuil: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    marital_status: Optional[str] = None
    nationality: Optional[str] = None


@dataclass
class AddressBlock:
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    address_number: Optional[str] = None
    city: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None


@dataclass
class DocumentaryBlock:
    document_type: Optional[str] = None
    document_number: Optional[str] = None
    health_insurance: Optional[str] = None
    health_insurance_number: Optional[str] = None
    union: Optional[str] = None
    union_number: Optional[str] = None


@dataclass
class EmploymentBlock:
    file_number: Optional[str] = None
    hire_date: Optional[date] = None
    termination_date: Optional[date] = None
    job_title: Optional[str] = None
    category: Optional[str] = None
    task: Optional[str] = None
    cost_center: Optional[str] = None
    union_agreement: Optional[str] = None
    hire_type: Optional[str] = None
    work_location: Optional[str] = None
    status: Optional[str] = None
    status_reason: Optional[str] = None


@dataclass
class BankingBlock:
    bank: Optional[str] = None
    bank_code: Optional[str] = None
    bank_branch: Optional[str] = None
    account_type: Optional[str] = None
    account_number: Optional[str] = None
    cbu: Optional[str] = None
    bank_alias: Optional[str] = None
    payment_method: Optional[str] = None
    payment_place: Optional[str] = None


@dataclass
class PensionBlock:
    pension_regime: Optional[str] = None
    activity: Optional[str] = None
    labor_condition: Optional[str] = None
    revista_situation: Optional[str] = None


@dataclass
class MetaBlock:
    source_row_number: Optional[int] = None
    source_format: Optional[str] = None
    mapping_version: str = "3"
    source_file_sha256: Optional[str] = None


@dataclass
class CanonicalEmployeeRecord:
    """
    The ONE internal model. High-fidelity representation of an employee.
    """
    identity: IdentityBlock = field(default_factory=IdentityBlock)
    address: AddressBlock = field(default_factory=AddressBlock)
    documentary: DocumentaryBlock = field(default_factory=DocumentaryBlock)
    employment: EmploymentBlock = field(default_factory=EmploymentBlock)
    banking: BankingBlock = field(default_factory=BankingBlock)
    pension: PensionBlock = field(default_factory=PensionBlock)
    meta: MetaBlock = field(default_factory=MetaBlock)

    # Dynamic schema-aware fields (Direct DB mapping)
    db_fields: Dict[str, Any] = field(default_factory=dict)
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    extra_fields_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        def serialize(obj):
            if isinstance(obj, date):
                return obj.isoformat()
            if isinstance(obj, dict):
                return {k: serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [serialize(i) for i in obj]
            return obj
        
        return serialize(asdict(self))

    @classmethod
    def from_dict(cls, data: dict) -> 'CanonicalEmployeeRecord':
        """Reconstructs a CanonicalEmployeeRecord from a serialized dict (e.g. from DB JSON)."""
        if not data:
            return cls()

        def _parse_date(val):
            if val is None:
                return None
            if isinstance(val, date):
                return val
            try:
                from datetime import datetime
                return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                return None

        def _build_block(block_cls, block_data, date_fields=()):
            if not isinstance(block_data, dict):
                return block_cls()
            kwargs = {}
            for f_name in block_cls.__dataclass_fields__:
                val = block_data.get(f_name)
                if f_name in date_fields:
                    val = _parse_date(val)
                kwargs[f_name] = val
            return block_cls(**kwargs)

        record = cls()
        record.identity = _build_block(IdentityBlock, data.get("identity", {}), date_fields=("birth_date",))
        record.address = _build_block(AddressBlock, data.get("address", {}))
        record.documentary = _build_block(DocumentaryBlock, data.get("documentary", {}))
        record.employment = _build_block(EmploymentBlock, data.get("employment", {}), date_fields=("hire_date", "termination_date"))
        record.banking = _build_block(BankingBlock, data.get("banking", {}))
        record.pension = _build_block(PensionBlock, data.get("pension", {}))
        record.meta = _build_block(MetaBlock, data.get("meta", {}))
        record.db_fields = data.get("db_fields", {})
        record.extra_fields = data.get("extra_fields", {})
        record.extra_fields_metadata = data.get("extra_fields_metadata", {})
        return record
