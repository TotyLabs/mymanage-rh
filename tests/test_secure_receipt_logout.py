import os
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-dircom-payroll-2026-very-secure")
os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"

import api.auth
import api.receipts
from main import app
from payroll_core import get_db


class _FakeResult:
    def fetchone(self):
        return SimpleNamespace(user_id="user-id")


class _FakeDb:
    def __init__(self):
        self.params = []

    def execute(self, statement, params):
        self.params.append(params)
        return _FakeResult()


class _EmptyResult:
    def fetchone(self):
        return None


class _EmptyDb:
    def execute(self, statement, params):
        return _EmptyResult()


def test_receipt_download_requires_authentication(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: object())

    response = TestClient(app).get(
        "/api/receipts/fce97c94-30a8-462a-9353-51fe9d462d58/download"
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"


@pytest.mark.parametrize(
    "headers",
    [
        {"Accept": "*/*", "Sec-Fetch-Mode": "navigate"},
        {"Accept": "application/pdf"},
    ],
)
def test_receipt_download_browser_navigation_gets_friendly_error(monkeypatch, headers):
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: object())

    response = TestClient(app).get(
        "/api/receipts/fce97c94-30a8-462a-9353-51fe9d462d58/download",
        headers=headers,
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["cache-control"] == "no-store"
    assert "Iniciá sesión para ver este recibo" in response.text
    assert "/ui/#/select-role" in response.text


def test_logout_revokes_cookie_and_header_tokens(monkeypatch):
    fake_db = _FakeDb()
    revoked = []
    monkeypatch.setitem(app.dependency_overrides, get_db, lambda: fake_db)
    monkeypatch.setattr(api.auth, "safe_transaction", lambda db: nullcontext())
    monkeypatch.setattr(api.auth, "hash_token", lambda token: f"hash:{token}")
    monkeypatch.setattr(
        api.auth,
        "delete_session_by_hash",
        lambda token_hash, user_id: revoked.append((token_hash, user_id)),
    )

    response = TestClient(app).post(
        "/api/auth/logout",
        cookies={"session": "cookie-token"},
        headers={
            "Authorization": "Bearer header-token",
            "X-Requested-With": "XMLHttpRequest",
        },
    )

    assert response.status_code == 200
    assert {entry["h"] for entry in fake_db.params} == {
        "hash:cookie-token",
        "hash:header-token",
    }
    assert set(revoked) == {
        ("hash:cookie-token", "user-id"),
        ("hash:header-token", "user-id"),
    }
    assert "session=\"\"" in response.headers["set-cookie"]


@pytest.mark.parametrize(
    ("user", "document", "expected_status"),
    [
        (
            {"id": "company-admin", "role": "admin", "organization_id": "org-a"},
            {"source": "enterprise", "organization_id": "org-a", "employee_id": "employee-a"},
            200,
        ),
        (
            {"id": "foreign-admin", "role": "admin", "organization_id": "org-b"},
            {"source": "enterprise", "organization_id": "org-a", "employee_id": "employee-a"},
            403,
        ),
        (
            {"id": "employee-a", "role": "employee", "organization_id": "org-a", "employee_id": "employee-a"},
            {"source": "enterprise", "organization_id": "org-a", "employee_id": "employee-a"},
            200,
        ),
        (
            {"id": "employee-b", "role": "employee", "organization_id": "org-a", "employee_id": "employee-b"},
            {"source": "enterprise", "organization_id": "org-a", "employee_id": "employee-a"},
            403,
        ),
        (
            {"id": "employee-a", "role": "employee", "organization_id": "org-a", "employee_id": "employee-a"},
            {"source": "payroll", "organization_id": "org-a", "employee_id": "employee-a"},
            200,
        ),
        (
            {"id": "employee-b", "role": "employee", "organization_id": "org-a", "employee_id": "employee-b"},
            {"source": "payroll", "organization_id": "org-a", "employee_id": "employee-a"},
            403,
        ),
    ],
)
def test_receipt_download_enforces_company_and_employee_ownership(
    monkeypatch, tmp_path, user, document, expected_status
):
    document = {
        **document,
        "id": "fce97c94-30a8-462a-9353-51fe9d462d58",
        "path": "receipt.pdf",
        "hash": None,
        "metadata": {},
    }
    safe_file = tmp_path / "receipt.pdf"
    safe_file.write_bytes(b"test pdf")

    monkeypatch.setitem(app.dependency_overrides, get_db, _EmptyDb)
    monkeypatch.setitem(app.dependency_overrides, api.receipts.require_auth, lambda: user)
    monkeypatch.setattr(
        api.receipts.DocumentRepository,
        "get_document",
        staticmethod(lambda db, receipt_id: document),
    )
    monkeypatch.setattr(api.receipts, "safe_join_under_storage", lambda path: str(safe_file))
    response = TestClient(app).get(f"/api/receipts/{document['id']}/download")

    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.headers["cache-control"] == "private, no-store"