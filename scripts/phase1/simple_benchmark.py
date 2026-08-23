#!/usr/bin/env python3
"""Simple micro-benchmark using requests + ThreadPoolExecutor.

Usage: python3 simple_benchmark.py <url> <concurrency> <total_requests>
Example: python3 simple_benchmark.py http://localhost:8000/health 50 200
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


def worker(session, url):
    t0 = time.time()
    try:
        r = session.get(url, timeout=10)
        status = r.status_code
    except Exception as e:
        return None, None
    return time.time() - t0, status


def run(url, concurrency, total):
    times = []
    statuses = {}
    with requests.Session() as s:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            futures = [ex.submit(worker, s, url) for _ in range(total)]
            for f in as_completed(futures):
                t, st = f.result()
                if t is None:
                    times.append(None)
                else:
                    times.append(t)
                    statuses[st] = statuses.get(st, 0) + 1

    successful = [t for t in times if t is not None]
    failed = len([t for t in times if t is None])
    if successful:
        print(f"Requests: {total}  Concurrency: {concurrency}")
        print(f"Successful: {len(successful)}  Failed: {failed}")
        print(f"Min: {min(successful):.3f}s  Max: {max(successful):.3f}s  Avg: {sum(successful)/len(successful):.3f}s")
    else:
        print("All requests failed")
    print("Status codes:", statuses)


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(2)
    url = sys.argv[1]
    concurrency = int(sys.argv[2])
    total = int(sys.argv[3])
    run(url, concurrency, total)
