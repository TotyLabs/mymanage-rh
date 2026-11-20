from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from services.receipt_service import (
    _find_active_batch_page_duplicate,
    _find_active_hash_duplicate,
)


def test_soft_deleted_receipt_does_not_block_reimport_but_active_duplicate_does():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE payroll_receipts (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                organization_id TEXT NOT NULL,
                receipt_pdf_sha256 TEXT NOT NULL,
                is_deleted BOOLEAN NOT NULL
            )
        """))
        connection.execute(text("""
            INSERT INTO payroll_receipts
                (id, batch_id, page_number, organization_id, receipt_pdf_sha256, is_deleted)
            VALUES
                ('deleted', 'new-batch', 1, 'org', 'page-hash', TRUE)
        """))

    with Session(engine) as db:
        assert _find_active_batch_page_duplicate(db, "new-batch", 1) is None
        assert _find_active_hash_duplicate(db, "org", "page-hash") is None

        db.execute(text("""
            INSERT INTO payroll_receipts
                (id, batch_id, page_number, organization_id, receipt_pdf_sha256, is_deleted)
            VALUES
                ('active', 'other-batch', 1, 'org', 'page-hash', FALSE)
        """))
        db.commit()

        assert _find_active_hash_duplicate(db, "org", "page-hash").id == "active"
