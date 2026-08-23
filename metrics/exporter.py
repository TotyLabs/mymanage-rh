import os
import time
import json
from typing import Dict, Any, List
from sqlalchemy import text
from payroll_core import engine, logger
from metrics.store import metrics_store
from metrics.collector import SystemMetricsCollector, DatabaseMetricsCollector, BusinessMetricsCollector
from metrics.aggregation import aggregate_worker_snapshots
from metrics.registry import metrics_registry

class MetricsExporter:
    @staticmethod
    def fetch_active_worker_snapshots() -> List[Dict[str, Any]]:
        """Fetch snapshots updated in the last 30 seconds from DB."""
        try:
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT instance_id, worker_id, pid, hostname, started_at, updated_at, metrics_json
                    FROM system_metrics_snapshots
                    WHERE updated_at >= NOW() - INTERVAL '30 seconds'
                    ORDER BY worker_id;
                """)).fetchall()
                result = []
                for r in rows:
                    m = r._mapping
                    result.append({
                        "instance_id": m["instance_id"],
                        "worker_id": m["worker_id"],
                        "pid": m["pid"],
                        "hostname": m["hostname"],
                        "started_at": m["started_at"].isoformat() if m["started_at"] else None,
                        "updated_at": m["updated_at"].isoformat() if m["updated_at"] else None,
                        "metrics_json": json.loads(m["metrics_json"]) if isinstance(m["metrics_json"], str) else m["metrics_json"]
                    })
                return result
        except Exception as e:
            logger.error(f"metrics.export_fetch_failed: {e}", exc_info=True)
            return []

    @classmethod
    def get_full_consolidated_report(cls) -> Dict[str, Any]:
        snapshots = cls.fetch_active_worker_snapshots()
        logger.debug(f"metrics.snapshots_loaded count={len(snapshots)}")
        aggregated = aggregate_worker_snapshots(snapshots)
        if not aggregated:
            local_snapshot = metrics_registry.export_worker_snapshot()
            aggregated = {
                "active_workers": 1,
                "workers_detail": [{"worker_id": "local", "pid": os.getpid(), "uptime": round(max(0.0, time.time() - metrics_registry.started_at), 2), "updated_at": None}],
                "api": local_snapshot.get("api", {}),
                "signature": local_snapshot.get("signature", {}),
                "import": local_snapshot.get("import", {}),
                "email": {
                    "sent": local_snapshot.get("email_otp", {}).get("email_sent", 0),
                    "failed": local_snapshot.get("email_otp", {}).get("email_failed", 0),
                },
                "security": local_snapshot.get("security", {}),
            }

        system_metrics = SystemMetricsCollector.collect()
        db_metrics = DatabaseMetricsCollector.collect()
        business_metrics = BusinessMetricsCollector.collect()

        return {
            "aggregated": aggregated,
            "system": system_metrics,
            "database": db_metrics,
            "business": business_metrics
        }

    @classmethod
    def generate_prometheus_text(cls) -> str:
        report = cls.get_full_consolidated_report()
        agg = report.get("aggregated", {})
        api = agg.get("api", {})
        sig = agg.get("signature", {})
        sys = report.get("system", {})
        db = report.get("database", {})

        lines = [
            "# HELP mymanage_api_requests_total Total API requests served across all workers",
            "# TYPE mymanage_api_requests_total counter",
            f"mymanage_api_requests_total {api.get('requests_total', 0)}",
            "# HELP mymanage_api_in_flight Active HTTP requests in flight",
            "# TYPE mymanage_api_in_flight gauge",
            f"mymanage_api_in_flight {api.get('in_flight', 0)}",
            "# HELP mymanage_api_latency_p95_ms P95 API Latency in ms",
            "# TYPE mymanage_api_latency_p95_ms gauge",
            f"mymanage_api_latency_p95_ms {api.get('p95_ms', 0)}",
            "# HELP mymanage_system_cpu_percent System CPU Usage percent",
            "# TYPE mymanage_system_cpu_percent gauge",
            f"mymanage_system_cpu_percent {sys.get('cpu_percent', 0)}",
            "# HELP mymanage_signatures_success_total Total successful digital signatures",
            "# TYPE mymanage_signatures_success_total counter",
            f"mymanage_signatures_success_total {sig.get('success', 0)}",
            "# HELP mymanage_active_workers Active Gunicorn workers reporting metrics",
            "# TYPE mymanage_active_workers gauge",
            f"mymanage_active_workers {agg.get('active_workers', 0)}"
        ]
        return "\n".join(lines) + "\n"
