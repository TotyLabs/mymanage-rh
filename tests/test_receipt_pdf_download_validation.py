import pytest
from fastapi import HTTPException

from api import receipts


def test_unencrypted_non_pdf_payload_is_not_returned_as_pdf(monkeypatch, tmp_path):
    encrypted_payload = tmp_path / "receipt.pdf"
    encrypted_payload.write_bytes(b"ciphertext")
    monkeypatch.setattr(receipts, "_encryption_metadata_exists", lambda *args: False)

    with pytest.raises(HTTPException) as error:
        receipts._maybe_decrypted_file_response(
            object(),
            encrypted_payload,
            organization_id="org-id",
            user={"id": "employee-id"},
            purpose="signed_receipt_pdf",
            media_type="application/pdf",
        )

    assert error.value.status_code == 500
    assert error.value.detail == "pdf_unavailable"
