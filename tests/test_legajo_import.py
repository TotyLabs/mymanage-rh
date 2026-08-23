import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from payroll_core import engine
from services.legajo.import_service import ImportService
from models import ImportJobStatus


@pytest.fixture
def db_session():
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_execute_job_accepts_processing_state(db_session):
    org_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    db_session.execute(
        text(
            """
            INSERT INTO organizations (id, name, slug)
            VALUES (:org_id, 'Test Org Import', 'test-org-import')
            """
        ),
        {"org_id": org_id},
    )

    db_session.execute(
        text(
            """
            INSERT INTO import_jobs (
                id, organization_id, source_type, operation_type,
                original_filename, file_sha256, import_mode, status, metadata_json
            ) VALUES (
                :job_id, :org_id, 'xlsx', 'execute',
                'test.xlsx', :sha, 'merge', 'processing', '{}'::jsonb
            )
            """
        ),
        {"job_id": job_id, "org_id": org_id, "sha": 'deadbeef' * 8},
    )
    db_session.commit()

    service = ImportService(db_session)
    metrics = service.execute_job(job_id=job_id, user_id=None)

    status = db_session.execute(
        text("SELECT status FROM import_jobs WHERE id = :job_id"),
        {"job_id": job_id},
    ).scalar_one()

    assert metrics == {"inserted": 0, "updated": 0, "invalid": 0}
    assert status == ImportJobStatus.imported.value
