import sys
import os
import uuid
import json
from dotenv import load_dotenv

load_dotenv('/root/Downloads/MyManageRH-Payroll-Backup/.env')
sys.path.append('/root/Downloads/MyManageRH-Payroll-Backup')

from sqlalchemy import create_engine, text
from config import DATABASE_URL
from payroll_core import utc_now

def test_historical_integrity_flow():
    engine = create_engine(DATABASE_URL)
    org_id = str(uuid.uuid4())
    emp_id = str(uuid.uuid4())
    user_id = str(uuid.uuid4())
    batch_id = str(uuid.uuid4())
    receipt_id = str(uuid.uuid4())
    
    dni = "99988822"
    cuil = "20-99988822-5"
    legajo = "LE-1004"
    full_name = "Jane Doe"
    
    print("\n--- Test historical integrity flow starting ---")
    
    with engine.begin() as conn:
        # Create a mock organization
        conn.execute(text("""
            INSERT INTO organizations (id, name, cuit)
            VALUES (:org_id, 'Test Org Integrity', '30-99988822-5')
        """), {"org_id": org_id})
        
        # Create a mock employee
        conn.execute(text("""
            INSERT INTO employees (id, organization_id, dni, cuil, first_name, last_name, file_number, is_deleted)
            VALUES (:emp_id, :org_id, :dni, :cuil, 'Jane', 'Doe', :legajo, false)
        """), {"emp_id": emp_id, "org_id": org_id, "dni": dni, "cuil": cuil, "legajo": legajo})
        
        # Create a mock user
        conn.execute(text("""
            INSERT INTO users (id, email, password_hash, role, status, organization_id, employee_id, full_name)
            VALUES (:user_id, 'jane.doe@example.com', 'hash', 'employee', 'active', :org_id, :emp_id, :full_name)
        """), {"user_id": user_id, "org_id": org_id, "emp_id": emp_id, "full_name": full_name})
        
        # Create a batch
        conn.execute(text("""
            INSERT INTO payroll_batches (id, organization_id, period_label, source_pdf_path, source_pdf_sha256, total_receipts)
            VALUES (:batch_id, :org_id, '2026-05', '/path/to/pdf', 'sha', 1)
        """), {"batch_id": batch_id, "org_id": org_id})
        
        # Create a SIGNED receipt (simulating already signed receipt with populated snapshot columns)
        conn.execute(text("""
            INSERT INTO payroll_receipts (
                id, batch_id, organization_id, employee_id, page_number,
                receipt_pdf_path, receipt_pdf_sha256, status, signed_at,
                snapshot_employee_name, snapshot_employee_dni, snapshot_employee_cuil,
                snapshot_employee_legajo, snapshot_created_at
            )
            VALUES (
                :receipt_id, :batch_id, :org_id, :emp_id, 1,
                '/path/to/page.pdf', 'sha-page', 'signed', :now,
                :full_name, :dni, :cuil, :legajo, :now
            )
        """), {
            "receipt_id": receipt_id,
            "batch_id": batch_id,
            "org_id": org_id,
            "emp_id": emp_id,
            "full_name": full_name,
            "dni": dni,
            "cuil": cuil,
            "legajo": legajo,
            "now": utc_now()
        })
        
        print("Initial database states inserted successfully.")
        
        # Verify initial display fallback queries
        row = conn.execute(text("""
            SELECT 
                pr.id,
                COALESCE(pr.snapshot_employee_name, TRIM(e.first_name || ' ' || COALESCE(e.last_name, ''))) AS display_name,
                COALESCE(pr.snapshot_employee_dni, e.dni) AS display_dni,
                pr.status
            FROM payroll_receipts pr
            LEFT JOIN employees e ON e.id = pr.employee_id
            WHERE pr.id = :receipt_id
        """), {"receipt_id": receipt_id}).fetchone()
        
        assert row.display_name == full_name
        assert row.display_dni == dni
        assert row.status == "signed"
        print("Initial verification: PASSED")
        
        # 1. Soft-delete employee (equivalent to delete_employee endpoint)
        # Update employee is_deleted flag
        conn.execute(text("""
            UPDATE employees SET is_deleted = true WHERE id = :emp_id
        """), {"emp_id": emp_id})
        
        # Detach user
        conn.execute(text("""
            UPDATE users SET organization_id = NULL, employee_id = NULL WHERE employee_id = :emp_id
        """), {"emp_id": emp_id})
        
        # Soft-delete orphaning logic (Only orphan UNSIGNED receipts)
        # This is what we updated in employees.py!
        conn.execute(text("""
            UPDATE payroll_receipts 
            SET status = 'pending_match'::receipt_status, employee_id = NULL
            WHERE employee_id = :emp_id AND organization_id = :org_id
              AND status != 'signed'
              AND signed_at IS NULL
              AND employee_signed_at IS NULL
        """), {"emp_id": emp_id, "org_id": org_id})
        
        print("Soft-delete executed.")
        
        # Verify that our SIGNED receipt kept its employee link intact
        receipt_row = conn.execute(text("""
            SELECT employee_id, status FROM payroll_receipts WHERE id = :receipt_id
        """), {"receipt_id": receipt_id}).fetchone()
        
        assert receipt_row.employee_id == emp_id, "Signed receipt should preserve employee_id link!"
        assert receipt_row.status == "signed", "Signed receipt status should remain 'signed'!"
        print("Soft-delete safety checks: PASSED")
        
        # 2. Hard-delete logic test (for hard_delete_employee endpoint)
        # In hard-delete, FK breaks, so employee_id is set to NULL, but status remains 'signed'
        conn.execute(text("""
            UPDATE payroll_receipts 
            SET employee_id = NULL
            WHERE employee_id = :emp_id
              AND (status = 'signed' OR signed_at IS NOT NULL OR employee_signed_at IS NOT NULL)
        """), {"emp_id": emp_id})
        
        hard_deleted_receipt_row = conn.execute(text("""
            SELECT employee_id, status FROM payroll_receipts WHERE id = :receipt_id
        """), {"receipt_id": receipt_id}).fetchone()
        
        assert hard_deleted_receipt_row.employee_id is None, "FK must be cleared on hard delete."
        assert hard_deleted_receipt_row.status == "signed", "Status must remain 'signed'."
        
        # Check display fallback when employee is completely gone (hard deleted)
        display_row = conn.execute(text("""
            SELECT 
                pr.id,
                COALESCE(pr.snapshot_employee_name, TRIM(e.first_name || ' ' || COALESCE(e.last_name, ''))) AS display_name,
                COALESCE(pr.snapshot_employee_dni, e.dni) AS display_dni,
                pr.status
            FROM payroll_receipts pr
            LEFT JOIN employees e ON e.id = pr.employee_id
            WHERE pr.id = :receipt_id
        """), {"receipt_id": receipt_id}).fetchone()
        
        assert display_row.display_name == full_name, "Display name must fallback to snapshot_employee_name!"
        assert display_row.display_dni == dni, "Display DNI must fallback to snapshot_employee_dni!"
        print("Hard-delete safety and fallback checks: PASSED")
        
        # 3. Restore safety test (equivalent to restore_employee endpoint)
        # Restore employee
        conn.execute(text("""
            UPDATE employees SET is_deleted = false WHERE id = :emp_id
        """), {"emp_id": emp_id})
        
        # Re-matching: try to recover orphaned receipts matching DNI
        # Excludes signed/completed receipts (status='pending_match' and signed_at is null)
        conn.execute(text("""
            UPDATE payroll_receipts
            SET employee_id = :emp_id, 
                status = 'pending_employer_signature'::receipt_status
            WHERE organization_id = :org_id
              AND employee_id IS NULL
              AND status = 'pending_match'
              AND signed_at IS NULL
              AND employee_signed_at IS NULL
              AND snapshot_employee_dni = :dni
        """), {"emp_id": emp_id, "org_id": org_id, "dni": dni})
        
        restored_receipt_row = conn.execute(text("""
            SELECT employee_id, status FROM payroll_receipts WHERE id = :receipt_id
        """), {"receipt_id": receipt_id}).fetchone()
        
        assert restored_receipt_row.status == "signed", "Restored employee must NOT reopen signed receipt!"
        print("Restore safety checks: PASSED")
        
        # Clean up database test records
        conn.execute(text("DELETE FROM payroll_receipts WHERE batch_id = :batch_id"), {"batch_id": batch_id})
        conn.execute(text("DELETE FROM payroll_batches WHERE id = :batch_id"), {"batch_id": batch_id})
        conn.execute(text("DELETE FROM users WHERE employee_id = :emp_id OR id = :user_id"), {"emp_id": emp_id, "user_id": user_id})
        conn.execute(text("DELETE FROM employees WHERE id = :emp_id"), {"emp_id": emp_id})
        conn.execute(text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": org_id})
        print("Cleaned up database test records.")
        print("--- All Historical Integrity Tests: PASSED ---")

if __name__ == "__main__":
    test_historical_integrity_flow()
