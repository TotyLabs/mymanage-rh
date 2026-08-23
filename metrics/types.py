import time
from typing import Dict, Any, List

class HistogramBucket:
    """
    Fixed-bucket histogram for latency and payload distributions.
    Allows exact aggregation across workers and calculation of P50, P95, P99.
    """
    DEFAULT_LE_BUCKETS = [
        0.005, 0.010, 0.025, 0.050, 0.100, 0.250, 0.500,
        1.0, 2.0, 5.0, 10.0, 30.0, 120.0, float("inf")
    ]

    def __init__(self, name: str, buckets: List[float] = None):
        self.name = name
        self.buckets = sorted(buckets or self.DEFAULT_LE_BUCKETS)
        self.counts = {b: 0 for b in self.buckets}
        self.sum = 0.0
        self.count = 0

    def observe(self, value: float):
        val = max(0.0, float(value))
        self.sum += val
        self.count += 1
        for b in self.buckets:
            if val <= b:
                self.counts[b] += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "sum": round(self.sum, 6),
            "buckets": {str(b): c for b, c in self.counts.items()}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'HistogramBucket':
        hist = cls(data["name"])
        hist.count = data.get("count", 0)
        hist.sum = data.get("sum", 0.0)
        raw_b = data.get("buckets", {})
        hist.counts = {}
        for k, v in raw_b.items():
            b_val = float("inf") if k == "inf" else float(k)
            hist.counts[b_val] = int(v)
        hist.buckets = sorted(hist.counts.keys())
        return hist
