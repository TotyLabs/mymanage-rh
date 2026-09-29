"""Stateless signed resource download token service.

This module intentionally stays independent from persistence and storage. It implements
an HMAC-SHA256 signed URL token suitable for protecting sensitive downloads in the
existing FastAPI backend without introducing a new SQL resource table.

Contract:
    payload = canonical JSON with claims fields
    token   = base64url(payload) + '.' + base64url(HMAC-SHA256(payload, secret))

Important:
    This service validates claims but does not itself authorize the file object. It
    is an authorization carrier that should be consumed by a download policy service
    that performs the final file scope/tenant/owner checks against the app's
    existing database records and safe path helpers.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Iterable, Mapping, Optional


class SignedResourceTokenService:
    """Create and verify a signed, stateless token for download access.

    Payload is a canonical JSON object with fields like:
        iss, sub, org, res, scope, purpose, iat, exp, nonce

    It intentionally does not require Redis or extra SQL tables, and therefore is
    safe across multi-instance deployments when used in stateless mode.
    """

    def __init__(
        self,
        secret_key: str,
        issuer: str = "mymanagerh",
        ttl_seconds: int = 60,
    ) -> None:
        if not secret_key:
            raise ValueError("secret_key is required to sign resource download tokens")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        self.secret_key = secret_key
        self.issuer = issuer
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _b64url_decode(part: str) -> bytes:
        # Repair urlsafe padding when needed.
        padded = part + ("=" * ((4 - len(part) % 4) % 4))
        return base64.urlsafe_b64decode(padded.encode("ascii"))

    def make_claims(
        self,
        *,
        resource_id: str,
        user_id: str,
        org_id: str,
        scope: str,
        purpose: str = "download",
        resource_type: str = "file",
        nonce: Optional[str] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create the canonical payload for a resource-level signed token.

        The resource_id is intentionally opaque in the URL. The final resolver
        should identify the actual business table entry without exposing its row id.
        """
        now = int(time.time())
        ttl = ttl_seconds if ttl_seconds is not None else self.ttl_seconds
        nonce_value = nonce or secrets.token_hex(16)

        claims = {
            "iss": self.issuer,
            "sub": user_id,
            "org": org_id,
            "res": resource_id,
            "scope": scope,
            "purpose": purpose,
            "resource_type": resource_type,
            "iat": now,
            "exp": now + ttl,
            "nonce": nonce_value,
            "v": 1,
        }
        return claims

    def encode(self, claims: Mapping[str, Any]) -> str:
        """Return a signed token string from a mapping of claims.

        The payload is canonicalized to ensure a consistent byte string across
        implementations.
        """
        payload_bytes = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload_b64 = self._b64url(payload_bytes)
        digest = hmac.new(self.secret_key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        sig_b64 = self._b64url(digest)
        return f"{payload_b64}.{sig_b64}"

    def verify(self, token: str) -> Dict[str, Any]:
        """Verify the token and return the payload claims or raise ValueError.

        This service checks the signature, issuer, version, iat, exp, and basic
        structure. It intentionally avoids DB-backed or in-memory JTI replay tables
        because those are not cross-instance safe in stateless multi-instance deploys.
        """
        if not token or "." not in token:
            raise ValueError("invalid_signed_resource_token")

        try:
            payload_b64, sig_b64 = token.split(".", 1)
            raw_payload = self._b64url_decode(payload_b64)
            payload = json.loads(raw_payload.decode("utf-8"))
        except Exception as exc:
            raise ValueError("invalid_signed_resource_token") from exc

        # Verify the HMAC signature directly from the payload segment.
        expected_sig = hmac.new(self.secret_key.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(self._b64url(expected_sig), sig_b64):
            raise ValueError("invalid_signed_resource_token_signature")

        if payload.get("v") != 1:
            raise ValueError("unsupported_token_version")

        if payload.get("iss") != self.issuer:
            raise ValueError("invalid_token_issuer")

        if not isinstance(payload.get("iat"), int):
            raise ValueError("invalid_token_iat")

        if not isinstance(payload.get("exp"), int):
            raise ValueError("invalid_token_exp")

        if int(payload["exp"]) < int(time.time()):
            raise ValueError("expired_signed_resource_token")

        for key in ("sub", "org", "res", "scope"):
            if not payload.get(key):
                raise ValueError("missing_signed_resource_claim")

        return payload

    def validate_scope(self, claims: Mapping[str, Any], allowed: Iterable[str]) -> None:
        """Ensure the token scope is in the allow-list of the endpoint policy."""
        if claims.get("scope") not in set(allowed):
            raise PermissionError("scope_not_allowed")

    def build_download_url(self, base_url: str, claims: Mapping[str, Any]) -> str:
        """Return an opaque, query-token URL for the browser/download router."""
        token = self.encode(claims)
        if "?" in base_url:
            return f"{base_url}&token={token}"
        return f"{base_url}?token={token}"
