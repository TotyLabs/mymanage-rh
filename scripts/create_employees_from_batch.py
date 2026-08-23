"""
Script para crear empleados automÃ¡ticamente a partir de DNIs extraÃ­dos en lotes.
Ãštil para casos donde los DNIs estÃ¡n en los recibos pero no hay registros de empleados.

Estrategia: "Auto-create Controlado"
- Crea empleados en estado "pending_verification"
- DNI confirmado (extraÃ­do del recibo)
- Nombre placeholder: "[Pendiente verificar] DNI XXXXXXX"
- Admin luego valida y completa datos en UI
- Estado cambia a "active" cuando se confirma

Uso:
    # Auto-crear desde DNIs extraÃ­dos en batch
    python scripts/create_employees_from_batch.py --organization-id <org-id> --batch-id <batch-id>
    
    # Auto-crear desde todos los batches de la org
    python scripts/create_employees_from_batch.py --organization-id <org-id>
    
    # Importar desde CSV (crea con estado pre_registered)
    python scripts/create_employees_from_batch.py --organization-id <org-id> --csv-file employees.csv
"""

import sys
import os
import argparse
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from payroll_core import get_db, logger, safe_transaction
from sqlalchemy import text

def create_employees_from_batch(organization_id: str, batch_id: str = None) -> dict:
    """
    Crea empleados automÃ¡ticamente a partir de DNIs extraÃ­dos en recibos.
    
    Args:
        organization_id: ID de la organizaciÃ³n
        batch_id: ID del batch (si es None, procesa todos los batches de la org)
    
    Returns:
        Dict con stats de creaciÃ³n
    """
    db = next(get_db())
    
    stats = {
        "extracted_dnis": 0,
        "created_employees": 0,
        "already_exist": 0,
        "errors": 0,
    }
    
    try:
        # Get all extracted DNIs from receipts that don't have an employee_id
        query = """
            SELECT DISTINCT pr.extracted_fields->>'dni' AS dni
            FROM payroll_receipts pr
            WHERE pr.organization_id = :org
            AND pr.employee_id IS NULL
            AND pr.extracted_fields->>'dni' IS NOT NULL
            AND pr.extracted_fields->>'dni' != ''
        """
        params = {"org": organization_id}
        
        if batch_id:
            query += " AND pr.batch_id = :bid"
            params["bid"] = batch_id
        
        dnis = db.execute(text(query), params).fetchall()
        stats["extracted_dnis"] = len(dnis)
        
        logger.info(f"create_employees.found_dnis count={len(dnis)} org={organization_id}")
        
        for dni_row in dnis:
            dni = dni_row.dni if hasattr(dni_row, 'dni') else dni_row[0]
            
            if not dni or not dni.strip():
                continue
            
            try:
                # Check if employee already exists with this DNI
                existing = db.execute(
                    text("SELECT id FROM employees WHERE organization_id = :org AND dni = :dni"),
                    {"org": organization_id, "dni": dni}
                ).fetchone()
                
                if existing:
                    stats["already_exist"] += 1
                    continue
                
                # Create a basic employee record
                # Use DNI as a default name if we don't have better info
                first_name = f"[Pendiente verificar]"
                last_name = f"DNI {dni}"
                
                with safe_transaction(db):
                    db.execute(
                        text("""
                            INSERT INTO employees (
                                organization_id, first_name, last_name, dni, 
                                status, status_reason, profile_completed, is_active
                            ) VALUES (:org, :fn, :ln, :dni, :status, :reason, :pc, :active)
                        """),
                        {
                            "org": organization_id,
                            "fn": first_name,
                            "ln": last_name,
                            "dni": dni,
                            "status": "pending_verification",
                            "reason": "auto_created_from_batch_dni",
                            "pc": False,
                            "active": True
                        }
                    )
                    stats["created_employees"] += 1
                    logger.debug(f"create_employees.created dni={dni} org={organization_id}")
                    
            except Exception as e:
                stats["errors"] += 1
                logger.warning(f"create_employees.error dni={dni} org={organization_id} err={e}")
        
        db.close()
        return stats
        
    except Exception as e:
        logger.exception("create_employees.bulk_error")
        raise e


def create_employees_from_csv(organization_id: str, csv_file: str) -> dict:
    """
    Crea empleados desde un archivo CSV.
    
    CSV format:
        first_name,last_name,dni
        Juan,PÃ©rez,12345678
        MarÃ­a,GarcÃ­a,87654321
    """
    import csv
    
    db = next(get_db())
    
    stats = {
        "total": 0,
        "created": 0,
        "skipped": 0,
        "errors": 0,
    }
    
    try:
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for i, row in enumerate(reader):
                stats["total"] += 1
                
                try:
                    first_name = (row.get("first_name") or "").strip()
                    last_name = (row.get("last_name") or "").strip()
                    dni = (row.get("dni") or "").strip()
                    
                    if not first_name or not dni:
                        logger.warning(f"create_employees.skip_row row={i+2} missing_fields")
                        stats["skipped"] += 1
                        continue
                    
                    # Check if already exists
                    existing = db.execute(
                        text("SELECT id FROM employees WHERE organization_id = :org AND dni = :dni"),
                        {"org": organization_id, "dni": dni}
                    ).fetchone()
                    
                    if existing:
                        stats["skipped"] += 1
                        continue
                    
                    # Create employee
                    with safe_transaction(db):
                        db.execute(
                            text("""
                                INSERT INTO employees (
                                    organization_id, first_name, last_name, dni, 
                                    status, profile_completed, is_active
                                ) VALUES (:org, :fn, :ln, :dni, :status, :pc, :active)
                            """),
                            {
                                "org": organization_id,
                                "fn": first_name,
                                "ln": last_name or None,
                                "dni": dni,
                                "status": "pre_registered",
                                "pc": False,
                                "active": True
                            }
                        )
                        stats["created"] += 1
                        
                except Exception as e:
                    stats["errors"] += 1
                    logger.warning(f"create_employees.csv_error row={i+2} err={e}")
        
        db.close()
        return stats
        
    except Exception as e:
        logger.exception("create_employees.csv_error")
        raise e


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create employees from batch DNIs or CSV")
    parser.add_argument("--organization-id", required=True, help="Organization ID")
    parser.add_argument("--batch-id", help="Optional batch ID (if None, uses all batches)")
    parser.add_argument("--csv-file", help="CSV file with employee data")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    import logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    
    if args.csv_file:
        logger.info(f"Importing employees from CSV: {args.csv_file}")
        stats = create_employees_from_csv(args.organization_id, args.csv_file)
    else:
        logger.info(f"Creating employees from batch DNIs: org={args.organization_id} batch={args.batch_id}")
        stats = create_employees_from_batch(args.organization_id, args.batch_id)
    
    logger.info(f"Complete: {stats}")
    print(f"\nResults:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
