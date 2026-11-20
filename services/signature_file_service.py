import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

import config
from payroll_core import logger
from services.encryption_service import (
    EncryptionError,
    EncryptionService,
    KmsError,
    get_encryption_service,
    record_kms_error_event,
)


def decrypt_signature_pdf(
    db: Session,
    file_path: Path,
    *,
    organization_id: str,
    actor_id: Optional[str],
) -> Tuple[Path, Optional[Path]]:
    service = get_encryption_service()
    metadata = service.get_metadata_for_path(db, file_path, organization_id)
    if not metadata:
        return file_path, None
    if metadata.get("purpose") != "signed_receipt_pdf":
        raise EncryptionError("unexpected_signature_pdf_encryption_purpose")

    temp_path = service.decrypt_file_to_temp(
        db,
        file_path,
        organization_id=organization_id,
        actor_id=actor_id,
        actor_type="employee",
        purpose="signed_receipt_pdf",
        expected_plaintext_sha256=metadata.get("plaintext_sha256"),
        suffix=".pdf",
    )
    return temp_path, temp_path


def encrypt_signed_pdf_result(
    db: Session,
    pdf_result: Dict[str, Any],
    *,
    organization_id: str,
    actor_id: Optional[str],
    actor_type: str,
) -> None:
    if not config.APP_ENCRYPTION_ENABLED:
        return

    service = get_encryption_service()
    signed_path = Path(pdf_result["signed_pdf_path"])
    metadata_items = []
    current_file_id = str(uuid.uuid4())
    current_purpose = "signed_receipt_pdf"
    try:
        metadata_items.append(
            service.encrypt_file_in_place(
                signed_path,
                organization_id=organization_id,
                purpose=current_purpose,
                file_id=current_file_id,
                plaintext_sha256=pdf_result["new_pdf_sha256"],
            )
        )

        signature_path = Path(pdf_result["sig_image_path"])
        current_purpose = "signature_evidence_image"
        current_file_id = str(uuid.uuid4())
        metadata_items.append(
            service.encrypt_file_in_place(
                signature_path,
                organization_id=organization_id,
                purpose=current_purpose,
                file_id=current_file_id,
                plaintext_sha256=pdf_result["sig_image_sha256"],
            )
        )
    except KmsError as exc:
        try:
            record_kms_error_event(
                db,
                organization_id=organization_id,
                actor_id=actor_id,
                actor_type=actor_type,
                file_id=current_file_id or "unknown",
                purpose=current_purpose,
                error_code=str(exc),
            )
        except Exception:
            logger.exception("encryption.kms_error_audit_failed")
        _cleanup_encryption_failure(signed_path, pdf_result.get("sig_image_path"))
        raise
    except EncryptionError:
        _cleanup_encryption_failure(signed_path, pdf_result.get("sig_image_path"))
        raise
    except OSError as exc:
        _cleanup_encryption_failure(signed_path, pdf_result.get("sig_image_path"))
        raise EncryptionError("signed_document_encryption_failed") from exc

    pdf_result["encryption_metadata_items"] = metadata_items


def persist_signed_pdf_encryption_metadata(
    db: Session,
    pdf_result: Dict[str, Any],
    *,
    actor_id: Optional[str],
    actor_type: str,
) -> None:
    service = get_encryption_service()
    for metadata in pdf_result.get("encryption_metadata_items", []):
        service.persist_metadata_and_audit(
            db,
            metadata,
            actor_id=actor_id,
            actor_type=actor_type,
        )


def _cleanup_encryption_failure(
    signed_path: Path,
    signature_path: Optional[str | Path],
) -> None:
    for path in (signed_path, Path(signature_path) if signature_path else None):
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.exception("encryption.plaintext_cleanup_failed")
