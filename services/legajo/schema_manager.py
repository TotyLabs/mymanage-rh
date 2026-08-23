"""
Schema Manager — queries the database to discover canonical fields at runtime.
"""

import logging
from typing import List, Dict
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Fields that must ALWAYS be considered core if they exist
REQUIRED_CORE = ["dni"]

# Mapping of DB column names to Logical Paths (Canonical Names)
COLUMN_TO_PATH = {
    # Identity
    "dni": "identity.dni",
    "cuil": "identity.cuil",
    "first_name": "identity.first_name",
    "last_name": "identity.last_name",
    "full_name": "identity.full_name",
    "gender": "identity.gender",
    "birth_date": "identity.birth_date",
    "marital_status": "identity.marital_status",
    "nationality": "identity.nationality",
    
    # Contact & Address
    "email": "address.email",
    "phone": "address.phone",
    "address": "address.address",
    "address_number": "address.address_number",
    "city": "address.city",
    "province": "address.province",
    "postal_code": "address.postal_code",
    
    # Documentary
    "document_type": "documentary.document_type",
    "document_number": "documentary.document_number",
    "health_insurance": "documentary.health_insurance",
    "health_insurance_number": "documentary.health_insurance_number",
    "union": "documentary.union",
    "union_number": "documentary.union_number",

    # Employment
    "file_number": "employment.file_number",
    "hire_date": "employment.hire_date",
    "termination_date": "employment.termination_date",
    "job_title": "employment.job_title",
    "category": "employment.category",
    "task": "employment.task",
    "cost_center": "employment.cost_center",
    "union_agreement": "employment.union_agreement",
    "hire_type": "employment.hire_type",
    "work_location": "employment.work_location",
    "status": "employment.status",
    "status_reason": "employment.status_reason",
    
    # Banking
    "bank": "banking.bank",
    "bank_code": "banking.bank_code",
    "bank_branch": "banking.bank_branch",
    "account_type": "banking.account_type",
    "account_number": "banking.account_number",
    "cbu": "banking.cbu",
    "bank_alias": "banking.bank_alias",
    "payment_method": "banking.payment_method",
    "payment_place": "banking.payment_place",
    
    # Pension (Previsionales)
    "pension_regime": "pension.pension_regime",
    "activity": "pension.activity",
    "labor_condition": "pension.labor_condition",
    "revista_situation": "pension.revista_situation"
}

# Reverse map for convenience
PATH_TO_COLUMN = {v: k for k, v in COLUMN_TO_PATH.items()}

class SchemaManager:
    def __init__(self, db_session: Session, job_id: str = "unknown"):
        self.db = db_session
        self.job_id = job_id
        self._ctx = f"[IMPORT {self.job_id}]"
        self._columns = []
        self._required = []

    def discover_schema(self, table_name: str = "employees") -> List[str]:
        """Queries information_schema to get column names."""
        query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = :table 
            AND table_schema = 'public'
        """)
        try:
            result = self.db.execute(query, {"table": table_name}).fetchall()
            self._columns = [row[0] for row in result]
            
            # Filter out internal/audit columns
            ignored = ["id", "organization_id", "created_at", "updated_at", "invite_token", "invite_token_expires_at", "profile_completed", "is_active", "status_reason"]
            self._columns = [c for c in self._columns if c not in ignored]
            
            # Determine required
            self._required = [c for c in REQUIRED_CORE if c in self._columns]
            
            logger.debug(f"{self._ctx} Schema discovered for '{table_name}': {len(self._columns)} active columns.")
            return self._columns
        except Exception as e:
            logger.error(f"{self._ctx} Failed to discover schema for {table_name}: {e}")
            return []

    @property
    def columns(self) -> List[str]:
        return self._columns

    @property
    def required_fields(self) -> List[str]:
        return self._required

    def get_path_for_column(self, col_name: str) -> str:
        """Returns the logical path for a column, or the column name itself."""
        return COLUMN_TO_PATH.get(col_name, col_name)

    def get_column_for_path(self, path: str) -> str:
        """Returns the DB column for a logical path, or the path itself if no mapping."""
        return PATH_TO_COLUMN.get(path, path)
