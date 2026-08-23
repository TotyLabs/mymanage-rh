"""
Security Module — File encryption for sensitive documents.

Implements robust AES-256-GCM encryption for files at rest
integrated transparently into the file pipeline.
"""
import os
import logging
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import config

logger = logging.getLogger("dircom.payroll.security")

# Magic prefix to identify files encrypted by this module and avoid double encryption
MAGIC_PREFIX = b"YCP_ENC\x00"

def get_fallback_key() -> bytes:
    """
    Derives a 32-byte key from config.SECRET_KEY.
    Ensures cryptographic strength using SHA-256.
    """
    key_src = config.SECRET_KEY or "fallback-secure-key-for-dircom-payroll-2026"
    return hashlib.sha256(key_src.encode("utf-8")).digest()


def encrypt_file(file_path: str) -> str:
    """
    Encrypts a file at rest using AES-256-GCM.

    Args:
        file_path: Path to the file to encrypt

    Returns:
        Path to the (encrypted) file
    """
    if not config.APP_ENCRYPTION_ENABLED:
        logger.debug(f"security.encrypt_disabled: {os.path.basename(file_path)}")
        return file_path

    try:
        if not os.path.exists(file_path):
            logger.error(f"security.encrypt_failed: File not found at {file_path}")
            return file_path

        with open(file_path, "rb") as f:
            data = f.read()

        # Avoid double-encrypting files
        if data.startswith(MAGIC_PREFIX):
            logger.debug(f"security.encrypt_already_encrypted: {os.path.basename(file_path)}")
            return file_path

        key = get_fallback_key()
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)

        ciphertext = aesgcm.encrypt(nonce, data, None)
        encrypted_payload = MAGIC_PREFIX + nonce + ciphertext

        # Atomic replacement
        temp_path = file_path + ".tmp"
        with open(temp_path, "wb") as f:
            f.write(encrypted_payload)
        
        os.replace(temp_path, file_path)
        logger.info(f"security.encrypt_success: {os.path.basename(file_path)}")
        return file_path

    except Exception as e:
        logger.error(f"security.encrypt_failed: {e}")
        return file_path


def decrypt_file(file_path: str) -> bytes:
    """
    Decrypts a file for reading.

    Args:
        file_path: Path to the encrypted file

    Returns:
        Decrypted file contents as bytes
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "rb") as f:
        data = f.read()

    if data.startswith(MAGIC_PREFIX):
        try:
            key = get_fallback_key()
            aesgcm = AESGCM(key)
            nonce = data[len(MAGIC_PREFIX):len(MAGIC_PREFIX) + 12]
            ciphertext = data[len(MAGIC_PREFIX) + 12:]
            
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            logger.debug(f"security.decrypt_success: {os.path.basename(file_path)}")
            return plaintext
        except Exception as e:
            logger.critical(f"security.decrypt_failed: Integrity verification failed for {file_path} - {e}")
            raise RuntimeError("Fallo de integridad al descifrar archivo protegido.") from e

    return data
