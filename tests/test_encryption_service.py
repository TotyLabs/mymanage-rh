import base64
import os
from pathlib import Path

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test")

from payroll_core import ALLOWED_STORAGE_DIR
from services.encryption_service import (
    EncryptionAccessDenied,
    EncryptionIntegrityError,
    EncryptionService,
    KmsError,
    LocalKmsProvider,
)


ORG_ID = "11111111-1111-1111-1111-111111111111"
OTHER_ORG_ID = "22222222-2222-2222-2222-222222222222"
FILE_ID = "33333333-3333-3333-3333-333333333333"


class _FakeMappings:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return _FakeMappings(self._row)

    def fetchone(self):
        return self._row


class _FakeDb:
    def __init__(self, metadata):
        self.metadata = metadata
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM file_encryption_metadata" in sql and "SELECT file_id" in sql:
            return _FakeResult(self.metadata)
        return _FakeResult()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def begin_nested(self):
        return self


class _FailingKmsProvider(LocalKmsProvider):
    def generate_data_key(self, encryption_context):
        raise KmsError("kms_down")


@pytest.fixture()
def encryption_service():
    master_key = base64.b64encode(b"\x01" * 32).decode("ascii")
    return EncryptionService(LocalKmsProvider(master_key, "local-test-key"))


@pytest.fixture()
def sensitive_file(tmp_path):
    base = Path(ALLOWED_STORAGE_DIR).resolve() / "test_encryption"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "receipt.pdf"
    path.write_bytes(b"%PDF-1.7\nfake signed payroll receipt\n%%EOF")
    yield path
    if path.exists():
        path.unlink()


def test_encrypts_and_decrypts_valid_pdf(encryption_service, sensitive_file):
    plaintext = sensitive_file.read_bytes()
    metadata = encryption_service.encrypt_file_in_place(
        sensitive_file,
        organization_id=ORG_ID,
        purpose="signed_receipt_pdf",
        file_id=FILE_ID,
    )

    assert sensitive_file.read_bytes() != plaintext
    assert metadata["algorithm"] == "AES-256-GCM"
    assert metadata["encrypted_data_key"]
    assert metadata["nonce"]
    assert metadata["auth_tag"]
    assert metadata["kms_key_id"] == "local-test-key"

    temp_path = encryption_service.decrypt_file_to_temp(
        _FakeDb(metadata),
        sensitive_file,
        organization_id=ORG_ID,
        actor_id=FILE_ID,
        actor_type="admin",
        purpose="signed_receipt_pdf",
        expected_plaintext_sha256=metadata["plaintext_sha256"],
        suffix=".pdf",
    )
    try:
        assert temp_path.read_bytes() == plaintext
    finally:
        EncryptionService.cleanup_temp_file(temp_path)


def test_decrypt_rejects_corrupt_ciphertext(encryption_service, sensitive_file):
    metadata = encryption_service.encrypt_file_in_place(
        sensitive_file,
        organization_id=ORG_ID,
        purpose="signed_receipt_pdf",
        file_id=FILE_ID,
    )
    ciphertext = bytearray(sensitive_file.read_bytes())
    ciphertext[0] ^= 0x01
    sensitive_file.write_bytes(ciphertext)

    with pytest.raises(EncryptionIntegrityError):
        encryption_service.decrypt_file_to_temp(
            _FakeDb(metadata),
            sensitive_file,
            organization_id=ORG_ID,
            actor_id=FILE_ID,
            actor_type="admin",
            purpose="signed_receipt_pdf",
            expected_plaintext_sha256=metadata["plaintext_sha256"],
        )


def test_cross_tenant_metadata_access_is_denied(encryption_service, sensitive_file):
    metadata = encryption_service.encrypt_file_in_place(
        sensitive_file,
        organization_id=ORG_ID,
        purpose="signed_receipt_pdf",
        file_id=FILE_ID,
    )
    metadata["organization_id"] = OTHER_ORG_ID

    with pytest.raises(EncryptionAccessDenied):
        encryption_service.decrypt_file_to_temp(
            _FakeDb(metadata),
            sensitive_file,
            organization_id=ORG_ID,
            actor_id=FILE_ID,
            actor_type="admin",
            purpose="signed_receipt_pdf",
        )


def test_kms_failure_is_fail_fast(sensitive_file):
    master_key = base64.b64encode(b"\x01" * 32).decode("ascii")
    service = EncryptionService(_FailingKmsProvider(master_key, "local-test-key"))

    with pytest.raises(KmsError):
        service.encrypt_file_in_place(
            sensitive_file,
            organization_id=ORG_ID,
            purpose="signed_receipt_pdf",
            file_id=FILE_ID,
        )


def test_storage_path_frozen_in_aad(encryption_service, sensitive_file):
    """Verifica que mover un archivo rompe el descifrado debido al invariant del AAD."""
    metadata = encryption_service.encrypt_file_in_place(
        sensitive_file,
        organization_id=ORG_ID,
        purpose="signed_receipt_pdf",
        file_id=FILE_ID,
    )
    
    # Simular un rename/move del archivo
    new_path = sensitive_file.parent / "renamed_receipt.pdf"
    os.rename(sensitive_file, new_path)
    
    try:
        # El descifrado debe fallar porque el path actual no coincide con el AAD congelado
        # (Nota: El service usa metadata['storage_path'] para calcular el AAD, 
        # pero si el archivo real está en un path distinto, el AAD calculado será diferente)
        with pytest.raises(EncryptionIntegrityError):
             encryption_service.decrypt_file_to_temp(
                _FakeDb(metadata),
                new_path,
                organization_id=ORG_ID,
                actor_id=FILE_ID,
                actor_type="admin",
                purpose="signed_receipt_pdf",
            )
    finally:
        if new_path.exists():
            os.rename(new_path, sensitive_file)


def test_rewrap_data_key(encryption_service):
    """Verifica la funcionalidad de rewrap sin descifrar el contenido."""
    # 1. Generar data key con context original
    ctx = {"purpose": "test", "file_id": "123"}
    dk = encryption_service.kms_provider.generate_data_key(ctx)
    original_plaintext = bytes(dk.plaintext_key)
    
    # 2. Rewrap con una nueva Master Key (en local provider, la master_key es la misma pero el ID cambia)
    new_edk = encryption_service.rewrap_data_key(
        plaintext_key=dk.plaintext_key,
        new_key_id="new-rotated-key",
        encryption_context=ctx
    )
    
    assert new_edk != dk.encrypted_data_key
    
    # 3. Validar que el nuevo EDK descifra a la misma plaintext key
    decrypted_key = encryption_service.kms_provider.decrypt_data_key(
        new_edk,
        ctx,
        "new-rotated-key"
    )
    assert bytes(decrypted_key) == original_plaintext


def test_trace_id_in_metadata(encryption_service, sensitive_file):
    """Verifica que la metadata de cifrado incluye un trace_id para correlación."""
    metadata = encryption_service.encrypt_file_in_place(
        sensitive_file,
        organization_id=ORG_ID,
        purpose="signed_receipt_pdf",
        file_id=FILE_ID,
    )
    assert "trace_id" in metadata
    assert len(metadata["trace_id"]) > 30 # UUID4 format
