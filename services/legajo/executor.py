"""
Import Execution Engine â€” Final Commitment Phase.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session
from models import (
    Employee, EmployeeExtraData, ImportJob, ImportJobRow, 
    ImportJobStatus, ImportMode, ResolutionStatus
)
from .canonical import CanonicalEmployeeRecord

logger = logging.getLogger(__name__)


class ImportExecutor:
    def __init__(self, db: Session):
        self.db = db

    def execute(self, job_id: str) -> Dict[str, int]:
        """
        Commits all 'insert' and 'update' rows to the actual Employee tables.
        This is a SINGLE ATOMIC TRANSACTION phase.
        """
        job = self.db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job:
            raise ValueError("Job not found")
        
        # â”€â”€ Idempotency & Safety Checks â”€â”€
        if job.status == ImportJobStatus.imported:
            raise ValueError("Este trabajo ya fue ejecutado previamente.")
            
        if job.status not in (ImportJobStatus.preview_ready, ImportJobStatus.failed):
            raise ValueError(f"El trabajo estÃ¡ en un estado invÃ¡lido para ejecuciÃ³n: {job.status}")

        # Transition to importing without committing yet
        job.status = ImportJobStatus.importing
        job.operation_type = "execute"
        self.db.flush()

        metrics = {"inserted": 0, "updated": 0, "failed": 0}

        # Fetch only actionable rows
        actionable_rows = self.db.query(ImportJobRow).filter(
            ImportJobRow.import_job_id == job_id,
            ImportJobRow.planned_action.in_(["insert", "update"])
        ).all()

        for row in actionable_rows:
            try:
                record = CanonicalEmployeeRecord.from_dict(row.normalized_data_json)
                
                if row.planned_action == "insert":
                    self._do_insert(job.organization_id, record)
                    metrics["inserted"] += 1
                elif row.planned_action == "update":
                    self._do_update(row.match_employee_id, record, ImportMode(job.import_mode))
                    metrics["updated"] += 1
                
                row.resolution_status = ResolutionStatus.success
            except Exception as e:
                logger.exception(f"Failed to execute row {row.id}")
                row.resolution_status = ResolutionStatus.failed
                row.execution_error = str(e)
                metrics["failed"] += 1

        # Final Job Update & ATOMIC COMMIT
        job.status = ImportJobStatus.imported
        job.finished_at = datetime.utcnow()
        self.db.commit()

        return metrics

    def _do_insert(self, org_id: str, record: CanonicalEmployeeRecord):
        """Creates new Employee and EmployeeExtraData."""
        # 1. Base Employee
        emp = Employee(
            organization_id=org_id,
            dni=record.identity.dni,
            cuil=record.identity.cuil,
            first_name=record.identity.first_name,
            last_name=record.identity.last_name,
            email=record.identity.email or f"{record.identity.dni}@mymanagerh.local", # Fallback for system integrity
            is_active=True
        )
        self.db.add(emp)
        self.db.flush() # Get emp.id

        # 2. Extra Data
        extra = EmployeeExtraData(employee_id=emp.id)
        self._map_record_to_extra(record, extra)
        self.db.add(extra)

    def _do_update(self, employee_id: str, record: CanonicalEmployeeRecord, mode: ImportMode):
        """Updates existing Employee and EmployeeExtraData."""
        emp = self.db.query(Employee).filter(Employee.id == employee_id).first()
        if not emp:
            raise ValueError(f"Employee {employee_id} vanished during execution.")

        # Update base fields (Merge style: only if present)
        if record.identity.first_name: emp.first_name = record.identity.first_name
        if record.identity.last_name: emp.last_name = record.identity.last_name
        if record.identity.email: emp.email = record.identity.email

        # Extra Data
        extra = self.db.query(EmployeeExtraData).filter(EmployeeExtraData.employee_id == employee_id).first()
        if not extra:
            extra = EmployeeExtraData(employee_id=employee_id)
            self.db.add(extra)
        
        self._map_record_to_extra(record, extra, mode=mode)

    def _map_record_to_extra(self, record: CanonicalEmployeeRecord, extra: EmployeeExtraData, mode: ImportMode = ImportMode.merge):
        """
        Maps the flat/nested Canonical record into the DB model.
        Merge mode: only overwrite non-null values from record.
        """
        # Mapping Identity
        self._set_if(extra, "sex_code", record.identity.sex_code, mode)
        self._set_if(extra, "birth_date", record.identity.birth_date, mode)

        # Mapping Address
        self._set_if(extra, "address_street", record.address.street_name, mode)
        self._set_if(extra, "address_number", record.address.street_number, mode)
        self._set_if(extra, "address_floor", record.address.floor, mode)
        self._set_if(extra, "address_apartment", record.address.apartment, mode)
        self._set_if(extra, "address_city", record.address.city, mode)
        self._set_if(extra, "address_province", record.address.province, mode)
        self._set_if(extra, "address_zip_code", record.address.zip_code, mode)

        # Mapping Employment
        self._set_if(extra, "legajo_number", record.employment.legajo_number, mode)
        self._set_if(extra, "hire_date", record.employment.hire_date, mode)
        self._set_if(extra, "termination_date", record.employment.termination_date, mode)
        self._set_if(extra, "agreement_code", record.employment.agreement_code, mode)
        self._set_if(extra, "category_code", record.employment.category_code, mode)
        self._set_if(extra, "division_code", record.employment.division_code, mode)
        self._set_if(extra, "cost_center_code", record.employment.cost_center_code, mode)
        self._set_if(extra, "assigned_monthly_hours", record.employment.assigned_monthly_hours, mode)

        # Mapping Payroll
        self._set_if(extra, "payment_method_code", record.payroll.payment_method_code, mode)
        self._set_if(extra, "salary_amount", record.payroll.salary_amount, mode)
        self._set_if(extra, "salary_currency", record.payroll.salary_currency, mode)

        # Mapping Banking
        self._set_if(extra, "bank_name", record.banking.bank_name, mode)
        self._set_if(extra, "bank_branch", record.banking.bank_branch, mode)
        self._set_if(extra, "bank_cbu", record.banking.cbu, mode)
        self._set_if(extra, "bank_account_number", record.banking.account_number, mode)

        # Mapping Social Security
        self._set_if(extra, "social_work_code", record.social.social_work_code, mode)
        self._set_if(extra, "health_insurance_code", record.social.health_insurance_code, mode)
        self._set_if(extra, "union_code", record.social.union_code, mode)

    def _set_if(self, target: Any, attr: str, val: Any, mode: ImportMode):
        """Helper to decide whether to set an attribute."""
        if val is not None:
            setattr(target, attr, val)
        elif mode == ImportMode.replace:
            # In replace mode, if source is null, we clear the DB field
            setattr(target, attr, None)
        # In merge mode, if source is null, we keep existing DB value
