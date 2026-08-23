"""
Legajo Import Service — orchestrates the full semantic ingestion flow.
"""

import hashlib
import logging
import os
from datetime import datetime
from typing import List, Optional, Any, Dict

from sqlalchemy.orm import Session
from models import ImportJob, ImportJobRow, ImportJobStatus, ImportMode
from .parsers import ParserFactory
from .schema_manager import SchemaManager, COLUMN_TO_PATH
from .normalizer import Normalizer
from .validator import Validator
from .ingestion import IngestionService, IngestionMode
from .canonical import CanonicalEmployeeRecord

logger = logging.getLogger(__name__)

class ImportService:
    def __init__(self, db: Session):
        self.db = db
        # Internal components (still exposed if needed, but primary is ingestion_service)
        self.schema_manager = SchemaManager(db)
        self.normalizer = Normalizer(self.schema_manager)
        self.validator = Validator(self.schema_manager)

    def create_import_job(self, organization_id: str, user_id: Optional[str], 
                          filename: str, file_content: bytes,
                          import_mode: ImportMode = ImportMode.merge) -> ImportJob:
        file_sha256 = hashlib.sha256(file_content).hexdigest()
        existing = self.db.query(ImportJob).filter(
            ImportJob.organization_id == organization_id,
            ImportJob.file_sha256 == file_sha256
        ).first()

        if existing:
            return existing

        job = ImportJob(
            organization_id=organization_id,
            created_by_user_id=user_id,
            source_type=os.path.splitext(filename)[1].lower().replace(".", ""),
            operation_type="preview",
            original_filename=filename,
            file_sha256=file_sha256,
            import_mode=import_mode,
            status=ImportJobStatus.uploaded
        )
        self.db.add(job)
        self.db.flush()
        if not job.duplicate_group_id: 
            job.duplicate_group_id = job.id
        self.db.commit()
        return job

    def _evaluate_sheet(self, sheet_name: str, raw_grid: List[List[Any]]) -> int:
        """
        Sheet Selection Engine (Phase 19): 
        Intelligently scores a sheet to determine if it contains actual employee data.
        """
        score = 0
        name_lower = sheet_name.lower()
        
        # 1. Penalties for obvious non-data sheets
        if any(bad in name_lower for bad in ["normas", "instrucciones", "anses", "form 572", "siradig", "modelo"]):
            score -= 50
            
        found_fields = set()
        long_text_penalties = 0
        
        # 2. Evaluate Cell Content Density (first 100 rows, 20 columns)
        for row in raw_grid[:100]:
            for cell in row[:20]:
                if not cell or str(cell).strip() == "": continue
                str_cell = str(cell).strip().lower()
                
                if len(str_cell) > 100:
                    long_text_penalties += 1
                    
                # 🥇 CRITICAL FIELDS
                if "dni" in str_cell or "documento" in str_cell:
                    if "dni" not in found_fields:
                        score += 50
                        found_fields.add("dni")
                elif "cuil" in str_cell or "cuit" in str_cell:
                    if "cuil" not in found_fields:
                        score += 50
                        found_fields.add("cuil")
                        
                # 🥈 KEY FIELDS
                elif "nombre" in str_cell or "apellido" in str_cell:
                    if "nombre_apellido" not in found_fields:
                        score += 20
                        found_fields.add("nombre_apellido")
                elif "ingreso" in str_cell or "fecha de alta" in str_cell:
                    if "ingreso" not in found_fields:
                        score += 10
                        found_fields.add("ingreso")
                        
                # 🥉 DENSITY & NUMERIC SIGNALS
                elif "email" in str_cell or "correo" in str_cell or "direccion" in str_cell or "telefono" in str_cell:
                    score += 2
                
                # Numeric signals (IDs like DNI/CUIL often have 7-11 digits)
                elif str_cell.isdigit() and 7 <= len(str_cell) <= 11:
                    score += 5
                
        # Baseline score for explicit TxtParser results if they contain data
        if name_lower == "text" and len(raw_grid) > 0 and score < 50:
            score = 100
                    
        score -= (long_text_penalties * 20)
        return score

    def process_file_to_preview(self, job_id: str, file_path: str) -> ImportJob:
        job = self.db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job: raise ValueError(f"Job {job_id} not found.")

        job.status = ImportJobStatus.importing
        job.started_at = datetime.utcnow()
        # 0. IDEMPOTENCY: Clear existing rows if this job is being re-processed
        self.db.query(ImportJobRow).filter(ImportJobRow.import_job_id == job.id).delete()
        self.db.flush()

        from .matching import MatchingService, UpsertPlanner
        matcher_svc = MatchingService(self.db)
        planner = UpsertPlanner()

        try:
            parser = ParserFactory.get_parser(job.original_filename)
            
            # 1. Dynamic Schema & Multi-Sheet Discovery
            self.schema_manager.discover_schema()
            
            sheets = parser.get_raw_sheets(file_path)
            
            # --- PHASE 19: SHEET SELECTION ENGINE ---
            best_sheet_name = None
            best_raw_rows = []
            best_engine_score = -9999
            
            for sheet_name, raw_rows in sheets.items():
                if not raw_rows: continue
                sheet_score = self._evaluate_sheet(sheet_name, raw_rows)
                logger.debug(f"[IMPORT {job.id}] Sheet Selection Engine evaluated '{sheet_name}': {sheet_score} points")
                
                if sheet_score > best_engine_score:
                    best_engine_score = sheet_score
                    best_sheet_name = sheet_name
                    best_raw_rows = raw_rows
                    
            if best_engine_score < 40 or not best_sheet_name:
                raise ValueError("No se detectó ninguna pestaña con datos de empleado válidos. Asegúrese de incluir DNI, CUIL o Nombre.")
                
            logger.info(f"[IMPORT {job.id}] Sheet Selection Engine selected '{best_sheet_name}' with {best_engine_score} points.")
            
            # 2. Detect Tabular vs Form Mode on BEST sheet only
            best_header_idx, best_col_mapping, best_col_confidence, best_header_labels = self.normalizer.detect_header_row(best_raw_rows)
            tabular_score = sum(best_col_confidence.values()) if best_col_confidence else 0

            # Form Mode Detection
            is_form_mode = best_header_idx == -1 or len(best_col_mapping) < 4 or tabular_score < 300

            if is_form_mode:
                logger.warning(f"[IMPORT {job.id}] FORM_MODE activated on sheet '{best_sheet_name}' (max rows: {len(best_raw_rows)}). Tabular score was {tabular_score}.")
                from .form_parser import FormParser
                form_parser = FormParser(job_id=str(job.id))
                final_rows = form_parser.extract(best_raw_rows)
                logger.info(f"[IMPORT {job.id}] FORM_MODE activated: {len(final_rows)} records detected on sheet '{best_sheet_name}'.")
                best_header_idx = -1
                self.normalizer.job_id = str(job.id)
                self.normalizer._ctx = f"[IMPORT {job.id}]"
                self.normalizer.set_mapping({}, {})
            else:
                logger.info(f"[IMPORT {job.id}] TABULAR_MODE activated on sheet '{best_sheet_name}' (tabular header score: {tabular_score}).")
                # 3. Dynamic Required Field Enforcement (e.g. DNI)
                required_paths = ["identity.dni"] # Always core if exists
                for path in required_paths:
                    col = self.schema_manager.get_column_for_path(path)
                    if col in self.schema_manager.columns:
                        if path not in best_col_mapping.values():
                            raise ValueError(f"Error crítico en pestaña '{best_sheet_name}': No se encontró la columna '{col}' la cual es obligatoria.")

                # 3. Final Mapping Configuration (canonical keys come from parser)
                self.normalizer.job_id = str(job.id)
                self.normalizer._ctx = f"[IMPORT {job.id}]"
                self.normalizer.set_mapping({}, {})

                # 4. Parse Data Rows using column-index canonical mapping
                final_rows = parser.parse(
                    file_path,
                    sheet_name=best_sheet_name,
                    header_row=best_header_idx,
                    col_mapping=best_col_mapping,
                    raw_rows=best_raw_rows,
                )
                
            job.total_rows = len(final_rows)

            # Store mapping log for transparency
            job.error_summary_json = {
                "mode": "FORM" if is_form_mode else "TABULAR",
                "sheet": best_sheet_name,
                "mapping_log": [
                    {
                        "col": col_idx,
                        "header": best_header_labels.get(col_idx, ""),
                        "field": field_path,
                        "confidence": best_col_confidence.get(col_idx, 0),
                    }
                    for col_idx, field_path in best_col_mapping.items()
                ]
            }

            valid_count = 0
            invalid_count = 0
            warning_count = 0
            inserted_count = 0
            updated_count = 0

            # 5. Pipeline per row via Unified Nucleus
            ingestion_svc = IngestionService(self.db, job.organization_id, str(job.created_by_user_id), job_id=str(job.id))
            
            # 🔥 SYNC MAPPING TO NUCLEUS
            ingestion_svc.normalizer.set_mapping(self.normalizer.active_mapping, self.normalizer.active_confidence)
            
            for i, raw in enumerate(final_rows):
                source_num = best_header_idx + i + 2 # 1-indexed, skipping headers
                
                # The Nucleus handles Normalize -> Validate -> Match
                result = ingestion_svc.process_row(raw, mode=IngestionMode.IMPORT, source_row_num=source_num, is_preview=True)
                
                is_invalid = result.status == "failed"
                has_warnings = len([iss for iss in result.issues if iss.level == "warning"]) > 0
                
                if is_invalid: invalid_count += 1
                else: 
                    valid_count += 1
                    strat = result.match_info.get("strategy", "").upper()
                    if strat == "INSERT": inserted_count += 1
                    elif strat in ["UPDATE", "REACTIVATE"]: updated_count += 1
                    
                if has_warnings: warning_count += 1

                # Row Snapshot
                # We extract what we need from the result
                dni_cuil = (result.record.db_fields.get("dni") or result.record.db_fields.get("cuil")) if result.record else None
                
                row_snapshot = ImportJobRow(
                    import_job_id=job.id,
                    source_row_number=source_num,
                    external_key=str(dni_cuil) if dni_cuil else "-",
                    raw_data_json=raw,
                    normalized_data_json=result.record.to_dict() if result.record else {}, # Authoritative data ONLY
                    validation_errors_json=[iss.message for iss in result.issues if iss.level == "error"],
                    validation_warnings_json=[iss.message for iss in result.issues if iss.level == "warning"],
                    planned_action=result.match_info.get("strategy", "skip").lower(),
                    matching_result_json=result.match_info, # Perspective/Reason
                    resolution_status="invalid" if is_invalid else "pending",
                    matched_employee_id=result.employee_id
                )
                self.db.add(row_snapshot)

                if (i + 1) % 100 == 0: self.db.flush()

            # Final summary logs
            ingestion_svc.normalizer.log_missing_columns_summary()
            
            job.valid_rows = valid_count
            job.invalid_rows = invalid_count
            job.warning_rows = warning_count
            job.inserted_count = inserted_count
            job.updated_count = updated_count
            job.status = ImportJobStatus.preview_ready
            job.finished_at = datetime.utcnow()
            self.db.commit()
            return job

        except Exception as e:
            logger.exception(f"[IMPORT {job.id}] Error processing import job {job_id}")
            self.db.rollback()
            job.status = ImportJobStatus.failed
            # Merge existing error info if any
            err_info = job.error_summary_json or {}
            err_info["exception"] = str(e)
            job.error_summary_json = err_info
            self.db.commit()
            raise

    def execute_job(self, job_id: str, user_id: Optional[str], selected_rows: Optional[List[int]] = None) -> Dict[str, Any]:
        """
        Execute the import for selected rows.
        Hardened: includes index validation.
        """
        job = self.db.query(ImportJob).filter(ImportJob.id == job_id).first()
        if not job: raise ValueError("ImportJob not found")

        if selected_rows is None and isinstance(job.metadata_json, dict):
            selected_rows = job.metadata_json.get("execute_selection")

        if job.status == ImportJobStatus.imported:
            raise ValueError("Este trabajo ya fue ejecutado previamente.")

        if job.status not in (
            ImportJobStatus.preview_ready,
            ImportJobStatus.failed,
            ImportJobStatus.queued,
            ImportJobStatus.processing,
        ):
            raise ValueError(f"El trabajo está en un estado inválido para ejecución: {job.status}")

        job.status = ImportJobStatus.importing
        job.started_at = job.started_at or datetime.utcnow()
        self.db.flush()

        rows = self.db.query(ImportJobRow).filter(ImportJobRow.import_job_id == job_id).order_by(ImportJobRow.source_row_number).all()
        
        # 1. Selection Filtering (GAP-HARDENED)
        if selected_rows is not None:
            # We assume selected_rows are indices from the preview (0-indexed)
            # Find which rows to process
            invalid_indices = [i for i in selected_rows if i < 0 or i >= len(rows)]
            if invalid_indices:
                raise ValueError(f"Índices de fila inválidos: {invalid_indices}")
            
            target_rows = [rows[i] for i in selected_rows]
        else:
            target_rows = rows

        inserted_count = 0
        updated_count = 0
        invalid_count = 0
        
        from services.legajo.ingestion import IngestionService, IngestionMode
        ingestion_svc = IngestionService(self.db, job.organization_id, user_id)
        
        for row in target_rows:
            if row.resolution_status != "invalid" and row.planned_action in ["insert", "update", "reactivate"]:
                try:
                    res = ingestion_svc.process_row(row.raw_data_json, mode=IngestionMode.IMPORT, source_row_num=row.source_row_number, is_preview=False)
                    if res.status != "failed":
                        if row.planned_action == "insert": inserted_count += 1
                        else: updated_count += 1 # reactivate and update both count here
                        row.resolution_status = "executed"
                        row.matched_employee_id = res.employee_id
                    else:
                        row.resolution_status = "invalid"
                        row.validation_errors_json = [iss.message for iss in res.issues if iss.level == "error"]
                        invalid_count += 1
                except Exception as e:
                    row.resolution_status = "invalid"
                    row.validation_errors_json = [str(e)]
                    invalid_count += 1
            else:
                row.resolution_status = "skipped" if row.planned_action == "skip" else "invalid"
                
        # Optional: Mark rows NOT in target_rows as 'skipped' / 'deselected'
        if selected_rows is not None:
            processed_ids = {r.id for r in target_rows}
            for r in rows:
                if r.id not in processed_ids:
                    r.resolution_status = "deselected"

        job.status = ImportJobStatus.imported
        self.db.commit()
        return {"inserted": inserted_count, "updated": updated_count, "invalid": invalid_count}

    def get_execution_summary(self, job_id: str, selected_rows: Optional[List[int]] = None) -> Dict[str, Any]:
        """Calculates metrics for a subset of rows before execution."""
        rows = self.db.query(ImportJobRow).filter(ImportJobRow.import_job_id == job_id).order_by(ImportJobRow.source_row_number).all()
        
        if selected_rows is not None:
             target_rows = [rows[i] for i in selected_rows if 0 <= i < len(rows)]
        else:
             target_rows = rows
             
        new_count = sum(1 for r in target_rows if r.planned_action == "insert" and r.resolution_status != "invalid")
        update_count = sum(1 for r in target_rows if r.planned_action in ["update", "reactivate"] and r.resolution_status != "invalid")
        
        return {
            "total_selected": len(target_rows),
            "new_count": new_count,
            "update_count": update_count,
            "invalid_in_selection": sum(1 for r in target_rows if r.resolution_status == "invalid")
        }

    def fetch_export_data(self, organization_id: str) -> List[CanonicalEmployeeRecord]:
        """
        Fetches all employees for an organization and converts them to CanonicalEmployeeRecord.
        """
        from models import Employee
        employees = self.db.query(Employee).filter(
            Employee.organization_id == organization_id,
            Employee.is_deleted == False
        ).all()
        
        results = []
        for emp in employees:
            rec = CanonicalEmployeeRecord()
            
            # Map columns to blocks
            for col in emp.__table__.columns:
                name = col.name
                if name in ["id", "organization_id", "created_at", "updated_at", "extra_fields", "invite_token", "invite_token_expires_at", "profile_completed", "is_active", "status_reason"]:
                    continue
                
                val = getattr(emp, name)
                path = COLUMN_TO_PATH.get(name)
                
                if path:
                    block_name, field_name = path.split(".")
                    block = getattr(rec, block_name)
                    setattr(block, field_name, val)
                else:
                    # Dynamic/Custom DB column not in COLUMN_TO_PATH
                    rec.db_fields[name] = val
            
            # Add extra_fields from JSONB
            if emp.extra_fields:
                rec.extra_fields.update(emp.extra_fields)
                
            results.append(rec)
        return results
