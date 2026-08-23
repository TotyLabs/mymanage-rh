import os
import sys
import time
import socket
import json
from datetime import datetime, timezone
from sqlalchemy import text
from payroll_core import engine, logger
from metrics.registry import metrics_registry

class MetricsStore:
    """
    Manages snapshot persistence and multi-worker aggregation.
    Workers write their snapshot every 5s via UPSERT into PostgreSQL.
    Old snapshots (>30s) are treated as stale and excluded.
    """
    INSTANCE_ID = os.getenv("INSTANCE_ID", f"{socket.gethostname()}-default")
    HOSTNAME = socket.gethostname()

    @classmethod
    def get_worker_id(cls) -> str:
        return f"worker-{os.getpid()}"

    @classmethod
    def flush_snapshot(cls):
        """UPSERT the current worker's snapshot into PostgreSQL (non-blocking/lightweight)."""
        try:
            worker_id = cls.get_worker_id()
            pid = os.getpid()
            now = datetime.now(timezone.utc)
            started_at = datetime.fromtimestamp(metrics_registry.started_at, tz=timezone.utc)
            snapshot_data = metrics_registry.export_worker_snapshot()

            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT INTO system_metrics_snapshots 
                    (instance_id, worker_id, pid, hostname, started_at, updated_at, metrics_json, schema_version)
                    VALUES (:instance_id, :worker_id, :pid, :hostname, :started_at, :updated_at, :metrics_json, 1)
                    ON CONFLICT (instance_id, worker_id) DO UPDATE SET
                        pid = EXCLUDED.pid,
                        updated_at = EXCLUDED.updated_at,
                        metrics_json = EXCLUDED.metrics_json;
                """), {
                    "instance_id": cls.INSTANCE_ID,
                    "worker_id": worker_id,
                    "pid": pid,
                    "hostname": cls.HOSTNAME,
                    "started_at": started_at,
                    "updated_at": now,
                    "metrics_json": json.dumps(snapshot_data)
                })
        except Exception as e:
            logger.error(f"metrics.flush_failed: {e}", exc_info=True)

    @classmethod
    def clean_stale_snapshots(cls):
        """Purge snapshots from workers that haven't updated in > 2 minutes."""
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    DELETE FROM system_metrics_snapshots 
                    WHERE updated_at < NOW() - INTERVAL '2 minutes'
                """))
        except Exception as e:
            logger.error(f"metrics.clean_stale_failed: {e}", exc_info=True)

metrics_store = MetricsStore()
