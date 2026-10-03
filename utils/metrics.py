"""
Utility: lightweight in-process monitoring (counters + latency stats) with
structured JSON event logging.
"""

import json
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

from utils.logger import get_logger

logger = get_logger("metrics")

_lock = threading.Lock()
_counters: dict[str, int] = defaultdict(int)
_latencies: dict[str, list[float]] = defaultdict(list)
_MAX_SAMPLES = 1000


def incr(name: str, value: int = 1) -> None:
    with _lock:
        _counters[name] += value


def observe(name: str, millis: float) -> None:
    with _lock:
        samples = _latencies[name]
        samples.append(millis)
        if len(samples) > _MAX_SAMPLES:
            del samples[0]


@contextmanager
def timed(name: str):
    """Time a block; records latency in ms and yields a dict with 'ms' set on exit."""
    result = {"ms": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["ms"] = (time.perf_counter() - start) * 1000
        observe(name, result["ms"])


def log_event(event: str, **fields) -> None:
    """Emit one structured JSON log line."""
    logger.info("%s", json.dumps({"event": event, **fields}, default=str, ensure_ascii=False))


def snapshot() -> dict:
    """Return counters and latency summaries (count, avg, p50, p95, max)."""
    with _lock:
        stats = {}
        for name, samples in _latencies.items():
            if not samples:
                continue
            s = sorted(samples)
            stats[name] = {
                "count": len(s),
                "avg_ms": round(sum(s) / len(s), 2),
                "p50_ms": round(s[len(s) // 2], 2),
                "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))], 2),
                "max_ms": round(s[-1], 2),
            }
        return {"counters": dict(_counters), "latencies": stats}
