"""
Import Job Queue Worker.

Processes ImportJob records that were enqueued via the API and executes them
asynchronously in a single worker loop. This module is intentionally lightweight
and uses Postgres row locking to avoid duplicate processing across multiple web
workers.
"""

import asyncio
import logging
from datetime import datetime
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from models import ImportJob, ImportJobStatus
from services.legajo.import_service import ImportService

logger = logging.getLogger("dircom.payroll.import_jobs")

JOB_POLL_INTERVAL_SECONDS = 10.0
JOB_BUSY_WAIT_SECONDS = 0.5
STUCK_JOB_RECOVERY_MINUTES = 30


def _recover_stuck_jobs(db: Session) -> None:
    """Return unfinished locked jobs to the queue if they appear stale."""
    try:
        db.execute(text("""
            UPDATE import_jobs
            SET status = 'queued', updated_at = NOW()
            WHERE status IN ('processing', 'importing')
              AND updated_at < NOW() - INTERVAL '30 minutes'
        """))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("import_job.recovery_failed")


def _fetch_next_job(db: Session):
    return db.execute(text("""
        SELECT id
        FROM import_jobs
        WHERE status = 'queued'
        ORDER BY created_at
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    """
    )).mappings().fetchone()


def _mark_job_processing(db: Session, job_id: str) -> None:
    db.execute(text("""
        UPDATE import_jobs
        SET status = 'processing', updated_at = NOW(),
            metadata_json = jsonb_set(
                COALESCE(metadata_json, '{}'::jsonb),
                '{queue_attempts}',
                to_jsonb(COALESCE((metadata_json->>'queue_attempts')::int, 0) + 1)
            )
        WHERE id = :id
    """), {"id": job_id})
    db.commit()


async def _process_queued_job(db_session_factory: Callable[[], Session]) -> bool:
    db = db_session_factory()
    try:
        _recover_stuck_jobs(db)
        row = _fetch_next_job(db)
        if not row:
            return False

        job_id = row["id"]
        _mark_job_processing(db, job_id)
    except Exception:
        logger.exception("import_job.dequeue_failed")
        return False
    finally:
        db.close()

    process_db = db_session_factory()
    try:
        service = ImportService(process_db)
        metrics = service.execute_job(job_id=job_id, user_id=None)
        logger.info(
            "import_job.executed",
            extra={"job_id": job_id, "metrics": metrics},
        )
        return True
    except Exception as exc:
        process_db.rollback()
        logger.exception("import_job.processing_failed", extra={"job_id": job_id})

        failure_db = db_session_factory()
        try:
            job = failure_db.query(ImportJob).filter(ImportJob.id == job_id).first()
            if job:
                job.status = ImportJobStatus.failed
                job.finished_at = datetime.utcnow()
                metadata = job.metadata_json or {}
                metadata["queue_error"] = str(exc)
                job.metadata_json = metadata
                failure_db.commit()
        except Exception:
            failure_db.rollback()
            logger.exception("import_job.mark_failed_failed", extra={"job_id": job_id})
        finally:
            failure_db.close()
        return False
    finally:
        process_db.close()


async def start_import_job_drain_loop(db_session_factory: Callable[[], Session]):
    logger.info("import_job.drain_loop_started")
    while True:
        processed = await _process_queued_job(db_session_factory)
        if not processed:
            await asyncio.sleep(JOB_POLL_INTERVAL_SECONDS)
        else:
            await asyncio.sleep(JOB_BUSY_WAIT_SECONDS)
