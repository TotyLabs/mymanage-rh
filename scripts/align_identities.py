import os
import sys
import re
import fitz
import json
from sqlalchemy import create_engine, text
from datetime import datetime

# Add root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from payroll_core import hash_password, normalize_org_name, get_db

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("Error: DATABASE_URL not set.")
    exit(1)
engine = create_engine(DATABASE_URL)

def extract_from_pdf(pdf_path):
    print(f"Parsing {pdf_path} (block-based)...")
    doc = fitz.open(pdf_path)
    identities = {}
    
    EXCLUDE = [
        "RECIBO", "ORIGINAL", "DUPLICADO", "TRIPLICADO", "EMPLEADOR", "EMPLEADO", 
        "DETALLE", "TOTAL", "FIRMA", "DOMICILIO", "CATEGORIA", "CONCEPTO", 
        "LUGAR", "FECHA", "BASICO", "JORNAL", "LAPSO", "HABERES", "DESCUENTOS", 
        "APELLIDO", "NOMBRE", "LEGAJO", "PERIODO", "LIQUIDACION", "CUIL", "DNI", 
        "OFICIAL", "ESPECIALIZADO", "AYUDANTE", "PEON", "CAPATAZ", "MEDIO", "COLECT"
    ]

    for page in doc:
        blocks = page.get_text("blocks")
        for i, b in enumerate(blocks):
            text = b[4].strip()
            
            # Detect CUIL
            cuil_match = re.search(r'(\d{2}-\d{8}-\d|\d{11})', text)
            if cuil_match:
                cuil = cuil_match.group(0).replace("-", "")
                dni = cuil[2:10]
                
                # Look up for a name (usually in previous blocks)
                found_name = None
                for j in range(i-1, i-6, -1):
                    if j < 0: break
                    candidate = blocks[j][4].strip()
                    if candidate.isupper() and len(candidate) > 8 and not any(k in candidate for k in EXCLUDE):
                         if re.match(r'^[A-Z\s]+$', candidate) and len(candidate.split()) >= 2:
                             found_name = candidate
                             break
                
                if found_name and dni not in identities:
                    identities[dni] = {
                        "full_name": found_name,
                        "dni": dni,
                        "cuil": cuil,
                        "org": "ACME Payroll SA"
                    }
    
    return list(identities.values())

def align_database(identities):
    report = {
        "detected": len(identities),
        "created": 0,
        "corrected": 0,
        "matched": 0,
        "errors": []
    }
    
    db = next(get_db())
    
    for iden in identities:
        dni = iden['dni']
        name = iden['full_name']
        cuil = iden['cuil']
        org_name = iden['org']
        
        print(f"Syncing: {name} (DNI: {dni})...")
        
        try:
            # Get organization
            org = db.execute(text("SELECT id FROM organizations WHERE name = :name"), {"name": org_name}).fetchone()
            if not org:
                report["errors"].append(f"Organization {org_name} not found for {name}")
                continue
            
            org_id = org.id
            
            # Check if employee exists
            emp = db.execute(text("""
                SELECT id, (first_name || ' ' || last_name) as full_name, cuil, status 
                FROM employees 
                WHERE dni = :dni AND organization_id = :org_id
            """), {"dni": dni, "org_id": org_id}).fetchone()
            
            if emp:
                # Validate name and CUIL
                updates = {}
                if emp.full_name != name:
                    name_parts = name.split(None, 1)
                    updates["first_name"] = name_parts[0]
                    updates["last_name"] = name_parts[1] if len(name_parts) > 1 else ""
                if emp.cuil != cuil:
                    updates["cuil"] = cuil
                
                if updates:
                    update_stmt = ", ".join([f"{k} = :{k}" for k in updates.keys()])
                    db.execute(text(f"UPDATE employees SET {update_stmt} WHERE id = :id"), {**updates, "id": emp.id})
                    report["corrected"] += 1
                    print(f"  - Corrected: {updates}")
                else:
                    report["matched"] += 1
                    print(f"  - Matched.")
            else:
                # Create missing
                name_parts = name.split(None, 1)
                fname = name_parts[0]
                lname = name_parts[1] if len(name_parts) > 1 else ""
                db.execute(text("""
                    INSERT INTO employees (organization_id, first_name, last_name, dni, cuil, status, profile_completed)
                    VALUES (:org_id, :fname, :lname, :dni, :cuil, 'pre_registered', false)
                """), {"org_id": org_id, "fname": fname, "lname": lname, "dni": dni, "cuil": cuil})
                report["created"] += 1
                print(f"  - Created missing employee.")
            
            db.commit()
            
        except Exception as e:
            db.rollback()
            report["errors"].append(f"Error syncing {name}: {str(e)}")
            
    return report

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python align_identities.py <path_to_pdf>")
        sys.exit(1)
        
    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found.")
        sys.exit(1)
        
    identities = extract_from_pdf(pdf_path)
    # Filter out junk
    identities = [i for i in identities if i['dni'].isdigit() and len(i['dni']) >= 7]
    
    if not identities:
        print("No identities found in document.")
        # Fallback to the one we know is in the PDF based on manual inspection if needed
        # But let's see what the script gets first.
    
    report = align_database(identities)
    print("\n--- Final Alignment Report ---")
    print(json.dumps(report, indent=2))
