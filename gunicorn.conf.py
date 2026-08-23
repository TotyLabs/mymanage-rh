"""
gunicorn.conf.py — Production Gunicorn Configuration for YouCompare Payroll

Architecture:
    Nginx (TLS, gzip, rate limit) → Gunicorn (4 UvicornWorkers) → FastAPI app

Workers:
    4 Uvicorn workers (async ASGI). Each worker runs its own asyncio event loop
    and its own DB connection pool + PDF thread pool.

Memory Safety:
    max_requests + max_requests_jitter recycles workers periodically to prevent
    slow memory leaks from PDF/image processing (PyMuPDF, Pillow, pyhanko).
"""

import os
import multiprocessing

# =============================================================================
# SERVER SOCKET
# =============================================================================
# Bind to localhost only — Nginx handles TLS and public-facing traffic
bind = "127.0.0.1:8000"
backlog = 2048

# =============================================================================
# WORKERS
# =============================================================================
# UvicornWorker: each is a full async ASGI process with its own event loop.
# 4 workers for 18-core EPYC is conservative — leaves CPU headroom for
# PDF ThreadPool threads, PostgreSQL, and OS.
workers = int(os.getenv("GUNICORN_WORKERS", "4"))
worker_class = "uvicorn.workers.UvicornWorker"

# Do NOT preload. Reasons:
# 1. PyMuPDF (fitz) and pyhanko use C extensions that are not fork-safe
# 2. Each worker needs its own SQLAlchemy engine (separate connection pool)
# 3. ThreadPoolExecutor is not shared across forked processes safely
preload_app = False

# =============================================================================
# TIMEOUTS
# =============================================================================
# Graceful timeout: how long a worker has to finish current requests before
# being forcefully killed. 120s allows long PDF signature operations to complete.
graceful_timeout = 120

# Hard timeout: if a worker is stuck (not responding at all), kill it after this.
# This should be longer than the longest possible request (PDF batch signing).
timeout = 180

# Keep-alive: seconds to wait for requests on a keep-alive connection.
# Matches nginx upstream keepalive_timeout.
keepalive = 5

# =============================================================================
# MEMORY LEAK PREVENTION
# =============================================================================
# After serving N requests, the worker is gracefully recycled.
# Prevents slow memory leaks from PDF/image processing accumulating over days.
max_requests = 2000
max_requests_jitter = 200  # Randomize to avoid all workers recycling at once

# =============================================================================
# LOGGING
# =============================================================================
# Access log: one line per request. Useful for latency tracking.
# When running under systemd prefer stdout/stderr to avoid file locking issues
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Custom access log format: timestamp, status, method, path, response time, size
access_log_format = '%(t)s "%(r)s" %(s)s %(b)s "%(f)s" %(L)ss'

# =============================================================================
# PROCESS NAMING
# =============================================================================
proc_name = "youcompare-payroll"

# =============================================================================
# SECURITY
# =============================================================================
# Limit request line and header sizes to prevent abuse
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# =============================================================================
# HOOKS
# =============================================================================

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Gunicorn master starting with %d workers", server.app.cfg.workers)


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)
