import os
import json
import uuid
import logging
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
import config
from payroll_core import (
    ALLOWED_STORAGE_DIR, 
    safe_transaction, 
    safe_write_file,
    utc_now
)
from services.encryption_service import (
    EncryptionService,
    KmsError,
    get_encryption_service,
    record_kms_error_event,
)

logger = logging.getLogger("dircom.payroll.documents")

class DocumentIntegrityError(Exception):
    """Raised when on-read hash verification fails."""
    pass

class DocumentService:
    """
    Unified Hub Service for managing non-payroll documents (V4.3).
    Implements structured storage, real-time integrity checks, and lifecycle governance.
    """

    @staticmethod
    def _calculate_file_hash(file_path_or_bytes) -> str:
        """
        Calculates SHA256 hash. Supports both bytes and file paths (chunked reading).
        """
        sha256 = hashlib.sha256()
        if isinstance(file_path_or_bytes, bytes):
            sha256.update(file_path_or_bytes)
        else:
            # Assume file path - read in 64kb chunks
            with open(file_path_or_bytes, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def get_storage_path(doc_type: str, organization_id: str, document_id: str, timestamp: datetime = None) -> Path:
        """Structure: storage/[type]/[org_id]/[year]/[month]/[id]/"""
        ts = timestamp or utc_now()
        year = str(ts.year)
        month = f"{ts.month:02d}"
        base_path = Path(ALLOWED_STORAGE_DIR) / doc_type.lower() / str(organization_id) / year / month / str(document_id)
        return base_path

    @staticmethod
    def save_document(
        db: Session,
        organization_id: str,
        doc_type: str,
        file_bytes: bytes,
        original_filename: str,
        uploaded_by: dict, # {user_id, email, role}
        period_label: str = None,
        custom_metadata: dict = None,
        status: str = "ACTIVE"
    ) -> dict:
        """
        Saves document with Cryptographic Integrity and Audit Context.
        """
        document_id = str(uuid.uuid4())
        now = utc_now()
        status = (status or "ACTIVE").upper()
        
        # 0. Detect MIME and calculate Hash
        mime_type, _ = mimetypes.guess_type(original_filename)
        mime_type = mime_type or "application/octet-stream"
        file_hash = DocumentService._calculate_file_hash(file_bytes)
        
        # 1. Resolve storage path
        base_path = DocumentService.get_storage_path(doc_type, organization_id, document_id, now)
        base_path.mkdir(parents=True, exist_ok=True)
        
        ext = os.path.splitext(original_filename)[1].lower() or ".bin"
        file_name = f"original{ext}"
        full_file_path = base_path / file_name
        
        # 2. Metadata construction (Auditable & Immutable)
        metadata = {
            "document_id": document_id,
            "organization_id": organization_id,
            "doc_type": doc_type,
            "original_filename": original_filename,
            "hash_sha256": file_hash,
            "mime_type": mime_type,
            "size_bytes": len(file_bytes),
            "uploaded_by": {
                "user_id": str(uploaded_by.get("id")),
                "email": uploaded_by.get("email"),
                "role": uploaded_by.get("role")
            },
            "uploaded_at": now.isoformat(),
            "version": 1,
            "custom": custom_metadata or {}
        }
        
        # Add metadata hash for self-verification
        metadata["metadata_hash"] = hashlib.sha256(json.dumps(metadata).encode()).hexdigest()
        
        encryption_metadata = None
        try:
            # 3. File Persistence
            safe_write_file(str(full_file_path), file_bytes)
            if config.APP_ENCRYPTION_ENABLED:
                try:
                    encryption_metadata = get_encryption_service().encrypt_file_in_place(
                        full_file_path,
                        organization_id=str(organization_id),
                        purpose=f"company_document:{doc_type.lower()}",
                        file_id=document_id,
                        plaintext_sha256=file_hash,
                    )
                    metadata["encryption"] = {
                        "file_id": encryption_metadata["file_id"],
                        "algorithm": encryption_metadata["algorithm"],
                        "kms_key_id": encryption_metadata["kms_key_id"],
                        "purpose": encryption_metadata["purpose"],
                    }
                except KmsError as exc:
                    try:
                        record_kms_error_event(
                            db,
                            organization_id=str(organization_id),
                            actor_id=str(uploaded_by.get("id")) if uploaded_by.get("id") else None,
                            actor_type=uploaded_by.get("role") if uploaded_by.get("role") in ("admin", "employee") else "system",
                            file_id=document_id,
                            purpose=f"company_document:{doc_type.lower()}",
                            error_code=str(exc),
                        )
                    except Exception:
                        logger.exception("document.encryption_kms_error_audit_failed")
                    try:
                        full_file_path.unlink(missing_ok=True)
                    except Exception:
                        logger.exception("document.plaintext_cleanup_failed_after_kms_error")
                    raise
            
            meta_path = base_path / "metadata.json"
            metadata.pop("metadata_hash", None)
            metadata["metadata_hash"] = hashlib.sha256(
                json.dumps(metadata, sort_keys=True).encode()
            ).hexdigest()
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            
            # 4. Database Persistence
            with safe_transaction(db):
                db.execute(text("""
                    INSERT INTO company_documents (
                        id, organization_id, doc_type, file_name, base_path, 
                        metadata, period_label, created_at, file_hash, status
                    ) VALUES (
                        :id, :org, :type, :name, :path, 
                        :meta, :period, :created, :hash, :status
                    )
                """), {
                    "id": document_id,
                    "org": organization_id,
                    "type": doc_type,
                    "name": original_filename,
                    "path": str(base_path),
                    "meta": json.dumps(metadata),
                    "period": period_label,
                    "created": now,
                    "hash": file_hash,
                    "status": status,
                })
                if encryption_metadata:
                    get_encryption_service().persist_metadata_and_audit(
                        db,
                        encryption_metadata,
                        actor_id=str(uploaded_by.get("id")) if uploaded_by.get("id") else None,
                        actor_type=uploaded_by.get("role") if uploaded_by.get("role") in ("admin", "employee") else "system",
                    )
            
            logger.info(f"document.saved: id={document_id} status={status} hash={file_hash}")
            return {"id": document_id, "status": status, "hash": file_hash}
            
        except Exception as e:
            try:
                if full_file_path.exists():
                    full_file_path.unlink()
            except Exception:
                logger.exception("document.save_cleanup_failed")
            logger.error(f"document.save_failed: {e}")
            raise Exception(f"Failed to save document: {str(e)}")

    @staticmethod
    def get_document_file(
        db: Session,
        document_id: str,
        organization_id: str,
        actor_id: str = None,
        actor_type: str = "system",
        return_temp_flag: bool = False,
    ) -> tuple:
        """
        Retrieves document with ON-READ INTEGRITY VERIFICATION.
        Returns (Path, OriginalName) or raises DocumentIntegrityError.
        """
        row = db.execute(text("""
            SELECT base_path, file_name, file_hash, status, doc_type
            FROM company_documents
            WHERE id = :id AND organization_id = :org AND status != 'DELETED'
        """), {"id": document_id, "org": organization_id}).fetchone()
        
        if not row:
            if return_temp_flag:
                return None, None, False
            return None, None
            
        base_path = Path(row.base_path)
        files = list(base_path.glob("original.*"))
        if not files:
            if return_temp_flag:
                return None, None, False
            return None, None
            
        file_path = files[0]

        try:
            storage_key = EncryptionService.storage_key(file_path)
            encrypted = db.execute(text("""
                SELECT 1
                FROM file_encryption_metadata
                WHERE organization_id = CAST(:org AS UUID)
                  AND storage_path = :storage_path
                LIMIT 1
            """), {"org": organization_id, "storage_path": storage_key}).fetchone()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
            encrypted = None

        if encrypted:
            temp_path = get_encryption_service().decrypt_file_to_temp(
                db,
                file_path,
                organization_id=str(organization_id),
                actor_id=actor_id,
                actor_type=actor_type,
                purpose=f"company_document:{row.doc_type.lower()}",
                expected_plaintext_sha256=row.file_hash,
                suffix=file_path.suffix,
            )
            if return_temp_flag:
                return temp_path, row.file_name, True
            return temp_path, row.file_name
        
        # --- CRITICAL: REAL-TIME HASH VERIFICATION ---
        current_hash = DocumentService._calculate_file_hash(file_path)
        if current_hash != row.file_hash:
            logger.error(f"INTEGRITY_VIOLATION: document={document_id} expected={row.file_hash} actual={current_hash}")
            raise DocumentIntegrityError(f"Integrity check failed for document {document_id}. File might be corrupted.")

        if return_temp_flag:
            return file_path, row.file_name, False
        return file_path, row.file_name

    @staticmethod
    def update_status(db: Session, document_id: str, organization_id: str, new_status: str):
        """Transitions document lifecycle state."""
        with safe_transaction(db):
            result = db.execute(text("""
                UPDATE company_documents 
                SET status = :status, 
                    updated_at = :now
                WHERE id = :id AND organization_id = :org
            """), {
                "status": new_status.upper(),
                "id": document_id,
                "org": organization_id,
                "now": utc_now()
            })
            if result.rowcount == 0:
                raise Exception("Document not found or access denied")
        logger.info(f"document.status_changed: id={document_id} status={new_status}")
