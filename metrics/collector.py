import time
import os
from typing import Dict, Any
from sqlalchemy import text
from payroll_core import engine, STORAGE_ROOT, logger

try:
    import psutil
    _PSUTIL_ENABLED = True
except ImportError:
    psutil = None  # type: ignore[assignment]
    _PSUTIL_ENABLED = False

class SystemMetricsCollector:
    @staticmethod
    def collect() -> Dict[str, Any]:
        if _PSUTIL_ENABLED:
            cpu_pct = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(str(STORAGE_ROOT))
            load_1, load_5, load_15 = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)

            # Worker processes detail
            current_proc = psutil.Process(os.getpid())
            rss_mb = round(current_proc.memory_info().rss / (1024 * 1024), 2)

            return {
                "cpu_percent": cpu_pct,
                "memory": {
                    "total_gb": round(mem.total / (1024**3), 2),
                    "used_gb": round(mem.used / (1024**3), 2),
                    "free_gb": round(mem.available / (1024**3), 2),
                    "used_percent": mem.percent,
                    "process_rss_mb": rss_mb
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "used_gb": round(disk.used / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "used_percent": disk.percent
                },
                "system": {
                    "load_avg": [round(load_1, 2), round(load_5, 2), round(load_15, 2)],
                    "threads": current_proc.num_threads()
                }
            }
        logger.warning('psutil unavailable: system metrics will be partially degraded')
        load_1, load_5, load_15 = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
        disk = os.statvfs(str(STORAGE_ROOT))
        total_gb = round((disk.f_blocks * disk.f_frsize) / (1024**3), 2)
        used_gb = round(((disk.f_blocks - disk.f_bfree) * disk.f_frsize) / (1024**3), 2)
        free_gb = round((disk.f_bavail * disk.f_frsize) / (1024**3), 2)

        return {
            "cpu_percent": 0.0,
            "memory": {
                "total_gb": 0.0,
                "used_gb": 0.0,
                "free_gb": 0.0,
                "used_percent": 0.0,
                "process_rss_mb": 0.0
            },
            "disk": {
                "total_gb": total_gb,
                "used_gb": used_gb,
                "free_gb": free_gb,
                "used_percent": 0.0
            },
            "system": {
                "load_avg": [round(load_1, 2), round(load_5, 2), round(load_15, 2)],
                "threads": 0
            }
        }

class DatabaseMetricsCollector:
    @staticmethod
    def collect() -> Dict[str, Any]:
        pool = engine.pool
        status = {
            "pool_size": pool.size(),
            "checked_out": pool.checkedout(),
            "checked_in": pool.checkedin(),
            "overflow": pool.overflow()
        }

        pg_stats = {}
        try:
            with engine.connect() as conn:
                res = conn.execute(text("""
                    SELECT 
                        count(*) FILTER (WHERE state = 'active') as active_connections,
                        count(*) FILTER (WHERE state = 'idle') as idle_connections,
                        count(*) as total_connections
                    FROM pg_stat_activity 
                    WHERE datname = current_database();
                """)).fetchone()
                if res:
                    m = res._mapping
                    pg_stats = {
                        "active_connections": m["active_connections"],
                        "idle_connections": m["idle_connections"],
                        "total_connections": m["total_connections"]
                    }
        except Exception:
            pg_stats = {"status": "unavailable"}

        return {
            "pool": status,
            "postgres": pg_stats
        }

class BusinessMetricsCollector:
    _cache = {}
    _cache_ttl = 30.0  # 30 seconds cache to avoid heavy COUNT(*) on large DBs

    @classmethod
    def collect(cls) -> Dict[str, Any]:
        now = time.time()
        if cls._cache and (now - cls._cache.get("_ts", 0) < cls._cache_ttl):
            return cls._cache.get("data", {})

        try:
            with engine.connect() as conn:
                orgs = conn.execute(text("SELECT count(*) FROM organizations WHERE is_active = true")).scalar() or 0
                users = conn.execute(text("SELECT count(*) FROM users WHERE is_active = true")).scalar() or 0
                employees = conn.execute(text("SELECT count(*) FROM employees WHERE is_active = true")).scalar() or 0
                receipts_signed = conn.execute(text("SELECT count(*) FROM receipts WHERE status = 'signed'")).scalar() or 0
                receipts_pending = conn.execute(text("SELECT count(*) FROM receipts WHERE status = 'pending'")).scalar() or 0

            data = {
                "organizations_active": orgs,
                "users_active": users,
                "employees_active": employees,
                "receipts_signed": receipts_signed,
                "receipts_pending": receipts_pending,
            }
            cls._cache = {"data": data, "_ts": now}
            return data
        except Exception:
            return {"status": "unavailable"}
