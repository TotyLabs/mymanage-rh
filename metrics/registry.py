import os
import re
import socket
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from metrics.types import HistogramBucket


class MetricsRegistry:
    """Thread-safe in-process registry for RED, business and operational metrics."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.started_at = time.time()
        self._requests_total = 0
        self._in_flight = 0
        self._requests_by_endpoint = Counter()
        self._requests_by_method = Counter()
        self._requests_by_status = Counter()
        self._requests_by_org = Counter()
        self._payload_in_total = 0
        self._payload_out_total = 0
        self._latency_hist = HistogramBucket("api_latency")
        self._signature_hist = HistogramBucket("signature_latency")
        self._signature_success = 0
        self._signature_failed = 0
        self._signature_active = 0
        self._signature_generated = 0
        self._signature_signed = 0
        self._imports_total = 0
        self._imports_rows_processed = 0
        self._imports_rows_success = 0
        self._imports_rows_error = 0
        self._imports_active = 0
        self._email_sent = 0
        self._email_failed = 0
        self._logins_success = 0
        self._logins_failed = 0
        self._rate_limits = 0
        self._tokens_invalid = 0
        self.instance_id = os.getenv("INSTANCE_ID", f"{socket.gethostname()}-default")

    def reset(self) -> None:
        with self._lock:
            self.started_at = time.time()
            self._requests_total = 0
            self._in_flight = 0
            self._requests_by_endpoint = Counter()
            self._requests_by_method = Counter()
            self._requests_by_status = Counter()
            self._requests_by_org = Counter()
            self._payload_in_total = 0
            self._payload_out_total = 0
            self._latency_hist = HistogramBucket("api_latency")
            self._signature_hist = HistogramBucket("signature_latency")
            self._signature_success = 0
            self._signature_failed = 0
            self._signature_active = 0
            self._signature_generated = 0
            self._signature_signed = 0
            self._imports_total = 0
            self._imports_rows_processed = 0
            self._imports_rows_success = 0
            self._imports_rows_error = 0
            self._imports_active = 0
            self._email_sent = 0
            self._email_failed = 0
            self._logins_success = 0
            self._logins_failed = 0
            self._rate_limits = 0
            self._tokens_invalid = 0

    @staticmethod
    def normalize_path(path: Optional[str]) -> str:
        if not path:
            return ""
        normalized = path.strip()
        if normalized.startswith("/api/"):
            normalized = re.sub(r"/employees/([0-9A-Za-z_-]+)", "/employees/{employee_id}", normalized)
            normalized = re.sub(r"/signature-requests/([0-9A-Za-z_-]+)", "/signature-requests/{token}", normalized)
            normalized = re.sub(r"/receipts/([0-9A-Za-z_-]+)", "/receipts/{receipt_id}", normalized)
        return normalized or "/"

    def inc_in_flight(self) -> None:
        with self._lock:
            self._in_flight += 1

    def dec_in_flight(self) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    def record_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_sec: float,
        payload_in: int = 0,
        payload_out: int = 0,
        org_id: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._requests_total += 1
            self._requests_by_method[method] += 1
            self._requests_by_status[str(status_code)] += 1
            normalized_path = self.normalize_path(path)
            self._requests_by_endpoint[normalized_path] += 1
            if org_id:
                self._requests_by_org[str(org_id)] += 1
            self._payload_in_total += max(0, int(payload_in))
            self._payload_out_total += max(0, int(payload_out))
            self._latency_hist.observe(max(0.0, float(duration_sec)))

    def record_signature(self, duration_sec: float, success: bool = True, generated: bool = False, signed: bool = False) -> None:
        with self._lock:
            self._signature_hist.observe(max(0.0, float(duration_sec)))
            if success:
                self._signature_success += 1
            else:
                self._signature_failed += 1
            if generated:
                self._signature_generated += 1
            if signed:
                self._signature_signed += 1

    def record_import(self, rows_processed: int = 0, rows_success: int = 0, rows_error: int = 0, active: Optional[int] = None) -> None:
        with self._lock:
            self._imports_total += 1
            self._imports_rows_processed += max(0, int(rows_processed))
            self._imports_rows_success += max(0, int(rows_success))
            self._imports_rows_error += max(0, int(rows_error))
            if active is not None:
                self._imports_active = max(0, int(active))

    def record_email(self, sent: bool = True) -> None:
        with self._lock:
            if sent:
                self._email_sent += 1
            else:
                self._email_failed += 1

    def record_auth(self, success: bool = True, rate_limit: bool = False, token_invalid: bool = False) -> None:
        with self._lock:
            if success:
                self._logins_success += 1
            else:
                self._logins_failed += 1
            if rate_limit:
                self._rate_limits += 1
            if token_invalid:
                self._tokens_invalid += 1

    def export_worker_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            latency_hist = self._latency_hist.to_dict()
            signature_hist = self._signature_hist.to_dict()
            uptime_seconds = max(0.0, time.time() - self.started_at)
            return {
                "instance_id": self.instance_id,
                "uptime_seconds": round(uptime_seconds, 2),
                "api": {
                    "requests_total": self._requests_total,
                    "in_flight": self._in_flight,
                    "requests_by_endpoint": dict(self._requests_by_endpoint),
                    "requests_by_method": dict(self._requests_by_method),
                    "requests_by_status": dict(self._requests_by_status),
                    "requests_by_org": dict(self._requests_by_org),
                    "payload_bytes_in": self._payload_in_total,
                    "payload_bytes_out": self._payload_out_total,
                    "latency_hist": latency_hist,
                    "p50_ms": self._latency_hist_to_percentile(0.50),
                    "p95_ms": self._latency_hist_to_percentile(0.95),
                    "p99_ms": self._latency_hist_to_percentile(0.99),
                },
                "signature": {
                    "pdf_generated": self._signature_generated,
                    "pdf_signed": self._signature_signed,
                    "success": self._signature_success,
                    "failed": self._signature_failed,
                    "active_processing": self._signature_active,
                    "latency_hist": signature_hist,
                    "p50_ms": self._signature_hist_to_percentile(0.50),
                    "p95_ms": self._signature_hist_to_percentile(0.95),
                    "p99_ms": self._signature_hist_to_percentile(0.99),
                },
                "import": {
                    "total": self._imports_total,
                    "rows_processed": self._imports_rows_processed,
                    "rows_success": self._imports_rows_success,
                    "rows_error": self._imports_rows_error,
                    "active_jobs": self._imports_active,
                },
                "email_otp": {
                    "email_sent": self._email_sent,
                    "email_failed": self._email_failed,
                },
                "security": {
                    "logins_success": self._logins_success,
                    "logins_failed": self._logins_failed,
                    "rate_limit_triggered": self._rate_limits,
                    "tokens_invalid": self._tokens_invalid,
                },
            }

    def _latency_hist_to_percentile(self, quantile: float) -> float:
        return self._hist_percentile(self._latency_hist, quantile)

    def _signature_hist_to_percentile(self, quantile: float) -> float:
        return self._hist_percentile(self._signature_hist, quantile)

    def _hist_percentile(self, hist: HistogramBucket, quantile: float) -> float:
        if hist.count <= 0:
            return 0.0
        target = quantile * hist.count
        acc = 0
        for bucket in sorted(hist.counts.keys()):
            acc += hist.counts[bucket]
            if acc >= target:
                return round(float(bucket) * 1000.0, 2) if bucket != float("inf") else round(120000.0, 2)
        return round(float(hist.buckets[-1]) * 1000.0, 2) if hist.buckets else 0.0


metrics_registry = MetricsRegistry()
