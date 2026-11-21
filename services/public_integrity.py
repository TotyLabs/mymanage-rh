import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, Optional


LEGACY_SIGNATURE_CUTOFF = date(2026, 11, 20)


def is_legacy_document(document_date) -> bool:
    if isinstance(document_date, datetime):
        document_date = document_date.date()
    return isinstance(document_date, date) and document_date <= LEGACY_SIGNATURE_CUTOFF


def classify_integrity(
    *,
    file_status: str,
    database_hash_status: str,
    seal_hash_status: str,
    evidence_hash_status: str,
    signature_status: str,
    legacy: bool,
    database_evidence_status: str = "not_applicable",
    certificate_status: str = "not_applicable",
) -> str:
    if (
        file_status == "failed"
        or database_hash_status == "failed"
        or seal_hash_status == "failed"
        or evidence_hash_status == "failed"
        or database_evidence_status == "failed"
        or certificate_status == "failed"
        or signature_status == "invalid"
        or (signature_status == "missing" and not legacy)
    ):
        return "red"
    if (
        legacy
        or database_hash_status != "valid"
        or seal_hash_status in {"historical", "unknown"}
        or evidence_hash_status not in {"valid", "not_applicable"}
        or database_evidence_status not in {"valid", "not_applicable"}
        or certificate_status not in {"valid", "not_applicable"}
        or signature_status != "valid"
    ):
        return "yellow"
    return "green"


def _sha256(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if re.fullmatch(r"[0-9a-f]{64}", normalized) else None


def normalize_fingerprint(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.replace(":", "").replace(" ", "").strip().upper()
    return normalized if re.fullmatch(r"[0-9A-F]{64}", normalized) else None


def _json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def _later_than(left: Any, right: Any) -> bool:
    left_datetime = _as_datetime(left)
    right_datetime = _as_datetime(right)
    if left_datetime is None or right_datetime is None:
        return False
    return left_datetime > right_datetime


def _as_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def analyze_receipt_evidence(
    *,
    evidence_rows: Iterable[Dict[str, Any]],
    signature_events: Iterable[Dict[str, Any]],
    seals: Iterable[Dict[str, Any]],
    document_hash: Optional[str],
    document_signed_at: Any,
    legacy: bool,
    audit_events: Iterable[Dict[str, Any]] = (),
    document_batch_id: Optional[str] = None,
    document_id: Optional[str] = None,
    document_source: Optional[str] = None,
) -> Dict[str, Any]:
    evidence_rows = list(evidence_rows)
    signature_events = list(signature_events)
    seals = list(seals)
    audit_events = list(audit_events)
    current_hash = _sha256(document_hash)
    failures = []
    warnings = []
    details = []
    expected_certificates = []
    image_artifacts = []
    event_records = []

    for event in signature_events:
        before = _sha256(event.get("pdf_sha256_before"))
        after = _sha256(event.get("pdf_sha256_after"))
        if event.get("pdf_sha256_before") and not before:
            failures.append("Un evento contiene un SHA-256 previo inválido.")
        if event.get("pdf_sha256_after") and not after:
            failures.append("Un evento contiene un SHA-256 final inválido.")
        if bool(before) != bool(after):
            warnings.append("Un evento de firma no tiene el par completo de hashes previo/final.")
        if not event.get("status_before") or not event.get("status_after"):
            warnings.append("Un evento no registra el estado del documento antes y después de firmar.")
        if before or after:
            event_records.append(
                {
                    **event,
                    "_before_hash": before,
                    "_after_hash": after,
                    "_data": _json_dict(event.get("data")),
                }
            )

    for previous, current in zip(event_records, event_records[1:]):
        if (
            previous["_after_hash"]
            and current["_before_hash"]
            and previous["_after_hash"] != current["_before_hash"]
        ):
            failures.append("La cadena de hashes de eventos de firma no coincide.")
        if (
            previous.get("status_after")
            and current.get("status_before")
            and previous["status_after"] != current["status_before"]
        ):
            failures.append("La secuencia de estados de firma no coincide entre eventos.")

    if event_records and current_hash and event_records[-1]["_after_hash"] != current_hash:
        if legacy or _later_than(document_signed_at, event_records[-1].get("created_at")):
            warnings.append("El último evento registra una versión anterior del PDF.")
        else:
            failures.append("El último hash de evento no coincide con el hash actual del documento.")

    event_hashes = {
        event["_after_hash"] for event in event_records if event["_after_hash"]
    }

    if not evidence_rows:
        warnings.append("No se encontró el registro detallado de la firma.")
    for evidence in evidence_rows:
        for field in ("acceptance_text", "signer_full_name", "signer_cuil", "period_label", "verification_id"):
            if not str(evidence.get(field) or "").strip():
                warnings.append("Al registro detallado de la firma le faltan datos legales o de identificación.")
        evidence_batch_id = str(evidence.get("batch_id") or "")
        if evidence_batch_id and document_batch_id and evidence_batch_id != str(document_batch_id):
            failures.append("El lote del registro de firma no coincide con el lote del documento.")
        if document_id and document_source:
            receipt_id = str(evidence.get("receipt_id") or "")
            enterprise_receipt_id = str(evidence.get("enterprise_receipt_id") or "")
            expected_receipt_id = str(document_id) if document_source == "payroll" else ""
            expected_enterprise_id = str(document_id) if document_source == "enterprise" else ""
            if receipt_id != expected_receipt_id or enterprise_receipt_id != expected_enterprise_id:
                failures.append("La evidencia está asociada a una clase o identificador de documento distinto.")
        signed_hash = _sha256(evidence.get("receipt_sha256_at_sign_time"))
        final_hash = _sha256(evidence.get("final_pdf_sha256"))
        image_hash = _sha256(evidence.get("signature_image_sha256"))
        if evidence.get("receipt_sha256_at_sign_time") and not signed_hash:
            failures.append("La evidencia contiene un SHA-256 previo inválido.")
        elif not signed_hash:
            warnings.append("A una evidencia le falta el SHA-256 previo.")
        if evidence.get("final_pdf_sha256") and not final_hash:
            failures.append("La evidencia contiene un SHA-256 final inválido.")
        elif not final_hash:
            warnings.append("A una evidencia le falta el SHA-256 final.")
        if evidence.get("signature_image_sha256") and not image_hash:
            failures.append("La evidencia contiene un SHA-256 de firma visual inválido.")
        elif not image_hash:
            warnings.append("A una evidencia le falta el SHA-256 de la firma visual.")

        image_path = evidence.get("signature_image_path")
        if image_path and image_hash:
            image_artifacts.append(
                {"path": image_path, "expected_hash": image_hash}
            )
        else:
            warnings.append("No se pudo localizar el archivo de firma visual de una evidencia.")

        matched_events = [
            event for event in event_records
            if final_hash and event["_after_hash"] == final_hash
        ]
        if event_records and final_hash and not matched_events:
            if legacy:
                warnings.append("Una evidencia no tiene evento de firma correlacionado.")
            else:
                failures.append("Una evidencia no tiene evento de firma correlacionado.")
        elif matched_events:
            event = matched_events[-1]
            if signed_hash and event["_before_hash"] and signed_hash != event["_before_hash"]:
                failures.append("El hash previo de evidencia no coincide con su evento de firma.")
            event_image_hash = _sha256(event["_data"].get("signature_sha256"))
            if image_hash and event_image_hash and image_hash != event_image_hash:
                failures.append("El hash de firma visual no coincide entre evidencia y evento.")
            event_document_hash = event["_data"].get("document_hash")
            if event_document_hash and _sha256(event_document_hash) != event["_after_hash"]:
                failures.append("El hash final del evento no coincide con el hash guardado en su detalle.")
            event_fingerprint = normalize_fingerprint(
                event["_data"].get("certificate_fingerprint")
            )
            evidence_fingerprint = normalize_fingerprint(
                evidence.get("cert_fingerprint_sha256")
            )
            if event_fingerprint and evidence_fingerprint and event_fingerprint != evidence_fingerprint:
                failures.append("El certificado registrado en el evento no coincide con el de la evidencia.")
            event_version = event["_data"].get("signature_version")
            evidence_version = evidence.get("sig_version")
            if event_version and evidence_version and str(event_version) != str(evidence_version):
                failures.append("La versión de firma del evento no coincide con la evidencia.")
            event_issuer = event["_data"].get("issuer")
            if event_issuer and evidence.get("cert_issuer") and str(event_issuer) != str(evidence["cert_issuer"]):
                failures.append("El emisor del certificado no coincide entre evento y evidencia.")
            acceptance_hash = _sha256(event["_data"].get("legal_acceptance_hash"))
            acceptance_text = str(evidence.get("acceptance_text") or "")
            if acceptance_hash and acceptance_text:
                if acceptance_hash != hashlib.sha256(acceptance_text.encode("utf-8")).hexdigest():
                    failures.append("El texto legal guardado no coincide con la huella registrada al firmar.")
            elif acceptance_text:
                warnings.append("No se pudo cotejar el texto legal con una huella guardada en el evento.")
            signer_role = str(event["_data"].get("signer_role") or "").lower()
            if signer_role and signer_role != "employee":
                failures.append("El rol del evento no corresponde al firmante de la evidencia.")
            elif not signer_role:
                warnings.append("El evento no identifica el rol del firmante.")
            actor_id = str(event.get("actor_id") or "")
            signer_user_id = str(evidence.get("signer_user_id") or "")
            if actor_id and signer_user_id and actor_id != signer_user_id:
                failures.append("El usuario del evento no coincide con el usuario de la evidencia.")
            actor_type = str(event.get("actor_type") or "").lower()
            expected_actor_type = "employee" if signer_role == "employee" else "admin"
            if actor_type and signer_role and actor_type != expected_actor_type:
                failures.append("El tipo de actor del evento no coincide con el firmante.")
            timestamp_source = str(event["_data"].get("timestamp_source") or "").upper()
            if timestamp_source == "TSA" and not evidence.get("tsa_timestamp"):
                warnings.append("El evento registra un sello de tiempo externo, pero falta su fecha en la evidencia.")

        fingerprint_value = evidence.get("cert_fingerprint_sha256")
        fingerprint = normalize_fingerprint(fingerprint_value)
        serial_value = evidence.get("cert_serial")
        serial = str(serial_value).strip() if serial_value is not None else ""
        if fingerprint_value and not fingerprint:
            failures.append("La evidencia contiene un fingerprint de certificado inválido.")
        if fingerprint and serial:
            expected_certificates.append(
                {"fingerprint": fingerprint, "serial": serial}
            )
        else:
            warnings.append("La evidencia no contiene fingerprint y número de serie completos.")

        signed_at = _as_datetime(evidence.get("signed_at"))
        not_before = _as_datetime(evidence.get("cert_not_before"))
        not_after = _as_datetime(evidence.get("cert_not_after"))
        if evidence.get("cert_not_before") and not_before is None:
            failures.append("La fecha de inicio de vigencia del certificado no es válida.")
        if evidence.get("cert_not_after") and not_after is None:
            failures.append("La fecha de vencimiento del certificado no es válida.")
        if not_before and not_after and signed_at:
            if not_before > signed_at or signed_at > not_after:
                failures.append("El certificado no estaba vigente en la fecha de firma guardada.")
        elif not (not_before and not_after):
            warnings.append("La evidencia no contiene el período completo de vigencia del certificado.")
        elif signed_at is None:
            warnings.append("No se pudo cotejar la vigencia del certificado con la fecha de firma.")

        if not str(evidence.get("cert_issuer") or "").strip() or not str(evidence.get("cert_subject") or "").strip():
            warnings.append("A la evidencia le faltan los campos de emisor o sujeto del certificado.")
        if not str(evidence.get("signature_algorithm") or "").strip() or str(evidence.get("signature_algorithm")).upper() == "UNKNOWN":
            warnings.append("La evidencia no identifica el algoritmo de firma.")
        if not evidence.get("sig_version"):
            warnings.append("La evidencia no identifica la versión del proceso de firma.")

        validation_status = str(evidence.get("validation_status") or "").strip().lower()
        if validation_status in {"revoked", "invalid"}:
            failures.append("La evidencia guardó un certificado revocado o inválido.")
        elif validation_status not in {"valid", "good"} or evidence.get("validation_error"):
            warnings.append("La validación de certificado guardada en DB fue incompleta.")
        revocation_statuses = {
            str(evidence.get(field) or "").strip().lower()
            for field in ("ocsp_status", "crl_status")
        }
        if "revoked" in revocation_statuses:
            failures.append("La evidencia guardó un estado de revocación negativo.")
        elif not revocation_statuses.intersection({"good", "valid"}):
            warnings.append("La evidencia no confirma un resultado OCSP o CRL positivo.")
        if evidence.get("tsa_timestamp") and _as_datetime(evidence["tsa_timestamp"]) is None:
            failures.append("La marca de tiempo TSA guardada en DB no es válida.")
        if not evidence.get("validation_checked_at"):
            warnings.append("La evidencia no registra cuándo se verificó el certificado.")
        if not str(evidence.get("signing_method") or "").strip():
            warnings.append("La evidencia no registra el método de firma.")
        if str(evidence.get("ocsp_status") or "").strip().lower() in {"good", "valid"} and not evidence.get("ocsp_checked_at"):
            warnings.append("Falta la fecha de consulta del estado OCSP.")
        if str(evidence.get("crl_status") or "").strip().lower() in {"good", "valid"} and not evidence.get("crl_checked_at"):
            warnings.append("Falta la fecha de consulta de la lista de revocación.")

    for event in event_records:
        fingerprint_value = event["_data"].get("certificate_fingerprint")
        fingerprint = normalize_fingerprint(fingerprint_value)
        if fingerprint_value and not fingerprint:
            failures.append("Un evento contiene un fingerprint de certificado inválido.")
        elif fingerprint:
            expected_certificates.append({"fingerprint": fingerprint, "serial": ""})
        else:
            warnings.append("Un evento no identifica el certificado usado para firmar.")
        event_image_hash = event["_data"].get("signature_sha256")
        if event_image_hash and not _sha256(event_image_hash):
            failures.append("Un evento contiene una huella de firma visual inválida.")
        elif not event_image_hash:
            warnings.append("Un evento no guarda la huella de la firma visual.")
        event_document_hash = event["_data"].get("document_hash")
        if event_document_hash and _sha256(event_document_hash) != event["_after_hash"]:
            failures.append("El hash final del evento no coincide con el hash guardado en su detalle.")
        elif not event_document_hash:
            warnings.append("Un evento no guarda la huella del documento firmado.")
        signer_role = str(event["_data"].get("signer_role") or "").lower()
        if signer_role and signer_role not in {"employee", "employer"}:
            failures.append("Un evento identifica un rol de firma desconocido.")
        event_source = str(event.get("document_source") or "")
        if event_source and document_source and event_source != document_source:
            failures.append("El evento de firma está asociado a otro tipo de documento.")
        timestamp_source = str(event["_data"].get("timestamp_source") or "").upper()
        if timestamp_source and timestamp_source not in {"TSA", "LOCAL_FALLBACK", "NONE"}:
            warnings.append("Un evento contiene un origen de sello de tiempo no reconocido.")
        identity_hash = event["_data"].get("signer_identity_hash")
        if identity_hash and not _sha256(identity_hash):
            failures.append("El identificador protegido del firmante tiene un formato inválido.")
        acceptance_hash = event["_data"].get("legal_acceptance_hash")
        if acceptance_hash and not _sha256(acceptance_hash):
            failures.append("La huella del texto legal de aceptación tiene un formato inválido.")
        elif not acceptance_hash:
            warnings.append("El evento no guarda la huella del texto legal aceptado.")

    if not event_records:
        warnings.append("No se encontraron eventos de firma con hashes para correlacionar.")

    seal_hashes = set()
    seals_by_hash = {}
    for seal in seals:
        seal_hash_value = seal.get("pdf_hash")
        seal_hash = _sha256(seal_hash_value)
        if seal_hash_value and not seal_hash:
            failures.append("Un sello contiene un SHA-256 inválido.")
        elif seal_hash:
            seal_hashes.add(seal_hash)
            seals_by_hash.setdefault(seal_hash, []).append(seal)
            if seal_hash != current_hash and seal_hash not in event_hashes:
                if legacy or _later_than(document_signed_at, seal.get("created_at")):
                    warnings.append("Un sello corresponde a una versión anterior del PDF.")
                else:
                    failures.append("El hash de un sello no coincide con el historial de firmas.")
        if not seal.get("seal_id") or str(seal.get("signer_role") or "").lower() not in {"employee", "employer"}:
            warnings.append("A un sello le faltan su identificador o el rol de quien firmó.")
        if not _json_dict(seal.get("metadata")).get("v_id"):
            warnings.append("A un sello le falta su identificador de verificación.")

    for evidence in evidence_rows:
        final_hash = _sha256(evidence.get("final_pdf_sha256"))
        matched_seals = seals_by_hash.get(final_hash, []) if final_hash else []
        if not matched_seals:
            (warnings if legacy else failures).append(
                "No se encontró un sello que corresponda al PDF registrado en la evidencia."
            )
            continue
        employee_seals = [
            seal for seal in matched_seals
            if str(seal.get("signer_role") or "").lower() == "employee"
        ]
        if not employee_seals:
            failures.append("El rol del sello asociado a la evidencia no corresponde al firmante.")
            continue
        for seal in employee_seals:
            seal_verification_id = _json_dict(seal.get("metadata")).get("v_id")
            evidence_verification_id = evidence.get("verification_id")
            if seal_verification_id and evidence_verification_id and seal_verification_id != evidence_verification_id:
                failures.append("El identificador del sello no coincide con el de la evidencia.")
            elif not seal_verification_id:
                warnings.append("Al sello asociado a la evidencia le falta el identificador de verificación.")

    for event in event_records:
        event_role = str(event["_data"].get("signer_role") or "").lower()
        event_hash = event["_after_hash"]
        if event_role and event_hash and seals_by_hash.get(event_hash):
            matching_roles = {
                str(seal.get("signer_role") or "").lower()
                for seal in seals_by_hash[event_hash]
            }
            if event_role not in matching_roles:
                failures.append("El rol del evento no coincide con el sello de esa versión del documento.")

    for audit_event in audit_events:
        data = _json_dict(audit_event.get("data"))
        action = str(audit_event.get("action") or "")
        if action == "SIMPLE_SIGN":
            audit_hash = _sha256(data.get("pdf_hash"))
            if data.get("pdf_hash") and not audit_hash:
                failures.append("El registro de auditoría contiene una huella de documento inválida.")
            elif not audit_hash:
                warnings.append("El registro de auditoría no contiene la huella del documento.")
            elif audit_hash not in event_hashes and audit_hash not in seal_hashes and audit_hash != current_hash:
                (warnings if legacy else failures).append(
                    "La firma registrada en auditoría no coincide con el historial del documento."
                )
        elif action == "EMPLOYER_SIGN":
            before = _sha256(data.get("pdf_sha256_before"))
            after = _sha256(data.get("pdf_sha256_after"))
            if not before or not after:
                warnings.append("Al registro de auditoría de la firma del empleador le faltan huellas.")
            elif not any(
                event["_before_hash"] == before and event["_after_hash"] == after
                for event in event_records
            ):
                (warnings if legacy else failures).append(
                    "La firma del empleador en auditoría no coincide con el historial de firmas."
                )

    if current_hash is None:
        warnings.append("No hay un hash SHA-256 actual válido en el registro del documento.")

    unique_certificates = {}
    for certificate in expected_certificates:
        existing = unique_certificates.get(certificate["fingerprint"])
        if existing is None or (not existing["serial"] and certificate["serial"]):
            unique_certificates[certificate["fingerprint"]] = certificate
    expected_certificates = list(unique_certificates.values())

    if failures:
        status = "failed"
        details.extend(dict.fromkeys(failures))
    else:
        status = "warning" if warnings else "valid"
        details.extend(dict.fromkeys(warnings))
        if not details:
            details.append("La evidencia, los eventos y los sellos son consistentes.")

    details.insert(
        0,
        f"{len(evidence_rows)} registro(s) de signature_evidence y "
        f"{len(signature_events)} evento(s) y {len(audit_events)} registro(s) de auditoría analizados.",
    )
    return {
        "status": status,
        "message": (
            "La evidencia de firma presenta inconsistencias."
            if status == "failed"
            else "La evidencia de firma requiere atención."
            if status == "warning"
            else "La evidencia de firma coincide con los registros de DB."
        ),
        "details": details,
        "expected_certificates": expected_certificates,
        "image_artifacts": image_artifacts,
    }


def correlate_pdf_certificates(
    expected_certificates: Iterable[Dict[str, str]],
    pdf_signatures: Iterable[Dict[str, Any]],
) -> Dict[str, Any]:
    expected_certificates = list(expected_certificates)
    pdf_signatures = list(pdf_signatures)
    if not expected_certificates:
        return {"status": "not_applicable", "message": "No hay fingerprints de certificado en la evidencia DB."}

    available = [
        {
            "fingerprint": normalize_fingerprint(signature.get("certificate_fingerprint")),
            "serial": str(signature.get("certificate_serial") or "").strip(),
        }
        for signature in pdf_signatures
    ]
    if not any(signature["fingerprint"] for signature in available):
        return {
            "status": "warning",
            "message": (
                "No se pudo extraer un certificado de las firmas PDF para cotejarlo con la evidencia."
                if pdf_signatures
                else "No hay firmas PDF incrustadas para cotejar el certificado guardado en DB."
            ),
        }
    unmatched = [
        expected for expected in expected_certificates
        if not any(
            signature["fingerprint"] == expected["fingerprint"]
            and (not expected["serial"] or signature["serial"] == expected["serial"])
            for signature in available
        )
    ]
    if unmatched:
        return {
            "status": "failed",
            "message": "El certificado de la evidencia DB no coincide con ninguna firma incrustada en el PDF.",
        }
    return {
        "status": "valid",
        "message": "Los fingerprints y números de serie de la evidencia coinciden con firmas del PDF.",
    }
