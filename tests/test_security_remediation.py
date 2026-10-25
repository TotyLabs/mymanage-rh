import os

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-for-security-tests")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from services.verification_service import VerificationService


def test_otp_digest_is_stable_and_keyed():
    digest = VerificationService.compute_context_hash(
        None, None, "123456", "password_reset"
    )

    assert digest == VerificationService.compute_context_hash(
        None, None, "123456", "password_reset"
    )
    assert digest != "123456"


def test_otp_digest_binds_operation_and_resource():
    digest = VerificationService.compute_context_hash(
        "receipt-a", "request-a", "123456", "signature"
    )

    assert digest != VerificationService.compute_context_hash(
        "receipt-a", "request-a", "123456", "password_reset"
    )
    assert digest != VerificationService.compute_context_hash(
        "receipt-b", "request-a", "123456", "signature"
    )
    assert digest != VerificationService.compute_context_hash(
        "receipt-a", "request-b", "123456", "signature"
    )


def test_otp_service_rejects_unknown_contexts():
    assert "password_reset" in VerificationService.ALLOWED_CONTEXTS
    assert "company_key_reset" in VerificationService.ALLOWED_CONTEXTS
    assert "arbitrary" not in VerificationService.ALLOWED_CONTEXTS
