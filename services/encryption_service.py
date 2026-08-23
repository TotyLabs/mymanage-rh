"""
Application-level envelope encryption for sensitive payroll files.

The service is intentionally provider-neutral:
- AWS KMS uses GenerateDataKey / Decrypt.
- Google Cloud KMS wraps an application-generated data key.
- Local KMS is only for development/testing and requires an explicit master key.

No plaintext data key is persisted. File payloads are encrypted with AES-256-GCM
and the encrypted data key plus GCM parameters are persisted separately.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from sqlalchemy.orm import Session

import config
from payroll_core import ALLOWED_STORAGE_DIR, audit, safe_transaction
from services import secure_temp

logger = logging.getLogger("dircom.payroll.encryption")

ALGORITHM_AES_256_GCM = "AES-256-GCM"
NONCE_SIZE_BYTES = 12
GCM_TAG_SIZE_BYTES = 16

ZEROIZATION_DISCLAIMER = """
LIMITACIÓN DE SEGURIDAD: Zeroization en Python.
La limpieza de memoria de data keys en runtime Python es 'best-effort'. 
Debido al recolector de basura (GC) y la inmutabilidad interna de ciertos objetos, 
no se puede garantizar la eliminación física total de todos los residuos de la llave 
en la RAM del host. Mitigamos este riesgo minimizando el tiempo de vida en memoria, 
usando tipos mutables (bytearray) y evitando el registro en logs.
"""


class EncryptionError(Exception):
    """Base class for application encryption failures."""


class KmsError(EncryptionError):
    """Raised when KMS cannot generate or decrypt a data key."""


class EncryptionMetadataNotFound(EncryptionError):
    """Raised when an encrypted file has no matching metadata record."""


class EncryptionAccessDenied(EncryptionError):
    """Raised when encryption metadata is accessed across tenant boundaries."""


class EncryptionIntegrityError(EncryptionError):
    """Raised when AES-GCM authentication or plaintext hash verification fails."""


@dataclass(frozen=True)
class GeneratedDataKey:
    plaintext_key: bytearray
    encrypted_data_key: str
    kms_key_id: str
    provider: str


class KmsProvider:
    """Provider interface for envelope encryption root-of-trust operations."""

    provider_name = "abstract"

    def generate_data_key(self, encryption_context: Dict[str, str]) -> GeneratedDataKey:
        raise NotImplementedError

    def decrypt_data_key(
        self,
        encrypted_data_key: str,
        encryption_context: Dict[str, str],
        kms_key_id: str,
    ) -> bytearray:
        raise NotImplementedError

    def rewrap_data_key(
        self,
        plaintext_key: bytearray,
        encryption_context: Dict[str, str],
        new_kms_key_id: str,
    ) -> str:
        """Wraps an existing plaintext key with a new KEK."""
        raise NotImplementedError


class LocalKmsProvider(KmsProvider):
    """
    Local development provider.

    This is not a production KMS. It wraps data keys using an explicit 32-byte
    master key supplied through APP_ENCRYPTION_LOCAL_MASTER_KEY.
    """

    provider_name = "local"

    def __init__(self, master_key_b64: str, key_id: str = "local-dev-key") -> None:
        if not master_key_b64:
            raise KmsError("APP_ENCRYPTION_LOCAL_MASTER_KEY is required for local KMS mode.")
        try:
            master_key = base64.b64decode(master_key_b64, validate=True)
        except Exception as exc:
            raise KmsError("APP_ENCRYPTION_LOCAL_MASTER_KEY must be valid base64.") from exc
        if len(master_key) != 32:
            raise KmsError("APP_ENCRYPTION_LOCAL_MASTER_KEY must decode to 32 bytes.")
        self._master_key = bytearray(master_key)
        self._key_id = key_id

    def generate_data_key(self, encryption_context: Dict[str, str]) -> GeneratedDataKey:
        plaintext_key = bytearray(secrets.token_bytes(32))
        aad = _context_to_aad(encryption_context)
        nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
        try:
            wrapped = AESGCM(bytes(self._master_key)).encrypt(nonce, bytes(plaintext_key), aad)
        except Exception as exc:
            _zeroize(plaintext_key)
            raise KmsError("local_kms_generate_data_key_failed") from exc

        blob = {
            "v": 1,
            "nonce": _b64(nonce),
            "ciphertext": _b64(wrapped),
        }
        return GeneratedDataKey(
            plaintext_key=plaintext_key,
            encrypted_data_key=_b64(json.dumps(blob, separators=(",", ":")).encode("utf-8")),
            kms_key_id=self._key_id,
            provider=self.provider_name,
        )

    def decrypt_data_key(
        self,
        encrypted_data_key: str,
        encryption_context: Dict[str, str],
        kms_key_id: str,
    ) -> bytearray:
        try:
            blob = json.loads(base64.b64decode(encrypted_data_key).decode("utf-8"))
            nonce = base64.b64decode(blob["nonce"])
            ciphertext = base64.b64decode(blob["ciphertext"])
            plaintext = AESGCM(bytes(self._master_key)).decrypt(
                nonce,
                ciphertext,
                _context_to_aad(encryption_context),
            )
        except InvalidTag as exc:
            raise KmsError("local_kms_data_key_authentication_failed") from exc
        except Exception as exc:
            raise KmsError("local_kms_decrypt_data_key_failed") from exc

        if len(plaintext) != 32:
            raise KmsError("local_kms_invalid_data_key_length")
        return bytearray(plaintext)

    def rewrap_data_key(
        self,
        plaintext_key: bytearray,
        encryption_context: Dict[str, str],
        new_kms_key_id: str,
    ) -> str:
        aad = _context_to_aad(encryption_context)
        nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
        try:
            wrapped = AESGCM(bytes(self._master_key)).encrypt(nonce, bytes(plaintext_key), aad)
        except Exception as exc:
            raise KmsError("local_kms_rewrap_data_key_failed") from exc

        blob = {
            "v": 1,
            "nonce": _b64(nonce),
            "ciphertext": _b64(wrapped),
        }
        return _b64(json.dumps(blob, separators=(",", ":")).encode("utf-8"))


class AwsKmsProvider(KmsProvider):
    """AWS KMS provider using GenerateDataKey and Decrypt."""

    provider_name = "aws"

    def __init__(self, key_id: str, region_name: Optional[str] = None) -> None:
        if not key_id:
            raise KmsError("APP_ENCRYPTION_KMS_KEY_ID is required for AWS KMS mode.")
        try:
            import boto3  # type: ignore
        except Exception as exc:
            raise KmsError("boto3 is required for AWS KMS mode.") from exc
        self._key_id = key_id
        self._client = boto3.client("kms", region_name=region_name)

    def generate_data_key(self, encryption_context: Dict[str, str]) -> GeneratedDataKey:
        try:
            res = self._client.generate_data_key(
                KeyId=self._key_id,
                KeySpec="AES_256",
                EncryptionContext=encryption_context,
            )
        except Exception as exc:
            raise KmsError("aws_kms_generate_data_key_failed") from exc
        return GeneratedDataKey(
            plaintext_key=bytearray(res["Plaintext"]),
            encrypted_data_key=_b64(res["CiphertextBlob"]),
            kms_key_id=res.get("KeyId", self._key_id),
            provider=self.provider_name,
        )

    def decrypt_data_key(
        self,
        encrypted_data_key: str,
        encryption_context: Dict[str, str],
        kms_key_id: str,
    ) -> bytearray:
        try:
            res = self._client.decrypt(
                CiphertextBlob=base64.b64decode(encrypted_data_key),
                EncryptionContext=encryption_context,
                KeyId=kms_key_id,
            )
        except Exception as exc:
            raise KmsError("aws_kms_decrypt_data_key_failed") from exc
        plaintext = res["Plaintext"]
        if len(plaintext) != 32:
            raise KmsError("aws_kms_invalid_data_key_length")
        return bytearray(plaintext)

    def rewrap_data_key(
        self,
        plaintext_key: bytearray,
        encryption_context: Dict[str, str],
        new_kms_key_id: str,
    ) -> str:
        try:
            res = self._client.encrypt(
                KeyId=new_kms_key_id,
                Plaintext=bytes(plaintext_key),
                EncryptionContext=encryption_context,
            )
        except Exception as exc:
            raise KmsError("aws_kms_rewrap_data_key_failed") from exc
        return _b64(res["CiphertextBlob"])


class GcpKmsProvider(KmsProvider):
    """
    Google Cloud KMS provider.

    GCP Cloud KMS does not expose AWS-style GenerateDataKey. This provider
    generates a random data key locally and wraps it with Cloud KMS Encrypt.
    """

    provider_name = "gcp"

    def __init__(self, key_name: str) -> None:
        if not key_name:
            raise KmsError("APP_ENCRYPTION_KMS_KEY_ID is required for GCP KMS mode.")
        try:
            from google.cloud import kms  # type: ignore
        except Exception as exc:
            raise KmsError("google-cloud-kms is required for GCP KMS mode.") from exc
        self._key_name = key_name
        self._client = kms.KeyManagementServiceClient()

    def generate_data_key(self, encryption_context: Dict[str, str]) -> GeneratedDataKey:
        plaintext_key = bytearray(secrets.token_bytes(32))
        try:
            res = self._client.encrypt(
                request={
                    "name": self._key_name,
                    "plaintext": bytes(plaintext_key),
                    "additional_authenticated_data": _context_to_aad(encryption_context),
                }
            )
        except Exception as exc:
            _zeroize(plaintext_key)
            raise KmsError("gcp_kms_wrap_data_key_failed") from exc
        return GeneratedDataKey(
            plaintext_key=plaintext_key,
            encrypted_data_key=_b64(res.ciphertext),
            kms_key_id=self._key_name,
            provider=self.provider_name,
        )

    def decrypt_data_key(
        self,
        encrypted_data_key: str,
        encryption_context: Dict[str, str],
        kms_key_id: str,
    ) -> bytearray:
        try:
            res = self._client.decrypt(
                request={
                    "name": kms_key_id,
                    "ciphertext": base64.b64decode(encrypted_data_key),
                    "additional_authenticated_data": _context_to_aad(encryption_context),
                }
            )
        except Exception as exc:
            raise KmsError("gcp_kms_unwrap_data_key_failed") from exc
        plaintext = res.plaintext
        if len(plaintext) != 32:
            raise KmsError("gcp_kms_invalid_data_key_length")
        return bytearray(plaintext)

    def rewrap_data_key(
        self,
        plaintext_key: bytearray,
        encryption_context: Dict[str, str],
        new_kms_key_id: str,
    ) -> str:
        try:
            res = self._client.encrypt(
                request={
                    "name": new_kms_key_id,
                    "plaintext": bytes(plaintext_key),
                    "additional_authenticated_data": _context_to_aad(encryption_context),
                }
            )
        except Exception as exc:
            raise KmsError("gcp_kms_rewrap_data_key_failed") from exc
        return _b64(res.ciphertext)


class EncryptionService:
    """Encrypts and decrypts sensitive files using envelope encryption."""

    def __init__(self, kms_provider: KmsProvider) -> None:
        self.kms_provider = kms_provider

    @staticmethod
    def storage_key(file_path: Path | str) -> str:
        path = Path(file_path).resolve()
        root = Path(ALLOWED_STORAGE_DIR).resolve()
        try:
            return path.relative_to(root).as_posix()
        except ValueError as exc:
            raise EncryptionAccessDenied("file_outside_allowed_storage") from exc

    def encrypt_file_in_place(
        self,
        file_path: Path | str,
        *,
        organization_id: str,
        purpose: str,
        file_id: Optional[str] = None,
        plaintext_sha256: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Encrypts a file in place and returns metadata to persist transactionally.

        The caller is responsible for persisting metadata with
        persist_metadata_and_audit() in the same business transaction.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            raise EncryptionError("file_not_found_for_encryption")

        file_id = file_id or str(uuid.uuid4())
        trace_id = str(uuid.uuid4())
        storage_path = self.storage_key(path)
        plaintext = path.read_bytes()
        plaintext_hash = plaintext_sha256 or hashlib.sha256(plaintext).hexdigest()
        encryption_context = self._encryption_context(
            file_id=file_id,
            organization_id=organization_id,
            purpose=purpose,
            storage_path=storage_path,
        )

        data_key: Optional[GeneratedDataKey] = None
        raw_key: Optional[bytearray] = None
        try:
            data_key = self.kms_provider.generate_data_key(encryption_context)
            raw_key = data_key.plaintext_key
            nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
            aad = self._file_aad(
                file_id=file_id,
                organization_id=organization_id,
                purpose=purpose,
                storage_path=storage_path,
                kms_key_id=data_key.kms_key_id,
            )
            encrypted = AESGCM(bytes(raw_key)).encrypt(nonce, plaintext, aad)
            ciphertext = encrypted[:-GCM_TAG_SIZE_BYTES]
            auth_tag = encrypted[-GCM_TAG_SIZE_BYTES:]
            ciphertext_hash = hashlib.sha256(ciphertext).hexdigest()
            self._atomic_replace(path, ciphertext)
        except KmsError:
            raise
        except Exception as exc:
            raise EncryptionError("file_encryption_failed") from exc
        finally:
            if raw_key is not None:
                # Security: Best-effort zeroization of the data key
                _zeroize(raw_key)
            del plaintext

        return {
            "file_id": file_id,
            "trace_id": trace_id,
            "organization_id": str(organization_id),
            "storage_path": storage_path,
            "encrypted_data_key": data_key.encrypted_data_key,
            "nonce": _b64(nonce),
            "auth_tag": _b64(auth_tag),
            "algorithm": ALGORITHM_AES_256_GCM,
            "kms_key_id": data_key.kms_key_id,
            "kms_provider": data_key.provider,
            "purpose": purpose,
            "plaintext_sha256": plaintext_hash,
            "ciphertext_sha256": ciphertext_hash,
            "encryption_context": encryption_context,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def decrypt_file_to_temp(
        self,
        db: Session,
        file_path: Path | str,
        *,
        organization_id: str,
        actor_id: Optional[str],
        actor_type: str,
        purpose: str,
        expected_plaintext_sha256: Optional[str] = None,
        suffix: Optional[str] = None,
    ) -> Path:
        """Decrypts an encrypted file into a temporary file for one response."""
        metadata = self.get_metadata_for_path(db, file_path, organization_id)
        if not metadata:
            raise EncryptionMetadataNotFound("encryption_metadata_not_found")
        if str(metadata["organization_id"]) != str(organization_id):
            raise EncryptionAccessDenied("cross_tenant_encryption_metadata_access")

        path = Path(file_path).resolve()
        ciphertext = path.read_bytes()
        ciphertext_hash = hashlib.sha256(ciphertext).hexdigest()
        if metadata.get("ciphertext_sha256") and ciphertext_hash != metadata["ciphertext_sha256"]:
            raise EncryptionIntegrityError("ciphertext_hash_mismatch")

        encrypted_data_key = metadata["encrypted_data_key"]
        kms_key_id = metadata["kms_key_id"]
        encryption_context = _json_or_dict(metadata.get("encryption_context")) or self._encryption_context(
            file_id=str(metadata["file_id"]),
            organization_id=str(organization_id),
            purpose=metadata.get("purpose") or purpose,
            storage_path=metadata["storage_path"],
        )

        raw_key: Optional[bytearray] = None
        plaintext: Optional[bytes] = None
        try:
            raw_key = self.kms_provider.decrypt_data_key(
                encrypted_data_key,
                _string_context(encryption_context),
                kms_key_id,
            )
            current_storage_path = self.storage_key(file_path)
            aad = self._file_aad(
                file_id=str(metadata["file_id"]),
                organization_id=str(organization_id),
                purpose=metadata.get("purpose") or purpose,
                storage_path=current_storage_path,
                kms_key_id=kms_key_id,
            )
            encrypted = ciphertext + base64.b64decode(metadata["auth_tag"])
            plaintext = AESGCM(bytes(raw_key)).decrypt(
                base64.b64decode(metadata["nonce"]),
                encrypted,
                aad,
            )
        except InvalidTag as exc:
            raise EncryptionIntegrityError("auth_tag_mismatch") from exc
        except KmsError:
            self.record_kms_error(
                db,
                organization_id=str(organization_id),
                actor_id=actor_id,
                actor_type=actor_type,
                file_id=str(metadata["file_id"]),
                purpose=purpose,
                error_code="kms_decrypt_failed",
            )
            raise
        except Exception as exc:
            raise EncryptionError("file_decryption_failed") from exc
        finally:
            if raw_key is not None:
                # Security: Best-effort zeroization of the data key
                _zeroize(raw_key)

        plaintext_hash = hashlib.sha256(plaintext).hexdigest()
        expected_hash = expected_plaintext_sha256 or metadata.get("plaintext_sha256")
        if expected_hash and plaintext_hash != expected_hash:
            del plaintext
            raise EncryptionIntegrityError("plaintext_hash_mismatch")

        trace_id = str(uuid.uuid4())
        request_id = getattr(db, "_request_id", None)

        # Mitigación de Plaintext Transitorio: usar secure temp dir (tmpfs en Linux)
        fd, tmp_name = secure_temp.secure_mkstemp(prefix="yc_decrypted_", suffix=suffix or path.suffix)
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(plaintext)
                tmp.flush()
                try:
                    os.fsync(tmp.fileno())
                except OSError:
                    pass
        finally:
            del plaintext

        with safe_transaction(db):
            db.execute(
                text("""
                    UPDATE file_encryption_metadata
                    SET last_decrypted_at = now()
                    WHERE file_id = CAST(:file_id AS UUID)
                      AND organization_id = CAST(:org AS UUID)
                """),
                {"file_id": metadata["file_id"], "org": organization_id},
            )
            self._audit(
                db,
                organization_id=str(organization_id),
                actor_type=actor_type,
                actor_id=actor_id,
                action="kms_key_used",
                entity_id=str(metadata["file_id"]),
                trace_id=trace_id,
                request_id=request_id,
                data={
                    "file_id": str(metadata["file_id"]),
                    "purpose": purpose,
                    "kms_key_id": kms_key_id,
                    "kms_provider": metadata.get("kms_provider"),
                    "operation": "decrypt_data_key",
                },
            )
            self._audit(
                db,
                organization_id=str(organization_id),
                actor_type=actor_type,
                actor_id=actor_id,
                action="document_decrypted",
                entity_id=str(metadata["file_id"]),
                trace_id=trace_id,
                request_id=request_id,
                data={
                    "file_id": str(metadata["file_id"]),
                    "storage_path": metadata["storage_path"],
                    "purpose": purpose,
                    "algorithm": metadata["algorithm"],
                },
            )

        return Path(tmp_name)

    def get_metadata_for_path(
        self,
        db: Session,
        file_path: Path | str,
        organization_id: str,
    ) -> Optional[Dict[str, Any]]:
        storage_path = self.storage_key(file_path)
        row = db.execute(
            text("""
                SELECT file_id, organization_id, storage_path, encrypted_data_key,
                       nonce, auth_tag, algorithm, kms_key_id, kms_provider,
                       purpose, plaintext_sha256, ciphertext_sha256,
                       encryption_context, created_at
                FROM file_encryption_metadata
                WHERE organization_id = CAST(:org AS UUID)
                  AND storage_path = :storage_path
                LIMIT 1
            """),
            {"org": organization_id, "storage_path": storage_path},
        ).mappings().fetchone()
        return dict(row) if row else None

    def is_encrypted(self, db: Session, file_path: Path | str, organization_id: str) -> bool:
        return self.get_metadata_for_path(db, file_path, organization_id) is not None

    def persist_metadata_and_audit(
        self,
        db: Session,
        metadata: Dict[str, Any],
        *,
        actor_id: Optional[str],
        actor_type: str,
    ) -> None:
        """Persists encryption metadata and mandatory audit events."""
        trace_id = metadata.get("trace_id") or str(uuid.uuid4())
        request_id = getattr(db, "_request_id", None)

        with safe_transaction(db):
            db.execute(
                text("""
                    INSERT INTO file_encryption_metadata (
                        file_id, organization_id, storage_path, encrypted_data_key,
                        nonce, auth_tag, algorithm, kms_key_id, kms_provider,
                        purpose, plaintext_sha256, ciphertext_sha256,
                        encryption_context, created_by, created_at
                    ) VALUES (
                        CAST(:file_id AS UUID), CAST(:organization_id AS UUID), :storage_path,
                        :encrypted_data_key, :nonce, :auth_tag, :algorithm,
                        :kms_key_id, :kms_provider, :purpose, :plaintext_sha256,
                        :ciphertext_sha256, CAST(:encryption_context AS JSONB),
                        CAST(:created_by AS UUID), :created_at
                    )
                    ON CONFLICT (organization_id, storage_path) DO UPDATE SET
                        file_id = EXCLUDED.file_id,
                        encrypted_data_key = EXCLUDED.encrypted_data_key,
                        nonce = EXCLUDED.nonce,
                        auth_tag = EXCLUDED.auth_tag,
                        algorithm = EXCLUDED.algorithm,
                        kms_key_id = EXCLUDED.kms_key_id,
                        kms_provider = EXCLUDED.kms_provider,
                        purpose = EXCLUDED.purpose,
                        plaintext_sha256 = EXCLUDED.plaintext_sha256,
                        ciphertext_sha256 = EXCLUDED.ciphertext_sha256,
                        encryption_context = EXCLUDED.encryption_context,
                        created_by = EXCLUDED.created_by,
                        created_at = EXCLUDED.created_at
                """),
                {
                    **metadata,
                    "encryption_context": json.dumps(metadata.get("encryption_context") or {}),
                    "created_by": actor_id,
                    "created_at": _parse_iso(metadata["created_at"]),
                },
            )
            self._audit(
                db,
                organization_id=metadata["organization_id"],
                actor_type=actor_type,
                actor_id=actor_id,
                action="kms_key_used",
                entity_id=metadata["file_id"],
                trace_id=trace_id,
                request_id=request_id,
                data={
                    "file_id": metadata["file_id"],
                    "purpose": metadata["purpose"],
                    "kms_key_id": metadata["kms_key_id"],
                    "kms_provider": metadata["kms_provider"],
                    "operation": "generate_data_key",
                },
            )
            self._audit(
                db,
                organization_id=metadata["organization_id"],
                actor_type=actor_type,
                actor_id=actor_id,
                action="document_encrypted",
                entity_id=metadata["file_id"],
                trace_id=trace_id,
                request_id=request_id,
                data={
                    "file_id": metadata["file_id"],
                    "storage_path": metadata["storage_path"],
                    "purpose": metadata["purpose"],
                    "algorithm": metadata["algorithm"],
                    "plaintext_sha256": metadata["plaintext_sha256"],
                    "ciphertext_sha256": metadata["ciphertext_sha256"],
                },
            )

    def record_kms_error(
        self,
        db: Session,
        *,
        organization_id: str,
        actor_id: Optional[str],
        actor_type: str,
        file_id: str,
        purpose: str,
        error_code: str,
    ) -> None:
        record_kms_error_event(
            db,
            organization_id=organization_id,
            actor_id=actor_id,
            actor_type=actor_type,
            file_id=file_id,
            purpose=purpose,
            error_code=error_code,
            request_id=getattr(db, "_request_id", None),
        )

    def rewrap_data_key(
        self,
        plaintext_key: bytearray,
        new_key_id: str,
        encryption_context: Dict[str, str],
    ) -> str:
        """
        Rewraps an existing plaintext data key with a new KEK.
        Does not touch the file ciphertext.
        """
        return self.kms_provider.rewrap_data_key(
            plaintext_key=plaintext_key,
            encryption_context=encryption_context,
            new_kms_key_id=new_key_id,
        )

    @staticmethod
    def cleanup_temp_file(file_path: Path | str) -> None:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            logger.warning("decrypted_temp_file_cleanup_failed")

    @staticmethod
    def _atomic_replace(path: Path, data: bytes) -> None:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".enc.tmp")
        try:
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(data)
                tmp.flush()
                try:
                    os.fsync(tmp.fileno())
                except OSError:
                    pass
            os.replace(tmp_name, path)
        except Exception:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    @staticmethod
    def _encryption_context(
        *,
        file_id: str,
        organization_id: str,
        purpose: str,
        storage_path: str,
    ) -> Dict[str, str]:
        """
        Generates the encryption context for KMS operations.
        INVARIANTE CRÍTICO: El 'storage_path' queda congelado en el contexto.
        Cualquier cambio de path después del cifrado invalidará el descifrado.
        """
        return {
            "system": "MyManageRH",
            "file_id": str(file_id),
            "organization_id": str(organization_id),
            "purpose": str(purpose),
            "storage_path": str(storage_path),
        }

    @staticmethod
    def _file_aad(
        *,
        file_id: str,
        organization_id: str,
        purpose: str,
        storage_path: str,
        kms_key_id: str,
    ) -> bytes:
        """
        Generates Additional Authenticated Data (AAD) for AES-GCM.
        INVARIANTE CRÍTICO: El 'storage_path' forma parte del binding criptográfico.
        Si el archivo se mueve o renombra, el descifrado fallará por auth_tag mismatch.
        """
        return _context_to_aad(
            {
                "file_id": str(file_id),
                "organization_id": str(organization_id),
                "purpose": str(purpose),
                "storage_path": str(storage_path),
                "algorithm": ALGORITHM_AES_256_GCM,
                "kms_key_id": str(kms_key_id),
            }
        )

    @staticmethod
    def _audit(
        db: Session,
        *,
        organization_id: str,
        actor_type: str,
        actor_id: Optional[str],
        action: str,
        entity_id: Optional[str],
        data: Dict[str, Any],
        trace_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> None:
        safe_actor_type = actor_type if actor_type in {"admin", "employee", "system"} else "system"
        audit_data = {**(data or {})}
        if trace_id:
            audit_data["trace_id"] = trace_id
        if request_id:
            audit_data["request_id"] = request_id
        audit(db, organization_id, safe_actor_type, actor_id, action, entity_id, audit_data)


_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    global _service
    if _service is not None:
        return _service

    provider_name = config.APP_ENCRYPTION_PROVIDER.lower()
    if provider_name == "aws":
        provider = AwsKmsProvider(config.APP_ENCRYPTION_KMS_KEY_ID, config.APP_ENCRYPTION_AWS_REGION)
    elif provider_name == "gcp":
        provider = GcpKmsProvider(config.APP_ENCRYPTION_KMS_KEY_ID)
    elif provider_name == "local":
        provider = LocalKmsProvider(
            config.APP_ENCRYPTION_LOCAL_MASTER_KEY,
            config.APP_ENCRYPTION_KMS_KEY_ID or "local-dev-key",
        )
    else:
        raise KmsError(f"unsupported_kms_provider:{provider_name}")

    _service = EncryptionService(provider)
    return _service


def encryption_actor_type(user: Dict[str, Any]) -> str:
    role = (user or {}).get("role")
    return role if role in {"admin", "employee"} else "system"


def record_kms_error_event(
    db: Session,
    *,
    organization_id: str,
    actor_id: Optional[str],
    actor_type: str,
    file_id: str,
    purpose: str,
    error_code: str,
    request_id: Optional[str] = None,
) -> None:
    safe_actor_type = actor_type if actor_type in {"admin", "employee", "system"} else "system"
    audit_data = {
        "file_id": file_id,
        "purpose": purpose,
        "error_code": error_code,
    }
    if request_id:
        audit_data["request_id"] = request_id
    with safe_transaction(db):
        audit(
            db,
            organization_id,
            safe_actor_type,
            actor_id,
            "kms_error",
            file_id,
            audit_data,
        )


def _context_to_aad(context: Dict[str, Any]) -> bytes:
    return json.dumps(_string_context(context), sort_keys=True, separators=(",", ":")).encode("utf-8")


def _string_context(context: Dict[str, Any]) -> Dict[str, str]:
    return {str(k): str(v) for k, v in (context or {}).items()}


def _json_or_dict(value: Any) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _zeroize(buf: bytearray) -> None:
    """
    Sobrescribe el contenido de un buffer mutable con ceros.
    NOTA: Esto es 'best-effort' en Python debido a cómo funciona el GC
    y la gestión de memoria del intérprete. Se usa para mitigar riesgos,
    pero no garantiza eliminación física inmediata de la RAM.
    """
    for i in range(len(buf)):
        buf[i] = 0


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
