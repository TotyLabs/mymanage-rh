import time
import asyncio
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from payroll_core import logger
from metrics.registry import metrics_registry
from metrics.store import metrics_store

class MetricsMiddleware(BaseHTTPMiddleware):
    """
    FastAPI HTTP Middleware for RED metrics (Requests, Errors, Duration).
    Does NOT consume or duplicate request bodies for streaming/file safety.
    Uses Content-Length header or ASGI response size wrapping.
    """
    # Background flusher control
    _flusher_task = None
    _snapshot_written = False

    async def dispatch(self, request: Request, call_next):
        # 1. Skip static UI files or metrics endpoint itself to avoid self-reinforcing metrics
        path = request.url.path
        if path.startswith("/ui/") or path == "/metrics" or path == "/favicon.ico":
            return await call_next(request)

        # 2. Extract payload length safely without reading body stream
        content_length = request.headers.get("Content-Length")
        payload_in = int(content_length) if content_length and content_length.isdigit() else 0

        # Extract org_id if set by auth dependency/session
        org_id = getattr(request.state, "organization_id", None) if hasattr(request, "state") else None

        metrics_registry.inc_in_flight()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration = time.perf_counter() - start_time

            # Extract response length safely from header
            res_length = response.headers.get("Content-Length")
            payload_out = int(res_length) if res_length and res_length.isdigit() else 0

            metrics_registry.record_request(
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_sec=duration,
                payload_in=payload_in,
                payload_out=payload_out,
                org_id=org_id
            )
            return response
        except Exception as e:
            duration = time.perf_counter() - start_time
            metrics_registry.record_request(
                method=request.method,
                path=path,
                status_code=500,
                duration_sec=duration,
                payload_in=payload_in,
                payload_out=0,
                org_id=org_id
            )
            raise e
        finally:
            metrics_registry.dec_in_flight()
            if not MetricsMiddleware._snapshot_written:
                try:
                    metrics_store.flush_snapshot()
                    MetricsMiddleware._snapshot_written = True
                except Exception as exc:
                    logger.error(f"metrics.first_request_flush_failed: {exc}", exc_info=True)

async def start_periodic_metrics_flusher():
    """Flushes per-worker snapshot to PostgreSQL every 5 seconds."""
    while True:
        try:
            metrics_store.flush_snapshot()
        except Exception as exc:
            logger.error(f"metrics.flusher_loop_error: {exc}", exc_info=True)
        await asyncio.sleep(5.0)
