"""
Unified Ingestion Service — The "Nucleus" of employee data entry.
Centralizes Normalization, Validation, Matching, and Persistence.
"""

import logging
import time
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from models import Employee, EmployeeStatus, ImportMode
from .schema_manager import SchemaManager
from .normalizer import Normalizer
from .validator import Validator, ValidationIssue
from .matching import MatchingService, MatchingResult, UpsertPlanner
from payroll_core import audit, logger as core_logger

logger = logging.getLogger(__name__)

class IngestionMode(Enum):
    MANUAL = "manual"  # Strict, UI-based
    IMPORT = "import"  # Batch tolerant
    SYNC = "sync"      # External source integration

class IngestionResult:
    def __init__(self, status: str, employee_id: Optional[str] = None, 
                 issues: List[ValidationIssue] = None, 
                 match_info: Dict[str, Any] = None,
                 record: Any = None,
                 execution_time_ms: float = 0):
        self.status = status # success | partial | failed
        self.employee_id = employee_id
        self.issues = issues or []
        self.match_info = match_info or {}
        self.record = record
        self.execution_time_ms = execution_time_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "employee_id": self.employee_id,
            "match_info": self.match_info,
            "execution_time_ms": self.execution_time_ms,
            "errors": [iss.to_dict() for iss in self.issues if iss.level == "error"],
            "warnings": [iss.to_dict() for iss in self.issues if iss.level == "warning"],
            "data": self.record.to_dict() if self.record else {}
        }

class IngestionService:
    def __init__(self, db: Session, organization_id: str, author_id: Optional[str] = None, job_id: str = "unknown"):
        self.db = db
        self.org_id = organization_id
        self.author_id = author_id # Use None if automated, since actor_id is UUID
        self.job_id = job_id
        self._ctx = f"[IMPORT {self.job_id}]"
        
        # Components
        self.schema_manager = SchemaManager(db, job_id=self.job_id)
        self.normalizer = Normalizer(self.schema_manager, job_id=self.job_id)
        self.validator = Validator(self.schema_manager)
        self.matcher = MatchingService(db)
        self.planner = UpsertPlanner()

    def process_row(self, raw_data: Dict[str, Any], 
                    mode: IngestionMode = IngestionMode.MANUAL,
                    source_row_num: int = 0,
                    is_preview: bool = False) -> IngestionResult:
        """
        The Unified Nucleus: Orchestrates the full ingestion pipeline for a single row.
        """
        start_time = time.time()
        
        try:
            # 1. Pre-cleaning & Normalization
            # Ensure fresh schema for every row in manual, or once per job in batch (caller handles)
            self.schema_manager.discover_schema()
            
            # Use IMPORT mode if it's batch, else MERGE
            import_mode = ImportMode.merge if mode == IngestionMode.MANUAL else ImportMode.merge
            
            record = self.normalizer.normalize_row(raw_data, source_row_num)
            
            # -- Garbage Filter (catches JS artifacts and obvious placeholders) --
            # NOTE: "0" and "0.0" removed — valid for test DNIs and numeric fields (business decision)
            def is_garbage(val: Any) -> bool:
                if not val: return True
                v = str(val).strip().lower()
                return v in [
                    "aaa", "s/d", "sin datos", "n/a", "null",
                    "undefined", "[object object]", "none", "nan", "test",
                    "xxx", "---", "...", "no disponible"
                ]

            if is_garbage(record.identity.first_name): record.identity.first_name = None
            if is_garbage(record.identity.last_name): record.identity.last_name = None
            if is_garbage(record.identity.dni): 
                record.identity.dni = None
                record.db_fields.pop("dni", None)
            
            # 2. Validation
            issues = self.validator.validate_row(record, is_manual=(mode == IngestionMode.MANUAL))
            errors = [iss for iss in issues if iss.level == "error"]
            
            # MANUAL mode is strict: block on any error
            if mode == IngestionMode.MANUAL and errors:
                result = IngestionResult("failed", issues=issues, record=record, execution_time_ms=(time.time()-start_time)*1000)
                self._audit_ingestion(None, record, mode, None, issues, start_time)
                return result

            # 3. Deterministic Matching (DNI > CUIL > Email)
            dni = record.db_fields.get("dni")
            cuil = record.db_fields.get("cuil")
            file_number = record.db_fields.get("file_number")
            
            match = self.matcher.find_match(self.org_id, dni, cuil, file_number)
            
            if match.match_type == "conflict":
                match_issue = ValidationIssue(
                    level="error", code="IDENTITY_CONFLICT", 
                    message=match.conflict_details, field_path="identity.dni"
                )
                issues.append(match_issue)
                self._audit_ingestion(None, record, mode, match, issues, start_time)
                return IngestionResult("failed", issues=issues, record=record, 
                                       match_info={"reason": "Conflicto de identidad"},
                                       execution_time_ms=(time.time()-start_time)*1000)

            # 4. Persistence Planning
            is_invalid = len(errors) > 0
            action = self.planner.plan_action(match, import_mode, is_invalid)
            
            reason = ""
            if action == "skip":
                if not dni and not cuil: reason = "Sin identificador (DNI/CUIL)"
                elif is_invalid: reason = "Datos inválidos"
                else: reason = "Ignorado por configuración"
            elif action == "invalid":
                reason = "Fila con errores críticos"

            if action in ["invalid", "skip"] and action != "insert" and action != "update":
                self._audit_ingestion(None, record, mode, match, issues, start_time)
                return IngestionResult("failed" if action == "invalid" else "success", 
                                       issues=issues, record=record, 
                                       match_info={"strategy": action.upper(), "reason": reason},
                                       execution_time_ms=(time.time()-start_time)*1000)

            # 4. Handle Inferred Legajo
            if match.inferred_legajo:
                record.db_fields["file_number"] = match.inferred_legajo
                issues.append(ValidationIssue(
                    level="warning", 
                    code="LEG_INFERRED",
                    message=f"Legajo '{match.inferred_legajo}' inferido automáticamente desde identidad legal (DNI/CUIL)."
                ))

            # 5. Persist (Insert/Update)
            employee_id = None
            if not is_preview:
                employee = self._upsert_canonical(record, match, mode)
                
                # 6. Enterprise Audit
                self._audit_ingestion(employee, record, mode, match, issues, start_time)
                employee_id = str(employee.id)
            else:
                employee_id = match.employee_id
            
            status = "partial" if [iss for iss in issues if iss.level == "warning"] else "success"
            
            return IngestionResult(
                status=status,
                employee_id=employee_id,
                issues=issues,
                match_info={
                    "strategy": "REACTIVATE" if match.is_deleted else action.upper(), 
                    "matched_by": match.match_type,
                    "reason": "OK" if not match.is_deleted else "Legajo previamente borrado (se reactivará)"
                },
                record=record,
                execution_time_ms=(time.time() - start_time) * 1000
            )

        except Exception as e:
            logger.exception(f"{self._ctx} IngestionService.process_row_failed")
            try:
                self.db.rollback()  # Reset session status after IntegrityError
            except Exception:
                pass  # Session may already be invalidated
            return IngestionResult("failed", execution_time_ms=(time.time()-start_time)*1000, 
                                   issues=[ValidationIssue(level="error", code="INTERNAL_ERROR", message=str(e))])

    def _upsert_canonical(self, record, match: MatchingResult, mode: IngestionMode) -> Employee:
        """Handles the actual DB persistence of a Canonical Record."""
        from sqlalchemy import inspect
        
        emp_id = match.employee_id
        db_fields = record.db_fields
        extra_fields = record.extra_fields
        extra_meta = record.extra_fields_metadata
        
        if emp_id:
            # UPDATE
            employee = self.db.query(Employee).filter(Employee.id == emp_id).first()
            if match.is_deleted:
                # GAP-FIX: Allow re-activation during explicit employee ingestion (Legajo)
                # This enables 'clean slate and re-import' workflows.
                logger.info(f"ingestion.reactivating_employee: employee_id={emp_id} was deleted but is being re-imported.")
                employee.is_deleted = False
                employee.is_active = True
                employee.status = "active"

            # Merge fields
            ignore_list = match.ignore_fields or []
            for k, v in db_fields.items():
                if v is not None and k not in ignore_list:
                    setattr(employee, k, v)
            
            # Merge extra_fields
            current_extra = employee.extra_fields or {}
            # We enrich the extra_fields structure here as requested
            for k, val in extra_fields.items():
                current_extra[k] = {
                    "value": val,
                    "confidence": extra_meta.get(k, {}).get("confidence", 0),
                    "source": extra_meta.get(k, {}).get("source", "ingestion"),
                    "detected_at": extra_meta.get(k, {}).get("detected_at", datetime.now(timezone.utc).isoformat())
                }
            employee.extra_fields = current_extra
            
            # Ensure profile is completed
            employee.profile_completed = True
            
        else:
            # CREATE
            employee = Employee(organization_id=self.org_id)
            ignore_list = match.ignore_fields or []
            for k, v in db_fields.items():
                if k not in ignore_list:
                    setattr(employee, k, v)
            
            # Enriched extra_fields
            enriched_extra = {}
            for k, val in extra_fields.items():
                enriched_extra[k] = {
                    "value": val,
                    "confidence": extra_meta.get(k, {}).get("confidence", 0),
                    "source": extra_meta.get(k, {}).get("source", "ingestion"),
                    "detected_at": extra_meta.get(k, {}).get("detected_at", datetime.now(timezone.utc).isoformat())
                }
            employee.extra_fields = enriched_extra
            employee.profile_completed = True
            
            # Generation of Invite Token (Phase 2 Hardening)
            import secrets
            from datetime import timedelta
            employee.status = EmployeeStatus.pre_registered
            employee.invite_token = secrets.token_urlsafe(32)
            employee.invite_token_expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            
            # Safety net: Ensure first_name is NOT NULL to avoid DB crash
            if not getattr(employee, "first_name", None):
                employee.first_name = "Empleado"
                logger.warning(f"{self._ctx} INGESTION_FALLBACK: Assigned placeholder name to employee {employee.dni}")
            if not getattr(employee, "last_name", None):
                employee.last_name = str(employee.dni or "Desconocido")
            
            self.db.add(employee)

        self.db.flush() # Get ID and verify constraints
        
        # Side Effects: Re-link receipts
        self._link_orphan_receipts(employee, record.db_fields.get("dni"))
        
        return employee

    def _link_orphan_receipts(self, employee: Employee, dni: str):
        """Auto-links receipts that match the DNI of the new/updated employee."""
        if not dni: return
        
        # Use existing logic from api/employees.py if possible, or replicate here
        # For simplicity and isolation, we replicate but keep it clean
        from payroll_core import SIGNATURE_MODE, create_signature_request
        
        res = self.db.execute(
            text("""
                UPDATE payroll_receipts
                SET employee_id = :emp, 
                    status = (CASE 
                        WHEN :sig_mode = 'dual' AND employer_signed_at IS NULL THEN 'pending_employer_signature'
                        ELSE 'pending_employer_signature'
                    END)::receipt_status
                WHERE organization_id = :org
                  AND employee_id IS NULL
                  AND (extracted_fields->>'dni' = :dni OR extracted_fields->>'document' = :dni)
                RETURNING id
            """),
            {"emp": str(employee.id), "org": self.org_id, "dni": dni, "sig_mode": SIGNATURE_MODE}
        ).fetchall()
        
        for r_row in res:
            create_signature_request(self.db, str(r_row.id), self.org_id, str(employee.id))

    def _audit_ingestion(self, employee: Optional[Employee], record, mode: IngestionMode, 
                         match: Optional[MatchingResult], issues: List[ValidationIssue], start_time: float):
        """Generates the Enterprise-Grade Audit Log."""
        exec_time = (time.time() - start_time) * 1000
        
        target_id = str(employee.id) if employee else None
        
        audit_data = {
            "mode": mode.value,
            "result": "SUCCESS" if (employee and not any(iss.level=="error" for iss in issues)) else "FAILED",
            "match": {
                "strategy": "UPDATE" if (match and match.employee_id) else ("CREATE" if (match and match.match_type == "none") else "NONE"),
                "matched_by": match.match_type if match else "none"
            },
            "fields_count": {
                "db": len(record.db_fields),
                "extra": len(record.extra_fields)
            },
            "issues": {
                "errors": [iss.code for iss in issues if iss.level == "error"],
                "warnings": [iss.code for iss in issues if iss.level == "warning"]
            },
            "execution_time_ms": round(exec_time, 2)
        }
        
        actor_type = "system" if not self.author_id or str(self.author_id).strip().lower() == "system" else "admin"
        actor_id = None if not self.author_id or str(self.author_id).strip().lower() == "system" else self.author_id
        audit(self.db, self.org_id, actor_type, actor_id, "EMPLOYEE_INGESTED", 
              target_id, audit_data)
