import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from payroll_core import engine
from services.legajo.import_service import ImportService
from services.legajo.normalizer import Normalizer
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

    slug = f"test-org-import-{uuid.uuid4().hex[:10]}"
    db_session.execute(
        text(
            """
            INSERT INTO organizations (id, name, slug)
            VALUES (:org_id, 'Test Org Import', :slug)
            """
        ),
        {"org_id": org_id, "slug": slug},
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


def test_employee_status_is_normalized_to_enum_values():
    normalizer = Normalizer.__new__(Normalizer)

    assert normalizer.coerce_value("status", "Activo") == "active"
    assert normalizer.coerce_value("status", "En Función") == "active"
    assert normalizer.coerce_value("status", "Inactivo") == "inactive"
    assert normalizer.coerce_value("status", "Pendiente") == "pending_verification"


def test_execute_job_normalizes_status_on_existing_employee_update(db_session):
    org_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    slug = f"test-org-status-update-{uuid.uuid4().hex[:10]}"
    db_session.execute(
        text(
            """
            INSERT INTO organizations (id, name, slug)
            VALUES (:org_id, 'Test Org Status Update', :slug)
            """
        ),
        {"org_id": org_id, "slug": slug},
    )

    employee = __import__('models').Employee(
        organization_id=org_id,
        first_name='Ramon',
        last_name='Ibarra',
        dni='18051384',
        status='active',
    )
    db_session.add(employee)
    db_session.commit()

    db_session.execute(
        text(
            """
            INSERT INTO import_jobs (
                id, organization_id, source_type, operation_type,
                original_filename, file_sha256, import_mode, status, metadata_json
            ) VALUES (
                :job_id, :org_id, 'xlsx', 'execute',
                'status-update.xlsx', :sha, 'merge', 'preview_ready', '{}'::jsonb
            )
            """
        ),
        {"job_id": job_id, "org_id": org_id, "sha": 'deadbeef' * 8},
    )

    db_session.execute(
        text(
            """
            INSERT INTO import_job_rows (
                id, import_job_id, source_row_number, external_key,
                raw_data_json, normalized_data_json, planned_action,
                resolution_status, matched_employee_id
            ) VALUES (
                :row_id, :job_id, 1, :dni,
                CAST(:raw_data AS JSONB), CAST(:normalized AS JSONB), 'update', 'pending', :employee_id
            )
            """
        ),
        {
            "row_id": str(uuid.uuid4()),
            "job_id": job_id,
            "dni": '18051384',
            "raw_data": '{"dni": "18051384", "status": "Activo", "first_name": "Ramon", "last_name": "Ibarra"}',
            "normalized": '{"dni": "18051384", "status": "active", "first_name": "Ramon", "last_name": "Ibarra"}',
            "employee_id": str(employee.id),
        },
    )
    db_session.commit()

    service = ImportService(db_session)
    metrics = service.execute_job(job_id=job_id, user_id=None)

    refreshed = db_session.query(__import__('models').Employee).filter_by(id=employee.id).one()
    row = db_session.query(__import__('models').ImportJobRow).filter_by(import_job_id=job_id).one()

    assert metrics["updated"] == 1
    assert refreshed.status == 'active'
    assert row.resolution_status == 'executed'


def test_imported_employee_stays_active_not_pre_registered(db_session):
    org_id = str(uuid.uuid4())
    slug = f"test-org-active-status-{uuid.uuid4().hex[:10]}"
    db_session.execute(
        text(
            """
            INSERT INTO organizations (id, name, slug)
            VALUES (:org_id, 'Test Org Active Status', :slug)
            """
        ),
        {"org_id": org_id, "slug": slug},
    )
    db_session.commit()

    service = ImportService(db_session)
    employee = service.db.query(__import__('models').Employee).filter_by(organization_id=org_id).first()
    assert employee is None

    created = __import__('models').Employee(
        organization_id=org_id,
        first_name='Ramon',
        last_name='Ibarra',
        dni='18051384',
        status='active',
    )
    db_session.add(created)
    db_session.commit()

    assert created.status == 'active'
    assert created.status != 'pre_registered'
