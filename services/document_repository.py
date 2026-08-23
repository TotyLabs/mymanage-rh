import logging
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import text
from payroll_core import safe_transaction

logger = logging.getLogger("dircom.payroll")

class DocumentRepository:
    """
    Abstraction layer to handle bimodal receipt access.
    Supports both legacy 'payroll_receipts' and new 'receipts' tables.
    """

    @staticmethod
    def get_document(db: Session, doc_id: str, for_update: bool = False) -> Optional[Dict[str, Any]]:
        """
        Fetches a document from either table and returns a normalized dictionary.
        """
        lock_clause = "FOR UPDATE OF r" if for_update else ""

        # 1. Try new architecture (receipts)
        row = db.execute(text(f"""
            SELECT 
                r.id, r.company_id AS organization_id, r.user_id AS employee_id,
                r.file_path AS path, r.file_hash AS hash, r.status, 
                r.receipt_metadata AS metadata, r.is_signed, r.document_locked,
                r.processing_signature, r.requires_employer, r.requires_employee,
                r.verification_id, r.batch_id, r.employer_signed_at, r.employee_signed_at,
                r.signed_at,
                (e.first_name || ' ' || e.last_name) AS full_name, e.cuil, e.dni, e.email,
                o.name AS organization_name, o.logo_path, o.cuit
            FROM receipts r
            LEFT JOIN users u ON r.user_id = u.id
            LEFT JOIN employees e ON LOWER(TRIM(u.email)) = LOWER(TRIM(e.email)) AND u.organization_id = e.organization_id
            JOIN organizations o ON r.company_id = o.id
            WHERE r.id = :id AND r.is_deleted = false
            {lock_clause}
        """), {"id": doc_id}).mappings().fetchone()

        if row:
            res = dict(row)
            res["source"] = "enterprise"
            return res

        # 2. Try legacy architecture (payroll_receipts)
        row = db.execute(text(f"""
            SELECT 
                r.id, r.organization_id, r.employee_id,
                r.receipt_pdf_path AS path, r.receipt_pdf_sha256 AS hash, r.status,
                r.extracted_fields AS metadata, r.document_locked,
                r.processing_signature, r.requires_employer, r.requires_employee,
                r.verification_id, r.batch_id, r.page_number, r.employer_signed_at, r.employee_signed_at,
                r.signed_at,
                (e.first_name || ' ' || e.last_name) AS full_name, e.cuil, e.dni, e.email,
                o.name AS organization_name, o.logo_path, o.cuit
            FROM payroll_receipts r
            LEFT JOIN employees e ON r.employee_id = e.id
            JOIN organizations o ON r.organization_id = o.id
            WHERE r.id = :id AND r.is_deleted = false
            {lock_clause}
        """), {"id": doc_id}).mappings().fetchone()

        if row:
            res = dict(row)
            res["source"] = "payroll"
            # Backward compat: payroll_receipts might not have is_signed, infer it
            res["is_signed"] = (res["status"] == "signed" or res["document_locked"])
            return res

        return None

    @staticmethod
    def update_document(db: Session, doc_id: str, source: str, **kwargs) -> bool:
        """
        Updates a document in the specified table using normalized field mapping.
        """
        if source == "enterprise":
            table = "receipts"
            mapping = {
                "organization_id": "company_id",
                "employee_id": "user_id",
                "path": "file_path",
                "hash": "file_hash",
                "metadata": "receipt_metadata",
            }
        else:
            table = "payroll_receipts"
            mapping = {
                "path": "receipt_pdf_path",
                "hash": "receipt_pdf_sha256",
                "metadata": "extracted_fields",
            }

        set_parts = []
        params = {"id": doc_id}
        for k, v in kwargs.items():
            db_col = mapping.get(k, k)
            if k == "metadata" and isinstance(v, dict):
                import json
                set_parts.append(f"{db_col} = COALESCE(CAST({db_col} AS JSONB), '{{}}'::jsonb) || CAST(:{k} AS JSONB)")
                params[k] = json.dumps(v)
            else:
                set_parts.append(f"{db_col} = :{k}")
                params[k] = v

        if not set_parts:
            return False

        sql = f"UPDATE {table} SET {', '.join(set_parts)} WHERE id = :id"
        db.execute(text(sql), params)
        return True

    @staticmethod
    def set_processing_flag(db: Session, doc_id: str, source: str, value: bool):
        """
        Utility specifically for the high-concurrency signature flag.
        """
        table = "receipts" if source == "enterprise" else "payroll_receipts"
        db.execute(text(f"UPDATE {table} SET processing_signature = :v WHERE id = :id"), {"v": value, "id": doc_id})
