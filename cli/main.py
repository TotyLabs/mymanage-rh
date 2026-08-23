import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from metrics.exporter import MetricsExporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="MyManage", description="Operability dashboard for MyManageRH")
    subparsers = parser.add_subparsers(dest="command")

    benchmarks = subparsers.add_parser("benchmarks", help="Show consolidated operational metrics")
    benchmarks.add_argument("--watch", action="store_true", help="Refresh the dashboard continuously")
    benchmarks.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds")
    benchmarks.add_argument("--json", action="store_true", help="Emit JSON instead of a text dashboard")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0
    if args.command == "benchmarks":
        if args.json:
            print(json.dumps(MetricsExporter.get_full_consolidated_report(), ensure_ascii=False, indent=2))
            return 0
        while True:
            report = MetricsExporter.get_full_consolidated_report()
            agg = report.get("aggregated", {})
            api = agg.get("api", {})
            print("MyManageRH benchmarks")
            print("-" * 40)
            print(f"active_workers={agg.get('active_workers', 0)}")
            print(f"requests_total={api.get('requests_total', 0)}")
            print(f"in_flight={api.get('in_flight', 0)}")
            print(f"p50/p95/p99_ms={api.get('p50_ms', 0)}/{api.get('p95_ms', 0)}/{api.get('p99_ms', 0)}")
            print(f"cpu_percent={report.get('system', {}).get('cpu_percent', 0)}")
            print(f"memory_rss_mb={report.get('system', {}).get('memory', {}).get('process_rss_mb', 0)}")
            if not args.watch:
                break
            import time
            time.sleep(args.interval)
        return 0
    return 0


if __name__ == "__main__":
    main()
