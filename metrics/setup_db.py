import os
import sys
from pathlib import Path

# Ensure root dir is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from sqlalchemy import text
from payroll_core import engine, logger

def ensure_metrics_table():
    """Ensure system_metrics_snapshots table exists in PostgreSQL."""
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS system_metrics_snapshots (
                    instance_id VARCHAR(128) NOT NULL,
                    worker_id VARCHAR(64) NOT NULL,
                    pid INT NOT NULL,
                    hostname VARCHAR(256) NOT NULL,
                    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    metrics_json JSONB NOT NULL,
                    schema_version INT NOT NULL DEFAULT 1,
                    PRIMARY KEY (instance_id, worker_id)
                );
                CREATE INDEX IF NOT EXISTS idx_metrics_snapshots_updated_at ON system_metrics_snapshots (updated_at);
            """))
        logger.info("metrics.table_ensured")
    except Exception as e:
        logger.error(f"metrics.table_ensure_failed: {e}")

if __name__ == "__main__":
    ensure_metrics_table()
