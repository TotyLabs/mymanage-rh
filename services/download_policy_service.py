"""Download policy service that applies signed-resource checks before FileResponse.

This is a safe adapter around the existing backend. It is deliberately:
- stateless
- compatible with `payroll_core.safe_join_under_storage`
- compatible with FastAPI `FileResponse`
- compatible with request-scoped auth already implemented in `payroll_core.require_auth`

It should be used centrally by a middleware or by a decorator on file-serving routes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Union

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse

from payroll_core import ALLOWED_STORAGE_DIR, safe_join_under_storage
from services.signed_resource_service import SignedResourceTokenService
from services.resource_resolver import FileResourceResolver


class DownloadPolicyService:
    """Validate a signed resource token and gate a sensitive file response.

    Contract:
        - token passed as query param `token`
        - payload signed by `SignedResourceTokenService`
        - scope checks run against the requested resource and session user
        - storage path must remain inside `ALLOWED_STORAGE_DIR`

    It does NOT serve file data itself; it should be invoked by the actual
    download route and passed the file path returned by the resolver.
    """

    def __init__(self, signed_service: SignedResourceTokenService, resolver: FileResourceResolver):
        self.token_service = signed_service
        self.resolver = resolver

    def enforce_token(self, token: Optional[str]) -> Dict[str, Any]:
        if not token:
            raise HTTPException(status_code=401, detail="missing_signed_download_token")
        try:
            claims = self.token_service.verify(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return claims

    def authorize_claims(self, claims: Mapping[str, Any], org_id: str, user_id: str) -> None:
        if claims.get("org") != org_id:
            raise HTTPException(status_code=403, detail="tenant_mismatch")
        if claims.get("sub") != user_id:
            raise HTTPException(status_code=403, detail="user_mismatch")

    def resolve_and_check_path(self, claims: Mapping[str, Any], scope: str) -> str:
        # Important: enforce scope from claims into the business-specific resolver.
        if claims.get("scope") != scope:
            raise HTTPException(status_code=403, detail="scope_mismatch")

        # Resolver is intentionally a business-service abstraction; in a real backend
        # you would pass the actual entity table and record type into the resolver.
        resource_id = str(claims.get("res") or "")
        org_id = str(claims.get("org") or "")
        user_id = str(claims.get("sub") or "")

        info = self.resolver.resolve(resource_id, org_id, user_id, scope)
        file_path = info.get("file_path")
        if not file_path:
            raise HTTPException(status_code=404, detail="resource_not_found")

        # Normalize and protect against path traversal.
        safe_path = safe_join_under_storage(Path(file_path).name)
        # Keep the policy conservative: use the already allowed storage base if the
        # file_path is a relative path under storage tree; otherwise the resolver
        # should return an absolute path and `safe_join_under_storage` must be applied.
        if not os.path.exists(safe_path):
            raise HTTPException(status_code=404, detail="resource_file_not_found")

        return safe_path

    def build_file_response(self, path: str, filename: str, media_type: str = "application/octet-stream") -> FileResponse:
        # Keep response headers minimal and not expose raw path.
        return FileResponse(path, media_type=media_type, filename=filename)
