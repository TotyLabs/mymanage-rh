import time
from typing import Dict, Any, List
from metrics.types import HistogramBucket

def compute_percentiles_from_buckets(counts: Dict[float, int], total_count: int, quantiles: List[float] = [0.50, 0.95, 0.99]) -> Dict[str, float]:
    """
    Calculate percentiles (P50, P95, P99) accurately from consolidated histogram buckets.
    """
    if total_count <= 0:
        return {f"P{int(q*100)}": 0.0 for q in quantiles}

    sorted_buckets = sorted(counts.keys())
    result = {}
    for q in quantiles:
        target = q * total_count
        accum = 0
        p_val = sorted_buckets[-1] if sorted_buckets else 0.0
        for b in sorted_buckets:
            accum = counts[b]
            if accum >= target:
                p_val = b if b != float("inf") else 30.0
                break
        result[f"P{int(q*100)}"] = round(p_val * 1000, 2)  # return in ms
    return result

def aggregate_worker_snapshots(snapshots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates metrics from N worker snapshots into a single coherent system-wide view.
    Merges counters, sums histograms, and correctly computes global P50/P95/P99.
    """
    if not snapshots:
        return {}

    total_requests = 0
    in_flight = 0
    endpoints_map: Dict[str, int] = {}
    methods_map: Dict[str, int] = {}
    status_map: Dict[str, int] = {}
    orgs_map: Dict[str, int] = {}

    # Histogram accumulation for API
    api_bucket_counts: Dict[float, int] = {}
    api_sum = 0.0
    api_count = 0

    # Digital signature
    sig_pdf_gen = 0
    sig_pdf_signed = 0
    sig_success = 0
    sig_failed = 0
    sig_active = 0
    sig_bucket_counts: Dict[float, int] = {}
    sig_sum = 0.0
    sig_count = 0

    # Excel Import
    import_total = 0
    import_rows_proc = 0
    import_rows_succ = 0
    import_rows_err = 0
    import_active = 0

    # Email & Security
    email_sent = 0
    email_failed = 0
    logins_success = 0
    logins_failed = 0
    rate_limits = 0
    tokens_invalid = 0

    active_workers = len(snapshots)
    worker_details = []

    for s in snapshots:
        m = s.get("metrics_json", {})
        worker_details.append({
            "worker_id": s.get("worker_id"),
            "pid": s.get("pid"),
            "uptime": m.get("uptime_seconds", 0),
            "updated_at": s.get("updated_at")
        })

        # API
        api = m.get("api", {})
        total_requests += api.get("requests_total", 0)
        in_flight += api.get("in_flight", 0)
        for ep, c in api.get("requests_by_endpoint", {}).items():
            endpoints_map[ep] = endpoints_map.get(ep, 0) + c
        for meth, c in api.get("requests_by_method", {}).items():
            methods_map[meth] = methods_map.get(meth, 0) + c
        for st, c in api.get("requests_by_status", {}).items():
            status_map[st] = status_map.get(st, 0) + c
        for org, c in api.get("requests_by_org", {}).items():
            orgs_map[org] = orgs_map.get(org, 0) + c

        # Merge API Histogram
        api_h = api.get("latency_hist", {})
        api_count += api_h.get("count", 0)
        api_sum += api_h.get("sum", 0.0)
        for b_str, cnt in api_h.get("buckets", {}).items():
            b_val = float("inf") if b_str == "inf" else float(b_str)
            api_bucket_counts[b_val] = api_bucket_counts.get(b_val, 0) + cnt

        # Signature
        sig = m.get("signature", {})
        sig_pdf_gen += sig.get("pdf_generated", 0)
        sig_pdf_signed += sig.get("pdf_signed", 0)
        sig_success += sig.get("success", 0)
        sig_failed += sig.get("failed", 0)
        sig_active += sig.get("active_processing", 0)

        sig_h = sig.get("latency_hist", {})
        sig_count += sig_h.get("count", 0)
        sig_sum += sig_h.get("sum", 0.0)
        for b_str, cnt in sig_h.get("buckets", {}).items():
            b_val = float("inf") if b_str == "inf" else float(b_str)
            sig_bucket_counts[b_val] = sig_bucket_counts.get(b_val, 0) + cnt

        # Import
        imp = m.get("import", {})
        import_total += imp.get("total", 0)
        import_rows_proc += imp.get("rows_processed", 0)
        import_rows_succ += imp.get("rows_success", 0)
        import_rows_err += imp.get("rows_error", 0)
        import_active += imp.get("active_jobs", 0)

        # Email & Security
        em = m.get("email_otp", {})
        email_sent += em.get("email_sent", 0)
        email_failed += em.get("email_failed", 0)

        sec = m.get("security", {})
        logins_success += sec.get("logins_success", 0)
        logins_failed += sec.get("logins_failed", 0)
        rate_limits += sec.get("rate_limit_triggered", 0)
        tokens_invalid += sec.get("tokens_invalid", 0)

    # Compute percentiles from merged histogram buckets
    api_percentiles = compute_percentiles_from_buckets(api_bucket_counts, api_count)
    sig_percentiles = compute_percentiles_from_buckets(sig_bucket_counts, sig_count)

    avg_latency_ms = round((api_sum / api_count) * 1000, 2) if api_count > 0 else 0.0
    sig_avg_latency_ms = round((sig_sum / sig_count) * 1000, 2) if sig_count > 0 else 0.0

    return {
        "active_workers": active_workers,
        "workers_detail": worker_details,
        "api": {
            "requests_total": total_requests,
            "in_flight": in_flight,
            "avg_latency_ms": avg_latency_ms,
            "p50_ms": api_percentiles["P50"],
            "p95_ms": api_percentiles["P95"],
            "p99_ms": api_percentiles["P99"],
            "requests_by_endpoint": endpoints_map,
            "requests_by_method": methods_map,
            "requests_by_status": status_map,
            "requests_by_org": orgs_map,
        },
        "signature": {
            "pdf_generated": sig_pdf_gen,
            "pdf_signed": sig_pdf_signed,
            "success": sig_success,
            "failed": sig_failed,
            "active_processing": sig_active,
            "avg_latency_ms": sig_avg_latency_ms,
            "p50_ms": sig_percentiles["P50"],
            "p95_ms": sig_percentiles["P95"],
            "p99_ms": sig_percentiles["P99"],
        },
        "import": {
            "total": import_total,
            "rows_processed": import_rows_proc,
            "rows_success": import_rows_succ,
            "rows_error": import_rows_err,
            "active_jobs": import_active,
        },
        "email": {
            "sent": email_sent,
            "failed": email_failed,
        },
        "security": {
            "logins_success": logins_success,
            "logins_failed": logins_failed,
            "rate_limits_triggered": rate_limits,
            "tokens_invalid": tokens_invalid,
        }
    }
