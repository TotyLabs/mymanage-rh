import os
import shutil
import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Mock environment configurations
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-dircom-payroll-2026-very-secure")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import config
from main import app
from file_processing.security import encrypt_file, decrypt_file, get_fallback_key
from file_processing.dispatcher import process_file

@pytest.fixture
def temp_plaintext_file(tmp_path):
    path = tmp_path / "test_file.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtestcontent")
    return str(path)

def test_fallback_key_derivation():
    key1 = get_fallback_key()
    assert len(key1) == 32
    # Changing key changes result
    old_key = config.SECRET_KEY
    try:
        config.SECRET_KEY = "another-different-secret-key"
        key2 = get_fallback_key()
        assert key1 != key2
    finally:
        config.SECRET_KEY = old_key

def test_transparent_encryption_disabled(temp_plaintext_file):
    # Ensure app encryption disabled
    old_val = config.APP_ENCRYPTION_ENABLED
    try:
        config.APP_ENCRYPTION_ENABLED = False
        
        orig_bytes = Path(temp_plaintext_file).read_bytes()
        res_path = encrypt_file(temp_plaintext_file)
        assert res_path == temp_plaintext_file
        
        # Data should remain plaintext
        assert Path(temp_plaintext_file).read_bytes() == orig_bytes
        
        dec_bytes = decrypt_file(temp_plaintext_file)
        assert dec_bytes == orig_bytes
    finally:
        config.APP_ENCRYPTION_ENABLED = old_val

def test_transparent_encryption_enabled(temp_plaintext_file):
    old_val = config.APP_ENCRYPTION_ENABLED
    try:
        config.APP_ENCRYPTION_ENABLED = True
        
        orig_bytes = Path(temp_plaintext_file).read_bytes()
        res_path = encrypt_file(temp_plaintext_file)
        assert res_path == temp_plaintext_file
        
        # File should be encrypted (starts with YCP_ENC)
        encrypted_bytes = Path(temp_plaintext_file).read_bytes()
        assert encrypted_bytes != orig_bytes
        assert encrypted_bytes.startswith(b"YCP_ENC\x00")
        
        # Decrypting should return original data
        dec_bytes = decrypt_file(temp_plaintext_file)
        assert dec_bytes == orig_bytes
        
        # Double encrypt should be a no-op
        res_path_2 = encrypt_file(temp_plaintext_file)
        assert Path(temp_plaintext_file).read_bytes() == encrypted_bytes
    finally:
        config.APP_ENCRYPTION_ENABLED = old_val

def test_csrf_middleware_exempt_and_allow():
    client = TestClient(app)
    
    # State-changing method without X-Requested-With should fail
    response = client.post("/api/auth/forgot-password", json={"email": "test@example.com"})
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_protection_triggered"

    # With X-Requested-With header should pass through
    headers = {"X-Requested-With": "XMLHttpRequest"}
    response = client.post("/api/auth/forgot-password", json={"email": "test@example.com"}, headers=headers)
    # OTP or User Not Found returned as 200 (no-enumeration)
    assert response.status_code == 200

def test_csrf_origin_header_validation():
    client = TestClient(app)
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://malicious-attacker.com"
    }
    
    # Under DEV environment (PRODUCTION = False), localhost and ngrok are allowed, but malicious is blocked
    response = client.post("/api/auth/forgot-password", json={"email": "test@example.com"}, headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "csrf_protection_triggered"
    
    # Allowed Dev Domain
    headers_allowed = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://localhost:8000"
    }
    response = client.post("/api/auth/forgot-password", json={"email": "test@example.com"}, headers=headers_allowed)
    assert response.status_code == 200

    # Allowed ngrok-free.dev Domain (Specifically requested)
    headers_ngrok_dev = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://nonexaggerative-smearier-luella.ngrok-free.dev"
    }
    response = client.post("/api/auth/forgot-password", json={"email": "test@example.com"}, headers=headers_ngrok_dev)
    assert response.status_code == 200

def test_cors_ngrok_dev():
    client = TestClient(app)
    # Test preflight OPTIONS request for a CORS check on a dev ngrok origin
    headers = {
        "Origin": "https://nonexaggerative-smearier-luella.ngrok-free.dev",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "Content-Type, X-Requested-With",
    }
    response = client.options("/api/auth/login", headers=headers)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://nonexaggerative-smearier-luella.ngrok-free.dev"

