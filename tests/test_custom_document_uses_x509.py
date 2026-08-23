import hashlib
import os
import tempfile
from pathlib import Path

import fitz

os.environ.setdefault("SECRET_KEY", "test")

from modules import digital_signature as ds


def test_process_pdf_signs_custom_document_with_x509(monkeypatch, tmp_path):
    pdf_path = tmp_path / "input.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Documento personalizado")
    doc.save(pdf_path)
    doc.close()

    calls = []

    class FakeEngine:
        def stamp_signature_from_bytes(self, **kwargs):
            output_path = kwargs["output_path"]
            Path(output_path).write_bytes(pdf_path.read_bytes())
            return {"generated_seal_id": "seal-123"}

        def calculate_file_sha256(self, path):
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def fake_sign_pdf(input_path, receipt_id, signer_identity):
        calls.append((input_path, receipt_id, signer_identity))
        return {
            "status": "success",
            "signed_path": input_path,
            "fingerprint": "fingerprint-123",
            "issuer": "issuer-test",
            "id_hash": "id-hash-123",
            "signature_version": "v3_pki",
            "timestamp_source": "SUCCESS",
            "validation_status": "valid",
            "ocsp_status": "good",
            "crl_status": "valid",
            "validation_checked_at": "now",
            "validation_error": None,
            "serial_number": "1",
            "subject": "CN=Test",
            "not_before": "now",
            "not_after": "later",
            "signature_algorithm": "sha256",
            "signing_method": "test",
        }

    monkeypatch.setattr(ds, "STORAGE_ROOT", tmp_path)
    monkeypatch.setattr(ds, "get_signature_engine", lambda: FakeEngine())
    monkeypatch.setattr(ds.DigitalSignatureEngine, "_store_signature_image", lambda *args, **kwargs: tmp_path / "sig.png")
    monkeypatch.setattr(ds.x509_service, "sign_pdf", fake_sign_pdf)

    ctx = {
        "role": "employee",
        "receipt_id": "receipt-1",
        "organization_id": "org-1",
        "receipt_pdf_path": str(pdf_path),
        "next_status": "signed",
        "full_name": "Juan Perez",
        "cuil": "20-12345678-9",
        "dni": "12345678",
        "email": "juan@example.com",
        "user": {
            "id": "user-1",
            "role": "employee",
            "full_name": "Juan Perez",
            "dni": "12345678",
            "email": "juan@example.com",
            "organization_id": "org-1",
        },
        "source": "custom_document",
    }

    result = ds.DigitalSignatureEngine.process_pdf(ctx, b"fake-signature")

    assert result["signature_version"] == "v3_pki"
    assert len(calls) == 1
    assert calls[0][2]["full_name"] == "Juan Perez"
