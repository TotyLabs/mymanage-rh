import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from payroll_core import logger, resolve_storage_path
from services.document_repository import DocumentRepository
from services.encryption_service import (
    EncryptionError,
    EncryptionIntegrityError,
    EncryptionService,
    KmsError,
    get_encryption_service,
)
from services.public_integrity import (
    LEGACY_SIGNATURE_CUTOFF,
    _sha256,
    _later_than,
    analyze_receipt_evidence,
    classify_integrity,
    correlate_pdf_certificates,
    is_legacy_document,
)


def _isoformat(value: Any) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _metadata_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            logger.warning("public_verification.invalid_seal_metadata")
    return {}


def _legajo_row(db: Session, document_id: str, organization_id: Optional[str] = None):
    row = db.execute(
        text("""
            SELECT s.id::text AS id, s.organization_id::text AS organization_id,
                   s.signed_pdf_path AS path, s.signed_pdf_sha256 AS hash,
                   s.source_pdf_path, s.source_pdf_sha256, s.signature_hash,
                   s.seal_id, s.signed_by_user_id::text AS signed_by_user_id,
                   s.status, s.signed_at, o.name AS organization_name
            FROM employee_legajo_signatures s
            JOIN organizations o ON o.id = s.organization_id
            WHERE s.id::text = :document_id
              AND (:organization_id IS NULL OR s.organization_id::text = :organization_id)
        """),
        {"document_id": document_id, "organization_id": organization_id},
    ).mappings().first()
    if row and row["status"] == "signed" and row["path"]:
        return dict(row)
    return None


def _resolve_document(db: Session, public_id: str) -> Optional[Dict[str, Any]]:
    seal = db.execute(
        text("""
            SELECT s.seal_id, s.signer_role, s.receipt_id::text AS document_id,
                   s.organization_id::text AS organization_id, s.pdf_hash,
                   s.metadata, s.created_at, o.name AS organization_name
            FROM receipt_seals s
            JOIN organizations o ON o.id = s.organization_id
            WHERE s.seal_id = :public_id
        """),
        {"public_id": public_id},
    ).mappings().first()

    if seal:
        legajo = _legajo_row(db, seal["document_id"], seal["organization_id"])
        if legajo:
            return {
                "document": legajo,
                "document_type": "legajo",
                "organization": legajo["organization_name"],
                "seal": dict(seal),
                "verification_id": _metadata_dict(seal["metadata"]).get("v_id"),
            }

        document = DocumentRepository.get_document(db, seal["document_id"])
        if document:
            return {
                "document": document,
                "document_type": "recibo",
                "organization": document.get("organization_name") or seal["organization_name"],
                "seal": dict(seal),
                "verification_id": _metadata_dict(seal["metadata"]).get("v_id")
                or document.get("verification_id"),
            }
        return None

    legajo = db.execute(
        text("""
            SELECT s.id::text AS id, s.organization_id::text AS organization_id
            FROM employee_legajo_signatures s
            WHERE s.seal_id = :public_id AND s.status = 'signed'
        """),
        {"public_id": public_id},
    ).mappings().first()
    if legajo:
        document = _legajo_row(db, legajo["id"], legajo["organization_id"])
        if document:
            return {
                "document": document,
                "document_type": "legajo",
                "organization": document["organization_name"],
                "seal": None,
                "verification_id": None,
            }

    evidence = db.execute(
        text("""
            SELECT e.receipt_id::text AS receipt_id,
                   e.enterprise_receipt_id::text AS enterprise_receipt_id,
                   e.verification_id
            FROM signature_evidence e
            WHERE e.verification_id = :public_id
            ORDER BY e.signed_at DESC
            LIMIT 1
        """),
        {"public_id": public_id},
    ).mappings().first()

    document_id = None
    verification_id = None
    if evidence:
        document_id = evidence["enterprise_receipt_id"] or evidence["receipt_id"]
        verification_id = evidence["verification_id"]
    else:
        linked_document = db.execute(
            text("""
                SELECT id::text AS id
                FROM payroll_receipts
                WHERE verification_id = :public_id AND is_deleted = false
                UNION ALL
                SELECT id::text AS id
                FROM receipts
                WHERE verification_id = :public_id AND is_deleted = false
                LIMIT 1
            """),
            {"public_id": public_id},
        ).mappings().first()
        if linked_document:
            document_id = linked_document["id"]
            verification_id = public_id

    if not document_id:
        return None
    document = DocumentRepository.get_document(db, document_id)
    if not document:
        return None
    return {
        "document": document,
        "document_type": "recibo",
        "organization": document.get("organization_name"),
        "seal": None,
        "verification_id": verification_id or document.get("verification_id"),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_pdf_signatures(path: Path) -> Dict[str, Any]:
    try:
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        from services.x509_service import get_validation_context_and_root

        validation_context, _ = get_validation_context_and_root()
        with path.open("rb") as file:
            reader = PdfFileReader(file)
            signatures = reader.embedded_signatures
            if not signatures:
                return {
                    "status": "missing",
                    "count": 0,
                    "trusted": None,
                    "signatures": [],
                    "trust_source": "configured_root" if validation_context else "system_default",
                }

            results = []
            for signature in signatures:
                try:
                    status = validate_pdf_signature(
                        signature,
                        signer_validation_context=validation_context,
                        ts_validation_context=validation_context,
                    )
                    certificate = (
                        getattr(status, "signing_cert", None)
                        or getattr(status, "signer_cert", None)
                    )
                    fingerprint = (
                        hashlib.sha256(certificate.dump()).hexdigest()
                        if certificate is not None
                        else None
                    )
                    serial = (
                        str(getattr(certificate.serial_number, "native", certificate.serial_number))
                        if certificate is not None
                        else None
                    )
                    timestamp_validity = getattr(status, "timestamp_validity", None)
                    timestamp_status = "not_present"
                    if timestamp_validity is not None:
                        if (
                            getattr(timestamp_validity, "intact", False) is False
                            or getattr(timestamp_validity, "valid", False) is False
                        ):
                            timestamp_status = "invalid"
                        elif getattr(timestamp_validity, "trusted", False) is not True:
                            timestamp_status = "untrusted"
                        else:
                            timestamp_status = "valid"
                    results.append({
                        "field_name": str(signature.field_name),
                        "intact": bool(status.intact),
                        "valid": bool(status.valid),
                        "trusted": status.trusted,
                        "docmdp_ok": getattr(status, "docmdp_ok", None),
                        "certificate_fingerprint": fingerprint,
                        "certificate_serial": serial,
                        "timestamp_status": timestamp_status,
                    })
                except Exception:
                    logger.exception("public_verification.pdf_signature_validation_failed")
                    results.append({
                        "field_name": str(signature.field_name),
                        "intact": None,
                        "valid": None,
                        "trusted": None,
                        "docmdp_ok": None,
                        "certificate_fingerprint": None,
                        "certificate_serial": None,
                        "timestamp_status": "unavailable",
                    })

            if any(
                result["intact"] is False
                or result["valid"] is False
                or result["docmdp_ok"] is False
                or result["timestamp_status"] == "invalid"
                for result in results
            ):
                overall_status = "invalid"
            elif any(result["valid"] is None for result in results):
                overall_status = "unavailable"
            elif any(
                result["trusted"] is not True
                or result["timestamp_status"] in {"untrusted", "unavailable"}
                for result in results
            ):
                overall_status = "untrusted"
            else:
                overall_status = "valid"

            return {
                "status": overall_status,
                "count": len(signatures),
                "trusted": overall_status == "valid",
                "signatures": results,
                "trust_source": "configured_root" if validation_context else "system_default",
            }
    except Exception:
        logger.exception("public_verification.pyhanko_validation_failed")
        return {
            "status": "unavailable",
            "count": 0,
            "trusted": None,
            "signatures": [],
            "trust_source": "unavailable",
        }


def _load_receipt_evidence(
    db: Session,
    document: Dict[str, Any],
    organization_id: str,
) -> Dict[str, Any]:
    foreign_key = {
        "payroll": "receipt_id",
        "enterprise": "enterprise_receipt_id",
    }.get(document.get("source"))
    if not foreign_key:
        raise ValueError("unsupported_receipt_source")
    evidence_rows = db.execute(
        text(f"""
            SELECT receipt_id::text AS receipt_id,
                   enterprise_receipt_id::text AS enterprise_receipt_id,
                   acceptance_text, signer_full_name, signer_cuil, period_label,
                   final_pdf_sha256, receipt_sha256_at_sign_time,
                   signature_image_path, signature_image_sha256,
                   verification_id, signed_at, signer_user_id::text AS signer_user_id,
                   batch_id::text AS batch_id, cert_fingerprint_sha256,
                   cert_serial, cert_issuer, cert_not_before, cert_not_after,
                   signature_algorithm, tsa_timestamp, sig_version,
                   validation_status, ocsp_status, ocsp_checked_at,
                   crl_status, crl_checked_at, validation_checked_at,
                   validation_error, signing_method
            FROM signature_evidence
            WHERE {foreign_key} = CAST(:document_id AS UUID)
            ORDER BY signed_at ASC
        """),
        {"document_id": document["id"]},
    ).mappings().all()
    events = db.execute(
        text(f"""
            SELECT action, document_source, actor_type::text AS actor_type,
                   actor_id::text AS actor_id,
                   status_before, status_after, pdf_sha256_before, pdf_sha256_after,
                   created_at, data
            FROM signature_events
            WHERE organization_id = CAST(:organization_id AS UUID)
              AND {foreign_key} = CAST(:document_id AS UUID)
              AND action IN ('SIGN_EMPLOYEE', 'SIGN_EMPLOYER', 'SIGN')
            ORDER BY created_at ASC, id ASC
        """),
        {"document_id": document["id"], "organization_id": organization_id},
    ).mappings().all()
    seals = db.execute(
        text("""
            SELECT seal_id, signer_role, pdf_hash, metadata, created_at
            FROM receipt_seals
            WHERE receipt_id = CAST(:document_id AS UUID)
              AND organization_id = CAST(:organization_id AS UUID)
            ORDER BY created_at ASC, id ASC
        """),
        {"document_id": document["id"], "organization_id": organization_id},
    ).mappings().all()
    audit_events = db.execute(
        text("""
            SELECT action, created_at, data
            FROM audit_log
            WHERE organization_id = CAST(:organization_id AS UUID)
              AND entity_id = CAST(:document_id AS UUID)
              AND action IN ('SIMPLE_SIGN', 'EMPLOYER_SIGN')
            ORDER BY created_at ASC, id ASC
        """),
        {"document_id": document["id"], "organization_id": organization_id},
    ).mappings().all()
    return {
        "evidence_rows": [dict(row) for row in evidence_rows],
        "events": [dict(row) for row in events],
        "audit_events": [dict(row) for row in audit_events],
        "seals": [
            dict(row) for row in seals
            if _metadata_dict(row["metadata"]).get("document_type") != "employee_legajo"
        ],
    }


def _inspect_storage_artifact(
    db: Session,
    raw_path: str,
    organization_id: str,
    *,
    purpose_hint: str,
) -> Dict[str, Any]:
    try:
        path = Path(resolve_storage_path(raw_path))
    except (HTTPException, TypeError, ValueError):
        return {"status": "failed", "message": "La ruta del archivo no es válida."}
    if not path.is_file():
        return {"status": "missing", "message": "El archivo no existe en el almacenamiento."}

    temp_path = None
    try:
        storage_key = EncryptionService.storage_key(path)
        metadata = db.execute(
            text("""
                SELECT purpose
                FROM file_encryption_metadata
                WHERE organization_id = CAST(:organization_id AS UUID)
                  AND storage_path = :storage_path
                LIMIT 1
            """),
            {"organization_id": organization_id, "storage_path": storage_key},
        ).mappings().first()
        content_path = path
        if metadata:
            temp_path = get_encryption_service().decrypt_file_to_temp(
                db,
                path,
                organization_id=organization_id,
                actor_id=None,
                actor_type="system",
                purpose=metadata["purpose"] or purpose_hint,
                suffix=path.suffix or ".bin",
            )
            content_path = temp_path
        return {
            "status": "valid",
            "sha256": _sha256_file(content_path),
        }
    except FileNotFoundError:
        logger.warning("public_verification.evidence_file_disappeared")
        return {"status": "missing", "message": "El archivo no existe en el almacenamiento."}
    except EncryptionIntegrityError:
        logger.exception("public_verification.evidence_file_integrity_failed")
        return {"status": "failed", "message": "La integridad de un archivo auxiliar no coincide."}
    except (KmsError, EncryptionError, OSError):
        logger.exception("public_verification.evidence_file_unavailable")
        return {"status": "unknown", "message": "No se pudo leer un archivo auxiliar."}
    finally:
        if temp_path:
            EncryptionService.cleanup_temp_file(temp_path)


def _inspect_receipt_image_artifacts(
    db: Session,
    artifacts: List[Dict[str, str]],
    organization_id: str,
) -> Dict[str, Any]:
    warnings = []
    failures = []
    for artifact in artifacts:
        result = _inspect_storage_artifact(
            db,
            artifact["path"],
            organization_id,
            purpose_hint="signature_evidence_image",
        )
        if result["status"] == "failed":
            failures.append(result["message"])
        elif result["status"] != "valid":
            warnings.append(result["message"])
        elif result["sha256"] != artifact["expected_hash"]:
            failures.append("El SHA-256 de una imagen de firma no coincide con la evidencia.")
    if failures:
        return {"status": "failed", "details": list(dict.fromkeys(failures))}
    if warnings:
        return {"status": "warning", "details": list(dict.fromkeys(warnings))}
    return {
        "status": "valid",
        "details": ["Los archivos de firma visual coinciden con sus hashes de evidencia."],
    }


def _analyze_legajo_database_evidence(
    db: Session,
    document: Dict[str, Any],
    seal: Optional[Dict[str, Any]],
    organization_id: str,
    actual_hash: Optional[str],
) -> Dict[str, Any]:
    failures = []
    warnings = []
    stored_hash = (document.get("hash") or "").strip().lower()
    source_hash = (document.get("source_pdf_sha256") or "").strip().lower()
    signature_hash = (document.get("signature_hash") or "").strip().lower()
    if not source_hash:
        warnings.append("El legajo no tiene el SHA-256 del PDF de origen.")
    elif not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        failures.append("El SHA-256 del PDF de origen guardado en DB no es válido.")
    if not signature_hash:
        warnings.append("El legajo no tiene el SHA-256 de la firma visual.")
    elif not re.fullmatch(r"[0-9a-f]{64}", signature_hash):
        failures.append("El SHA-256 de la firma visual guardado en DB no es válido.")
    if actual_hash and stored_hash and actual_hash != stored_hash:
        failures.append("El PDF firmado no coincide con el SHA-256 guardado en employee_legajo_signatures.")
    if seal:
        metadata = _metadata_dict(seal.get("metadata"))
        row_seal_id = str(document.get("seal_id") or "")
        stored_seal_id = str(seal.get("seal_id") or "")
        if row_seal_id and stored_seal_id and row_seal_id != stored_seal_id:
            failures.append("El identificador del sello no coincide con el registro del legajo.")
        elif not row_seal_id or not stored_seal_id:
            warnings.append("No se pudo confirmar el identificador del sello del legajo.")
        if str(seal.get("signer_role") or "").lower() != "employee":
            failures.append("El sello del legajo no identifica al empleado como firmante.")
        if metadata.get("pages_stamped") is False:
            failures.append("El sello indica que la firma visual no se aplicó a las páginas.")
        elif metadata.get("pages_stamped") is not True:
            warnings.append("El sello no confirma que la firma visual se aplicó a las páginas.")
        for field, stored_value, expected_value in (
            ("pdf_hash", seal.get("pdf_hash"), stored_hash),
            ("source_pdf_sha256", metadata.get("source_pdf_sha256"), source_hash),
            ("signature_hash", metadata.get("signature_hash"), signature_hash),
        ):
            if stored_value and expected_value and str(stored_value).lower() != expected_value:
                failures.append(f"El campo {field} del sello no coincide con employee_legajo_signatures.")
            elif not stored_value:
                warnings.append(f"Al sello del legajo le falta {field}.")
    else:
        warnings.append("No se encontró el sello asociado al legajo.")

    source_path = document.get("source_pdf_path")
    if source_path and source_hash:
        source_result = _inspect_storage_artifact(
            db,
            source_path,
            organization_id,
            purpose_hint="employee_legajo_signature_source",
        )
        if source_result["status"] == "failed":
            failures.append(source_result["message"])
        elif source_result["status"] != "valid":
            warnings.append(source_result["message"])
        elif source_result["sha256"] != source_hash:
            failures.append("El PDF de origen no coincide con su SHA-256 registrado.")
    else:
        warnings.append("No se pudo localizar el PDF de origen del legajo.")

    signature_row = None
    if document.get("signed_by_user_id") and signature_hash:
        signature_row = db.execute(
            text("""
                SELECT signature_path, signature_hash
                FROM user_signatures
                WHERE user_id = CAST(:user_id AS UUID)
                  AND signature_hash = :signature_hash
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {
                "user_id": document["signed_by_user_id"],
                "signature_hash": signature_hash,
            },
        ).mappings().first()
    if signature_row:
        image_result = _inspect_storage_artifact(
            db,
            signature_row["signature_path"],
            organization_id,
            purpose_hint="user_signature",
        )
        if image_result["status"] == "failed":
            failures.append(image_result["message"])
        elif image_result["status"] != "valid":
            warnings.append(image_result["message"])
        elif image_result["sha256"] != signature_hash:
            failures.append("La firma visual del legajo no coincide con su SHA-256 registrado.")
        if signature_row["signature_hash"] and signature_row["signature_hash"].lower() != signature_hash:
            failures.append("El hash de user_signatures no coincide con el registro del legajo.")
    else:
        warnings.append("No se encontró la imagen de firma original en user_signatures.")

    audit_rows = db.execute(
        text("""
            SELECT created_at, data
            FROM audit_log
            WHERE organization_id = CAST(:organization_id AS UUID)
              AND entity_id = CAST(:document_id AS UUID)
              AND action = 'EMPLOYEE_LEGAJO_SIGNED'
            ORDER BY created_at ASC, id ASC
        """),
        {"document_id": document["id"], "organization_id": organization_id},
    ).mappings().all()
    if not audit_rows:
        warnings.append("No se encontró el evento de firma del legajo en el historial de auditoría.")
    for audit_row in audit_rows:
        audit_data = _metadata_dict(audit_row["data"])
        for field, expected_hash in (
            ("source_pdf_sha256", source_hash),
            ("signed_pdf_sha256", stored_hash),
            ("signature_hash", signature_hash),
        ):
            audit_hash = _sha256(audit_data.get(field))
            if not audit_hash:
                warnings.append(f"Al evento de auditoría del legajo le falta {field}.")
            elif expected_hash and audit_hash != expected_hash:
                failures.append(f"El campo {field} de auditoría no coincide con el registro del legajo.")

    status = "failed" if failures else "warning" if warnings else "valid"
    details = list(dict.fromkeys(failures + warnings))
    if not details:
        details.append("Los hashes del legajo y los registros de sello coinciden.")
    return {
        "status": status,
        "message": (
            "La evidencia del legajo presenta inconsistencias."
            if status == "failed"
            else "La evidencia del legajo requiere atención."
            if status == "warning"
            else "La evidencia del legajo coincide con los registros de DB."
        ),
        "details": details,
        "expected_certificates": [],
    }


def verify_public_document(db: Session, public_id: str) -> Optional[Dict[str, Any]]:
    resolved = _resolve_document(db, public_id)
    if not resolved:
        return None

    document = resolved["document"]
    document_type = resolved["document_type"]
    organization_id = str(document["organization_id"])
    recorded_hash = (document.get("hash") or "").strip().lower()
    seal = resolved["seal"]
    seal_hash = (seal.get("pdf_hash") or "").strip().lower() if seal else ""
    signed_at = document.get("signed_at") or (seal.get("created_at") if seal else None)
    legacy = is_legacy_document(signed_at)
    if document_type == "recibo":
        db_evidence = _load_receipt_evidence(db, document, organization_id)
        evidence_rows = db_evidence["evidence_rows"]
        event_rows = db_evidence["events"]
        audit_rows = db_evidence["audit_events"]
        seal_rows = db_evidence["seals"]
        if not seal and seal_rows:
            seal = seal_rows[-1]
            seal_hash = (seal.get("pdf_hash") or "").strip().lower()
            if signed_at is None:
                signed_at = seal.get("created_at")
                legacy = is_legacy_document(signed_at)
        latest_evidence = evidence_rows[-1] if evidence_rows else None
    else:
        evidence_rows = []
        event_rows = []
        audit_rows = []
        seal_rows = []
        if seal:
            seal_rows = [seal]
        else:
            rows = db.execute(
                text("""
                    SELECT seal_id, signer_role, pdf_hash, metadata, created_at
                    FROM receipt_seals
                    WHERE receipt_id = CAST(:document_id AS UUID)
                      AND organization_id = CAST(:organization_id AS UUID)
                    ORDER BY created_at ASC, id ASC
                """),
                {"document_id": document["id"], "organization_id": organization_id},
            ).mappings().all()
            seal_rows = [
                dict(row) for row in rows
                if _metadata_dict(row["metadata"]).get("document_type") == "employee_legajo"
            ]
            if seal_rows:
                seal = seal_rows[-1]
                seal_hash = (seal.get("pdf_hash") or "").strip().lower()
                if signed_at is None:
                    signed_at = seal.get("created_at")
                    legacy = is_legacy_document(signed_at)
        latest_evidence = None

    checks = {}
    actual_hash = None
    signature_result = {
        "status": "unavailable",
        "count": 0,
        "trusted": None,
        "signatures": [],
        "trust_source": "unavailable",
    }
    main_content_path = None
    main_temp_path = None
    try:
        try:
            path = Path(resolve_storage_path(document["path"]))
        except (HTTPException, TypeError, ValueError):
            logger.warning("public_verification.invalid_storage_path")
            checks["storage"] = {
                "status": "failed",
                "message": "La ruta del archivo no es válida.",
            }
            path = None

        if path is not None and not path.is_file():
            checks["storage"] = {
                "status": "failed",
                "message": "El archivo no existe en el almacenamiento.",
            }
        elif path is not None:
            checks["storage"] = {
                "status": "valid",
                "message": "El archivo existe en el almacenamiento.",
            }
            try:
                storage_key = EncryptionService.storage_key(path)
                encryption_metadata = db.execute(
                    text("""
                        SELECT purpose
                        FROM file_encryption_metadata
                        WHERE organization_id = CAST(:organization_id AS UUID)
                          AND storage_path = :storage_path
                        LIMIT 1
                    """),
                    {"organization_id": organization_id, "storage_path": storage_key},
                ).mappings().first()
                main_content_path = path
                if encryption_metadata:
                    main_temp_path = get_encryption_service().decrypt_file_to_temp(
                        db,
                        path,
                        organization_id=organization_id,
                        actor_id=None,
                        actor_type="system",
                        purpose=encryption_metadata["purpose"],
                        suffix=".pdf",
                    )
                    main_content_path = main_temp_path

                with main_content_path.open("rb") as file:
                    is_pdf = b"%PDF-" in file.read(1024)
                if not is_pdf:
                    checks["storage"] = {
                        "status": "failed",
                        "message": "El archivo almacenado no es un PDF válido.",
                    }
                    signature_result["status"] = "invalid"
                else:
                    actual_hash = _sha256_file(main_content_path)
            except FileNotFoundError:
                logger.warning("public_verification.storage_file_disappeared")
                checks["storage"] = {
                    "status": "failed",
                    "message": "El archivo no existe en el almacenamiento.",
                }
            except EncryptionIntegrityError:
                logger.exception("public_verification.encrypted_file_integrity_failed")
                checks["storage"] = {
                    "status": "failed",
                    "message": "La integridad del archivo almacenado no pudo confirmarse.",
                }
            except KmsError:
                logger.exception("public_verification.kms_unavailable")
                checks["storage"] = {
                    "status": "unknown",
                    "message": "El archivo existe, pero no se pudo validar temporalmente su contenido.",
                }
            except EncryptionError:
                logger.exception("public_verification.decryption_failed")
                checks["storage"] = {
                    "status": "unknown",
                    "message": "El archivo existe, pero no se pudo validar temporalmente su contenido.",
                }
            except OSError:
                logger.exception("public_verification.storage_read_failed")
                checks["storage"] = {
                    "status": "unknown",
                    "message": "El archivo existe, pero no se pudo leer para validar su integridad.",
                }

        if actual_hash is None:
            checks["database_hash"] = {
                "status": "unknown",
                "message": "No se pudo comparar el SHA-256 del archivo con el registro.",
            }
        elif not recorded_hash:
            checks["database_hash"] = {
                "status": "unknown",
                "message": "El documento no tiene un SHA-256 actual registrado.",
            }
        elif actual_hash == recorded_hash:
            checks["database_hash"] = {
                "status": "valid",
                "message": "El SHA-256 coincide con el registro actual del documento.",
            }
        else:
            checks["database_hash"] = {
                "status": "failed",
                "message": "El SHA-256 del archivo no coincide con el registro actual.",
            }

        if not seal:
            checks["seal_hash"] = {
                "status": "not_applicable",
                "message": "El documento se identificó mediante su ID de verificación.",
            }
        elif not seal_hash or actual_hash is None:
            checks["seal_hash"] = {
                "status": "unknown",
                "message": "No se pudo comparar el hash del sello.",
            }
        elif actual_hash == seal_hash or any(
            (event.get("pdf_sha256_after") or "").strip().lower() == seal_hash
            for event in event_rows
        ):
            checks["seal_hash"] = {
                "status": "valid",
                "message": "El hash del sello coincide con el archivo o con una versión de su historial de firma.",
            }
        elif _later_than(signed_at, seal.get("created_at")):
            checks["seal_hash"] = {
                "status": "historical",
                "message": "El sello puede corresponder a una versión anterior del documento.",
            }
        else:
            checks["seal_hash"] = {
                "status": "failed",
                "message": "El hash del sello no coincide con el archivo actual.",
            }

        if document_type == "recibo":
            db_analysis = analyze_receipt_evidence(
                evidence_rows=evidence_rows,
                signature_events=event_rows,
                seals=seal_rows,
                audit_events=audit_rows,
                document_hash=actual_hash or recorded_hash,
                document_signed_at=signed_at,
                legacy=legacy,
                document_batch_id=document.get("batch_id"),
                document_id=str(document["id"]),
                document_source=document.get("source"),
            )
            image_check = _inspect_receipt_image_artifacts(
                db,
                db_analysis["image_artifacts"],
                organization_id,
            )
            if image_check["status"] == "failed":
                db_analysis["status"] = "failed"
            elif image_check["status"] == "warning" and db_analysis["status"] == "valid":
                db_analysis["status"] = "warning"
            db_analysis["details"].extend(image_check["details"])
            evidence = latest_evidence
        else:
            db_analysis = _analyze_legajo_database_evidence(
                db,
                document,
                seal,
                organization_id,
                actual_hash,
            )
            evidence = None

        checks["database_evidence"] = {
            "status": db_analysis["status"],
            "message": db_analysis["message"],
            "details": db_analysis["details"],
        }

        if document_type != "recibo":
            checks["evidence_hash"] = {
                "status": "not_applicable",
                "message": "La evidencia del legajo se analiza en el registro propio del documento.",
            }
        elif not evidence:
            checks["evidence_hash"] = {
                "status": "not_applicable",
                "message": "No hay un registro de evidencia de firma adicional.",
            }
        else:
            evidence_hash = (evidence.get("final_pdf_sha256") or "").strip().lower()
            if not evidence_hash or actual_hash is None:
                checks["evidence_hash"] = {
                    "status": "unknown",
                    "message": "No se pudo comparar el hash de la evidencia de firma.",
                }
            elif actual_hash == evidence_hash or any(
                (event.get("pdf_sha256_after") or "").strip().lower() == evidence_hash
                for event in event_rows
            ):
                checks["evidence_hash"] = {
                    "status": "valid",
                    "message": "El hash de evidencia coincide con el archivo o con una versión de su historial de firma.",
                }
            elif _later_than(signed_at, evidence.get("signed_at")):
                checks["evidence_hash"] = {
                    "status": "historical",
                    "message": "La evidencia conserva el hash de una versión anterior firmada.",
                }
            else:
                checks["evidence_hash"] = {
                    "status": "failed",
                    "message": "El hash de la evidencia no coincide con el documento actual.",
                }

        if main_content_path and actual_hash is not None:
            signature_result = _validate_pdf_signatures(main_content_path)

        signature_status = signature_result["status"]
        if signature_status == "valid":
            signature_message = "PyHanko validó las firmas PDF y la cadena de confianza."
        elif signature_status == "untrusted":
            signature_message = "La firma PDF es íntegra, pero el certificado no pudo establecerse como confiable."
        elif signature_status == "missing" and legacy:
            signature_message = "No se encontró una firma PDF compatible; puede corresponder a la versión anterior."
        elif signature_status == "missing":
            signature_message = "No se encontró una firma criptográfica PDF."
        elif signature_status == "invalid":
            signature_message = "PyHanko detectó una firma, marca de tiempo o cambio no permitido inválido."
        else:
            signature_message = "No se pudo completar la validación criptográfica con PyHanko."
        trust_source_message = {
            "configured_root": "Se utilizó la raíz de confianza configurada.",
            "system_default": "Se utilizaron las raíces de confianza del sistema disponibles.",
            "unavailable": "No se pudo cargar un contexto de confianza.",
        }.get(signature_result["trust_source"], "Contexto de confianza no disponible.")
        checks["pdf_signature"] = {
            "status": signature_status,
            "message": signature_message,
            "trust_source": signature_result["trust_source"],
            "details": [trust_source_message],
        }

        if document_type == "recibo":
            certificate_check = correlate_pdf_certificates(
                db_analysis["expected_certificates"],
                signature_result["signatures"],
            )
        else:
            certificate_check = {
                "status": "not_applicable",
                "message": "El legajo utiliza un sello visual y no registra un certificado de firma PDF propio.",
            }
        checks["certificate_correlation"] = certificate_check

        integrity_status = classify_integrity(
            file_status=checks["storage"]["status"],
            database_hash_status=checks["database_hash"]["status"],
            seal_hash_status=checks["seal_hash"]["status"],
            evidence_hash_status=checks["evidence_hash"]["status"],
            signature_status=signature_status,
            legacy=legacy,
            database_evidence_status=db_analysis["status"],
            certificate_status=certificate_check["status"],
        )

        audit_verification_id = (
            evidence.get("verification_id")
            if evidence and evidence.get("receipt_id") and evidence.get("verification_id")
            else None
        )
        download_url = (
            f"/api/employee-legajos/{document['id']}/pdf?version=signed"
            if document_type == "legajo"
            else f"/api/receipts/{document['id']}/download"
        )

        return {
            "status": {"green": "valid", "yellow": "warning", "red": "invalid"}[integrity_status],
            "integrity_status": integrity_status,
            "document_id": str(document["id"]),
            "document_type": document_type,
            "organization": resolved["organization"],
            "signed_at": _isoformat(signed_at),
            "verification_id": resolved["verification_id"] or public_id,
            "audit_verification_id": audit_verification_id,
            "document_hash": actual_hash or recorded_hash or None,
            "signature_count": signature_result["count"],
            "pdf_signatures": signature_result["signatures"],
            "checks": checks,
            "legacy_warning": legacy,
            "legacy_cutoff": LEGACY_SIGNATURE_CUTOFF.isoformat(),
            "download_url": download_url,
        }
    finally:
        if main_temp_path:
            EncryptionService.cleanup_temp_file(main_temp_path)
