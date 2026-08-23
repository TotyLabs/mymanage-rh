"""
Legajo Matching System â€” identifies existing employees in the DB.

Strategy:
1. Primary: Match by (organization_id, dni).
2. Secondary: Match by (organization_id, cuil).

Conflict:
- If DNI finds Emp A and CUIL finds Emp B -> CRITICAL CONFLICT.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session
from models import Employee, ImportMode, PlannedAction

logger = logging.getLogger(__name__)


@dataclass
class MatchingResult:
    employee_id: Optional[str] = None
    match_type: str = "none"  # none | dni | cuil | legajo | conflict
    is_deleted: bool = False
    conflict_details: Optional[str] = None
    ignore_fields: List[str] = None
    inferred_legajo: Optional[str] = None # NEW: Legajo found in DB but missing in Excel


class MatchingService:
    def __init__(self, db: Session):
        self.db = db

    def find_match(self, organization_id: str, dni: str, cuil: str, file_number: str = None) -> MatchingResult:
        """
        Executes the matching strategy.
        Note: identifiers must be normalized strings.
        """
        match_dni = None
        match_cuil = None
        match_legajo = None

        if dni:
            match_dni = self.db.query(Employee).filter(
                Employee.organization_id == organization_id,
                Employee.dni == dni
            ).first()

        if cuil:
            match_cuil = self.db.query(Employee).filter(
                Employee.organization_id == organization_id,
                Employee.cuil == cuil
            ).first()
            
        if file_number:
            match_legajo = self.db.query(Employee).filter(
                Employee.organization_id == organization_id,
                Employee.file_number == str(file_number)
            ).first()

        # 1. Identity Anchors (DNI + CUIL)
        strong_match = match_dni or match_cuil
        
        # 2. Excel Legajo Handling & Conflict Detection
        res = MatchingResult()
        
        if strong_match:
            res.employee_id = strong_match.id
            res.is_deleted = bool(getattr(strong_match, "is_deleted", False))
            res.match_type = "dni" if match_dni else "cuil"
            
            db_legajo = getattr(strong_match, "file_number", None)
            
            if file_number:
                # 🥇 Rule: Authoritative Identity Match
                if db_legajo and str(db_legajo) != str(file_number):
                    # ⚠️ Rule: Ignore Excel legajo if mismatch with DB Truth
                    msg = (f"LEG_MISMATCH_IGNORED: El bloque indica Legajo '{file_number}', "
                           f"pero la identidad (DNI/CUIL) ya está vinculada al Legajo '{db_legajo}' en la DB. "
                           f"Usando Verdad de DB y descartando dato de Excel.")
                    logger.warning(msg)
                    res.ignore_fields = ["file_number"]
                    # Keep the record valid, just ignore the field
                
                # Check if this Excel legajo is ALREADY used by someone else
                elif match_legajo and match_legajo.id != strong_match.id:
                    msg = (f"IDENTITY_CONFLICT: El Legajo '{file_number}' ya pertenece al ID {match_legajo.id}, "
                           f"pero el DNI/CUIL apunta al ID {strong_match.id}. Esto requiere revisión manual.")
                    logger.error(msg)
                    return MatchingResult(match_type="conflict", conflict_details=msg)
            else:
                # 🥈 Rule: Inferred from Identity
                if db_legajo:
                    res.inferred_legajo = str(db_legajo)
                    logger.info(f"MATCHING_INFO: Legajo '{db_legajo}' inferred from identity for ID {strong_match.id}")
        
        elif match_legajo:
            # Match ONLY by Legajo (no DNI/CUIL found)
            res.employee_id = match_legajo.id
            res.match_type = "legajo"
            res.is_deleted = bool(getattr(match_legajo, "is_deleted", False))
        else:
            return MatchingResult(match_type="none")

        return res


class UpsertPlanner:
    """
    Decides the final 'planned_action' (insert, update, skip) based on 
    match results, import mode, and validation.
    """
    
    @staticmethod
    def plan_action(match: MatchingResult, 
                    import_mode: ImportMode, 
                    is_invalid: bool) -> str:
        
        if is_invalid:
            return "invalid"
            
        if match.match_type == "conflict":
            return "invalid" # Conflicts block the row

        if match.match_type == "none":
            # New employee
            return "insert"
        else:
            # Match found
            if import_mode == ImportMode.replace:
                return "update"
            else:
                # Default for 'merge': update existing data
                return "update"
                # If we had a 'skip_existing' mode, we'd use 'skip' here.
