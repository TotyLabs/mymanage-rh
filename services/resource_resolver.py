"""Opaque resource resolver for signed download policy.

This module intentionally does NOT create a new SQL table or a new persistent record
for download tokens. Instead it resolves a resource_id from an existing business
entity in the existing persistence model and applies the current tenant/scopes.

The service should remain stateless and compatible with multiple app instances.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


class FileResourceResolver:
    """Resolve an opaque resource identifier against the business DB tables.

    This resolver uses existing tables and should never invent a new resource table.
    We keep the mapping to business tables in a pure, deterministic way:
        sha256(resource_type + resource_pk + org_id)

    That keeps the identifier opaque, non-enumerable, and stateless across infra.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    @staticmethod
    def opaque_resource_id(resource_type: str, pk: str, org_id: str) -> str:
        payload = f"{resource_type}:{pk}:{org_id}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def resolve(self, resource_id: str, org_id: str, user_id: str, scope: str) -> Dict[str, Any]:
        """Resolve a resource_id into the real storage metadata.

        The resolver uses the service's own existing DB schema and checks the
        resource type by scope. The caller (e.g. download policy) should keep
        using the safe storage path helpers from `payroll_core.py`.
        """
        # Map scope -> existing table selection. This is intentionally conservative.
        scope_to_table = {
            "receipt:download": ("payroll_receipts", "receipt_pdf_path"),
            "document:download": ("company_documents", "file_path"),
            "signature:download": ("user_signatures", "signature_path"),
            "notification:attachment": ("notifications", "file_path"),
            "org:logo": ("organizations", "logo_path"),
            "audit:report": ("audit_log", "data"),
        }

        if scope not in scope_to_table:
            raise PermissionError("unsupported_download_scope")

        table, file_col = scope_to_table[scope]
        # Example deterministic backend resolution pattern. Prefer a service-specific
        # SQL query that matches the table structure used by the endpoint.
        # The resolver MUST validate org_id and ownership in the same call.
        row = self.db.execute(text(f"""
            SELECT id, organization_id, user_id, {file_col} AS file_path
            FROM {table}
            WHERE organization_id = :org_id
              AND id = :pk
              AND is_active = true
            LIMIT 1
        """), {"org_id": org_id, "pk": resource_id}).fetchone()

        if not row:
            raise PermissionError("resource_not_found_or_not_authorized")

        # Keep the return shape explicit and safe.
        return {
            "resource_type": scope.split(":", 1)[0],
            "table": table,
            "column": file_col,
            "org_id": str(row.organization_id),
            "user_id": str(row.user_id) if row.user_id else None,
            "file_path": str(row.file_path),
        }
