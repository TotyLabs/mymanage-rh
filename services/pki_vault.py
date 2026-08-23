import os
import base64
import logging
from pathlib import Path
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy.orm import Session
from sqlalchemy import text

import config
from models.pki import KeyMetadata

logger = logging.getLogger("dircom.payroll.pki")

class SecureKeyVault:
    """
    Industrial-grade Software HSM abstraction.
    Handles versioned, encrypted storage of PKI keys with AES-256-GCM.
    """
    def __init__(self, master_key: str):
        # Derive a 256-bit key from the master_key string
        # PEP 0524: Ensure master_key is sufficient entropy
        salt = b"dircom-pki-immutable-salt-v1" 
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        self.aes_key = kdf.derive(master_key.encode())
        self.aead = AESGCM(self.aes_key)

    def encrypt_key(self, data: bytes) -> tuple[bytes, bytes]:
        nonce = os.urandom(12)
        encrypted_data = self.aead.encrypt(nonce, data, None)
        return nonce, encrypted_data

    def decrypt_key(self, nonce: bytes, encrypted_data: bytes) -> bytes:
        return self.aead.decrypt(nonce, encrypted_data, None)

    def store_new_key(self, db: Session, key_id: str, raw_data: bytes, expires_at=None) -> KeyMetadata:
        """
        Stores a new version of a key, encrypted on disk, with DB metadata.
        """
        # 1. Get latest version
        last = db.query(KeyMetadata).filter(KeyMetadata.key_id == key_id).order_by(KeyMetadata.version.desc()).first()
        new_version = (last.version + 1) if last else 1
        
        # 2. Encrypt
        nonce, encrypted_data = self.encrypt_key(raw_data)
        
        # 3. Save to disk: {STORAGE}/pki/{key_id}_v{version}.enc
        pki_dir = Path(config.ALLOWED_STORAGE_DIR) / "pki"
        pki_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{key_id}_v{new_version}.enc"
        file_path = pki_dir / filename
        
        # Store as [nonce(12)][encrypted_data]
        # We use atomic write pattern here as well
        temp_path = file_path.with_suffix(".tmp")
        with open(temp_path, "wb") as f:
            f.write(nonce + encrypted_data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, file_path)
            
        # 4. Fingerprint (SHA256 of raw data) - Used for non-repudiation binding
        digest = hashes.Hash(hashes.SHA256())
        digest.update(raw_data)
        fp_hex = digest.finalize().hex().upper()
        
        # 5. DB record
        meta = KeyMetadata(
            key_id=key_id,
            version=new_version,
            fingerprint=fp_hex,
            encrypted_path=str(file_path.relative_to(config.ALLOWED_STORAGE_DIR)),
            expires_at=expires_at
        )
        # Retire old keys of the same ID (if any)
        if last:
            db.query(KeyMetadata).filter(
                KeyMetadata.key_id == key_id, 
                KeyMetadata.status == 'active'
            ).update({"status": "retired", "retired_at": datetime.now(timezone.utc)})
            
        db.add(meta)
        db.flush()
        
        logger.info(f"PKI_VAULT: Stored new key version. ID={key_id} V={new_version} FP={fp_hex[:8]}...")
        return meta

    def get_active_key(self, db: Session, key_id: str) -> tuple[bytes, KeyMetadata]:
        """
        Retrieves and decrypts the current active version of a key.
        """
        meta = db.query(KeyMetadata).filter(
            KeyMetadata.key_id == key_id,
            KeyMetadata.status == 'active'
        ).order_by(KeyMetadata.version.desc()).first()
        
        if not meta:
            logger.error(f"PKI_VAULT: No active key found for {key_id}")
            raise RuntimeError(f"No active PKI key found for ID: {key_id}")
            
        full_path = Path(config.ALLOWED_STORAGE_DIR) / meta.encrypted_path
        if not full_path.exists():
            raise FileNotFoundError(f"Encrypted key file missing: {full_path}")
            
        with open(full_path, "rb") as f:
            raw_blob = f.read()
            
        if len(raw_blob) < 13: # at least 12 nonce + 1 byte data
            raise ValueError(f"Encrypted key blob corrupted: {full_path}")
            
        nonce = raw_blob[:12]
        encrypted_data = raw_blob[12:]
        
        try:
            decrypted = self.decrypt_key(nonce, encrypted_data)
        except Exception as e:
            logger.critical(f"PKI_VAULT: Decryption failed for {key_id} v{meta.version}. Master key mismatch?")
            raise RuntimeError(f"Decryption failed for key {key_id}. Verify MASTER_ENCRYPTION_KEY.") from e
        
        return decrypted, meta
