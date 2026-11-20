from pathlib import Path

import pytest

from services import signature_file_service as signature_files
from services.encryption_service import EncryptionError


def test_decrypt_signature_pdf_uses_stored_metadata(monkeypatch, tmp_path):
    encrypted_path = tmp_path / "receipt.enc"
    encrypted_path.write_bytes(b"ciphertext")
    decrypted_path = tmp_path / "receipt.pdf"
    decrypted_path.write_bytes(b"%PDF-test")
    calls = {}

    class FakeEncryptionService:
        def get_metadata_for_path(self, db, file_path, organization_id):
            return {"purpose": "signed_receipt_pdf", "plaintext_sha256": "abc"}

        def decrypt_file_to_temp(self, db, file_path, **kwargs):
            calls.update(kwargs)
            return decrypted_path

    monkeypatch.setattr(
        signature_files,
        "get_encryption_service",
        lambda: FakeEncryptionService(),
    )

    result_path, temp_path = signature_files.decrypt_signature_pdf(
        object(),
        encrypted_path,
        organization_id="org-id",
        actor_id="employee-id",
    )

    assert result_path == decrypted_path
    assert temp_path == decrypted_path
    assert calls["organization_id"] == "org-id"
    assert calls["actor_id"] == "employee-id"
    assert calls["expected_plaintext_sha256"] == "abc"
    assert calls["purpose"] == "signed_receipt_pdf"


def test_decrypt_signature_pdf_leaves_plain_pdf_unchanged(monkeypatch, tmp_path):
    pdf_path = tmp_path / "receipt.pdf"
    pdf_path.write_bytes(b"%PDF-test")

    class FakeEncryptionService:
        def get_metadata_for_path(self, db, file_path, organization_id):
            return None

        def decrypt_file_to_temp(self, *args, **kwargs):
            raise AssertionError("plain PDFs must not be decrypted")

    monkeypatch.setattr(
        signature_files,
        "get_encryption_service",
        lambda: FakeEncryptionService(),
    )

    assert signature_files.decrypt_signature_pdf(
        object(),
        pdf_path,
        organization_id="org-id",
        actor_id="employee-id",
    ) == (pdf_path, None)


def test_decrypt_signature_pdf_rejects_unexpected_encryption_purpose(monkeypatch, tmp_path):
    class FakeEncryptionService:
        def get_metadata_for_path(self, db, file_path, organization_id):
            return {"purpose": "payment_receipt"}

    monkeypatch.setattr(
        signature_files,
        "get_encryption_service",
        lambda: FakeEncryptionService(),
    )

    with pytest.raises(EncryptionError):
        signature_files.decrypt_signature_pdf(
            object(),
            tmp_path / "receipt.pdf",
            organization_id="org-id",
            actor_id="employee-id",
        )


def test_signed_pdf_encryption_metadata_is_persisted(monkeypatch, tmp_path):
    signed_pdf = tmp_path / "signed.pdf"
    signature_image = tmp_path / "signature.png"
    signed_pdf.write_bytes(b"%PDF-test")
    signature_image.write_bytes(b"image")
    persisted = []

    class FakeEncryptionService:
        def encrypt_file_in_place(self, file_path, **kwargs):
            return {"storage_path": Path(file_path).name, **kwargs}

        def persist_metadata_and_audit(self, db, metadata, **kwargs):
            persisted.append((metadata, kwargs))

    fake_service = FakeEncryptionService()
    monkeypatch.setattr(signature_files, "get_encryption_service", lambda: fake_service)
    monkeypatch.setattr(signature_files.config, "APP_ENCRYPTION_ENABLED", True)
    result = {
        "signed_pdf_path": signed_pdf,
        "sig_image_path": signature_image,
        "new_pdf_sha256": "pdf-hash",
        "sig_image_sha256": "image-hash",
    }

    signature_files.encrypt_signed_pdf_result(
        object(),
        result,
        organization_id="org-id",
        actor_id="actor-id",
        actor_type="employee",
    )
    signature_files.persist_signed_pdf_encryption_metadata(
        object(),
        result,
        actor_id="actor-id",
        actor_type="employee",
    )

    assert len(result["encryption_metadata_items"]) == 2
    assert [entry[0]["purpose"] for entry in persisted] == [
        "signed_receipt_pdf",
        "signature_evidence_image",
    ]
