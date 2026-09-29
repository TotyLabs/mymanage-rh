import pytest

from services.signed_resource_service import SignedResourceTokenService


def test_signed_token_encode_decode_round_trip():
    service = SignedResourceTokenService(secret_key="test-secret-key-for-dircom-payroll-2026-very-secure", issuer="mymanagerh", ttl_seconds=60)
    claims = service.make_claims(
        resource_id="opaque-resource-id",
        user_id="user-123",
        org_id="org-456",
        scope="receipt:download",
        purpose="download",
        resource_type="receipt",
    )
    token = service.encode(claims)
    decoded = service.verify(token)
    assert decoded["scope"] == "receipt:download"
    assert decoded["org"] == "org-456"
    assert decoded["sub"] == "user-123"


def test_signed_token_ttl_must_be_positive():
    with pytest.raises(ValueError):
        SignedResourceTokenService(
            secret_key="test-secret-key-for-dircom-payroll-2026-very-secure",
            issuer="mymanagerh",
            ttl_seconds=0,
        )
