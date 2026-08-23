import importlib


def test_registry_records_requests_and_normalizes_paths():
    registry_module = importlib.import_module("metrics.registry")
    registry = registry_module.MetricsRegistry()
    registry.reset()

    for duration in [0.005, 0.015, 0.03, 0.08, 0.2, 0.4, 0.8]:
        registry.record_request(
            method="GET",
            path="/api/employees/123",
            status_code=200,
            duration_sec=duration,
            payload_in=128,
            payload_out=256,
            org_id="org-1",
        )

    snapshot = registry.export_worker_snapshot()
    assert snapshot["api"]["requests_total"] == 7
    assert snapshot["api"]["requests_by_status"]["200"] == 7
    assert snapshot["api"]["in_flight"] == 0
    assert snapshot["api"]["latency_hist"]["count"] == 7
    assert snapshot["api"]["p95_ms"] >= 0

    normalized = registry.normalize_path("/api/employees/123")
    assert normalized == "/api/employees/{employee_id}"
