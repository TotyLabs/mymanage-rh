"""
Integration-style tests for the digital signature HTTP endpoints.

Focus on:
- Structured error responses
- Token validation behaviour
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from main import app
from payroll_core import utc_now, hash_token, engine


client = TestClient(app)


@pytest.fixture
def db_session():
    """Simple DB session bound to the main engine."""
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_invalid_token_returns_structured_error():
    """
    /sign/{token}/info debe devolver error estructurado para token invÃ¡lido.
    """
    invalid_token = "not-a-valid-token"
    res = client.get(f"/sign/{invalid_token}/info")
    assert res.status_code == 400
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "INVALID_TOKEN"


def test_expired_token_returns_structured_error(db_session):
    """
    /sign/{token}/info debe devolver TOKEN_EXPIRED cuando el token estÃ¡ vencido.
    """
    now = utc_now()

    # Seed minimal org/employee/receipt/signature_request
    org_row = db_session.execute(
        text(
            """
            INSERT INTO organizations (id, name, slug)
            VALUES (uuid_generate_v4(), 'Test Org Sig', 'test-org-sig')
            RETURNING id
            """
        )
    ).fetchone()
    org_id = str(org_row.id)

    emp_row = db_session.execute(
        text(
            """
            INSERT INTO employees (id, organization_id, full_name, cuil, email)
            VALUES (uuid_generate_v4(), :org_id, 'Empleado Prueba', '20123456789', 'empleado@test.local')
            RETURNING id
            """
        ),
        {"org_id": org_id},
    ).fetchone()
    emp_id = str(emp_row.id)

    batch_row = db_session.execute(
        text(
            """
            INSERT INTO payroll_batches (id, organization_id, period_label, uploaded_at, total_receipts, processed_receipts)
            VALUES (uuid_generate_v4(), :org_id, '2026-01', :now, 1, 1)
            RETURNING id
            """
        ),
        {"org_id": org_id, "now": now},
    ).fetchone()
    batch_id = str(batch_row.id)

    # Dummy PDF path/hash; sign_info no valida el archivo
    receipt_row = db_session.execute(
        text(
            """
            INSERT INTO payroll_receipts (
                id, batch_id, organization_id, employee_id, page_number,
                receipt_pdf_path, receipt_pdf_sha256, extracted_fields, status
            )
            VALUES (
                uuid_generate_v4(), :batch_id, :org_id, :emp_id, 1,
                '/tmp/dummy-receipt.pdf', :sha, '{}'::jsonb, 'pending_signature'
            )
            RETURNING id
            """
        ),
        {"batch_id": batch_id, "org_id": org_id, "emp_id": emp_id, "sha": "0" * 64},
    ).fetchone()
    receipt_id = str(receipt_row.id)

    # Build expired token
    plain_token = "a" * 64
    t_hash = hash_token(plain_token)
    expired_at = now - timedelta(hours=1)

    db_session.execute(
        text(
            """
            INSERT INTO signature_requests (
                id, receipt_id, employee_id, organization_id,
                token_hash, token_expires_at, status
            )
            VALUES (
                uuid_generate_v4(), :receipt_id, :emp_id, :org_id,
                :token_hash, :expires_at, 'pending'
            )
            """
        ),
        {
            "receipt_id": receipt_id,
            "emp_id": emp_id,
            "org_id": org_id,
            "token_hash": t_hash,
            "expires_at": expired_at,
        },
    )
    db_session.commit()

    # Call endpoint with expired token
    res = client.get(f"/sign/{plain_token}/info")
    assert res.status_code == 410
    body = res.json()
    assert "error" in body
    assert body["error"]["code"] == "TOKEN_EXPIRED"

