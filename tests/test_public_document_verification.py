import hashlib
from datetime import date, datetime, timezone

import pytest

from services.public_integrity import (
    analyze_receipt_evidence,
    classify_integrity,
    correlate_pdf_certificates,
    is_legacy_document,
)


SOURCE_HASH = "1" * 64
SIGNED_HASH = "2" * 64
IMAGE_HASH = "3" * 64
CERTIFICATE_FINGERPRINT = "A" * 64


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"file_status": "failed"}, "red"),
        ({"database_hash_status": "failed"}, "red"),
        ({"evidence_hash_status": "failed"}, "red"),
        ({"signature_status": "invalid"}, "red"),
        ({"signature_status": "missing", "legacy": False}, "red"),
        ({"signature_status": "missing", "legacy": True}, "yellow"),
        ({"signature_status": "untrusted"}, "yellow"),
        ({"legacy": True}, "yellow"),
        ({"seal_hash_status": "historical"}, "yellow"),
        ({"evidence_hash_status": "historical"}, "yellow"),
        ({}, "green"),
    ],
)
def test_classify_integrity(overrides, expected):
    states = {
        "file_status": "valid",
        "database_hash_status": "valid",
        "seal_hash_status": "valid",
        "evidence_hash_status": "not_applicable",
        "signature_status": "valid",
        "legacy": False,
    }
    states.update(overrides)

    assert classify_integrity(**states) == expected


def test_legacy_signature_cutoff_includes_november_20_only():
    assert is_legacy_document(date(2026, 11, 20))
    assert not is_legacy_document(date(2026, 11, 21))


def test_classify_integrity_marks_inconsistent_database_evidence_red():
    assert classify_integrity(
        file_status="valid",
        database_hash_status="valid",
        seal_hash_status="valid",
        evidence_hash_status="valid",
        signature_status="valid",
        legacy=False,
        database_evidence_status="failed",
    ) == "red"


def test_receipt_evidence_links_database_record_to_event_and_seal():
    result = analyze_receipt_evidence(
        evidence_rows=[{
            "acceptance_text": "Aceptado.",
            "signer_full_name": "Persona de prueba",
            "signer_cuil": "20123456789",
            "period_label": "Noviembre 2026",
            "verification_id": "VER-TEST",
            "signer_user_id": "user-1",
            "batch_id": "batch-1",
            "receipt_id": "receipt-1",
            "receipt_sha256_at_sign_time": SOURCE_HASH,
            "final_pdf_sha256": SIGNED_HASH,
            "signature_image_path": "signatures/employee.png",
            "signature_image_sha256": IMAGE_HASH,
            "cert_fingerprint_sha256": CERTIFICATE_FINGERPRINT,
            "cert_serial": "1234",
            "cert_issuer": "CN=Issuer",
            "cert_subject": "CN=Signer",
            "cert_not_before": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "cert_not_after": datetime(2027, 1, 1, tzinfo=timezone.utc),
            "signature_algorithm": "sha256WithRSAEncryption",
            "sig_version": "v5",
            "signed_at": datetime(2026, 11, 20, tzinfo=timezone.utc),
            "validation_status": "valid",
            "ocsp_status": "good",
            "ocsp_checked_at": datetime(2026, 11, 20, tzinfo=timezone.utc),
            "validation_checked_at": datetime(2026, 11, 20, tzinfo=timezone.utc),
            "signing_method": "Digital-PAdES-LTV",
        }],
        seals=[{
            "seal_id": "SEAL-TEST",
            "signer_role": "employee",
            "pdf_hash": SIGNED_HASH,
            "metadata": {"v_id": "VER-TEST"},
        }],
        signature_events=[
            {
                "action": "SIGN",
                "actor_type": "employee",
                "actor_id": "user-1",
                "document_source": "payroll",
                "status_before": "pending_employee_signature",
                "status_after": "signed",
                "pdf_sha256_before": SOURCE_HASH,
                "pdf_sha256_after": SIGNED_HASH,
                "data": {
                    "signature_sha256": IMAGE_HASH,
                    "certificate_fingerprint": CERTIFICATE_FINGERPRINT,
                    "document_hash": SIGNED_HASH,
                    "signature_version": "v5",
                    "issuer": "CN=Issuer",
                    "signer_role": "employee",
                    "signer_identity_hash": "4" * 64,
                    "legal_acceptance_hash": hashlib.sha256(b"Aceptado.").hexdigest(),
                    "timestamp_source": "LOCAL_FALLBACK",
                },
            }
        ],
        document_hash=SIGNED_HASH,
        document_signed_at=None,
        legacy=False,
        document_batch_id="batch-1",
        document_id="receipt-1",
        document_source="payroll",
    )

    assert result["status"] == "valid"
    assert result["expected_certificates"] == [{
        "fingerprint": CERTIFICATE_FINGERPRINT,
        "serial": "1234",
    }]
    assert result["image_artifacts"] == [{
        "path": "signatures/employee.png",
        "expected_hash": IMAGE_HASH.lower(),
    }]


def test_receipt_evidence_detects_broken_event_hash_chain():
    result = analyze_receipt_evidence(
        evidence_rows=[],
        signature_events=[
            {"pdf_sha256_before": SOURCE_HASH, "pdf_sha256_after": SIGNED_HASH},
            {"pdf_sha256_before": IMAGE_HASH, "pdf_sha256_after": SOURCE_HASH},
        ],
        seals=[],
        document_hash=SOURCE_HASH,
        document_signed_at=None,
        legacy=False,
    )

    assert result["status"] == "failed"
    assert any("cadena de hashes" in detail for detail in result["details"])


def test_missing_receipt_evidence_is_incomplete_not_a_clean_verification():
    result = analyze_receipt_evidence(
        evidence_rows=[],
        signature_events=[],
        seals=[],
        document_hash=SIGNED_HASH,
        document_signed_at=None,
        legacy=False,
    )

    assert result["status"] == "warning"


def test_receipt_audit_hash_must_match_signature_history():
    result = analyze_receipt_evidence(
        evidence_rows=[],
        signature_events=[],
        seals=[],
        audit_events=[{
            "action": "SIMPLE_SIGN",
            "data": {"pdf_hash": SOURCE_HASH},
        }],
        document_hash=SIGNED_HASH,
        document_signed_at=None,
        legacy=False,
    )

    assert result["status"] == "failed"
    assert any("auditoría" in detail for detail in result["details"])


def test_pdf_certificate_is_compared_to_database_evidence():
    expected = [{"fingerprint": CERTIFICATE_FINGERPRINT, "serial": "1234"}]

    assert correlate_pdf_certificates(
        expected,
        [{
            "certificate_fingerprint": CERTIFICATE_FINGERPRINT.lower(),
            "certificate_serial": "1234",
        }],
    )["status"] == "valid"
    assert correlate_pdf_certificates(
        expected,
        [{
            "certificate_fingerprint": SOURCE_HASH,
            "certificate_serial": "1234",
        }],
    )["status"] == "failed"

