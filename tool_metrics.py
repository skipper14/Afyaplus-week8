"""Thread-safe in-memory MCP counters with no patient text or identifiers."""

import math
from collections import Counter, deque
from threading import Lock
from typing import Any

_lock = Lock()
_calls: Counter[tuple[str, str, str]] = Counter()
_http_statuses: Counter[int] = Counter()
_http_latency_ms: deque[float] = deque(maxlen=2000)
_http_errors = 0


def record_tool_call(tool_name: str, server_version: str, outcome: str) -> None:
    with _lock:
        _calls[(tool_name, server_version, outcome)] += 1


def record_http_request(status_code: int, duration_ms: float) -> None:
    global _http_errors
    with _lock:
        _http_statuses[status_code] += 1
        _http_latency_ms.append(max(0.0, duration_ms))
        if status_code >= 400:
            _http_errors += 1


def snapshot() -> dict[str, Any]:
    with _lock:
        rows = [
            {"tool": tool, "server_version": version, "outcome": outcome, "calls": count}
            for (tool, version, outcome), count in sorted(_calls.items())
        ]
        total_requests = sum(_http_statuses.values())
        latencies = sorted(_http_latency_ms)
        p95 = latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)] if latencies else 0.0
        http = {
            "requests": total_requests,
            "errors": _http_errors,
            "error_rate": _http_errors / total_requests if total_requests else 0.0,
            "p95_latency_ms": round(p95, 2),
            "statuses": {str(status): count for status, count in sorted(_http_statuses.items())},
        }
    return {"calls": rows, "total_calls": sum(row["calls"] for row in rows), "http": http}


def reset() -> None:
    global _http_errors
    with _lock:
        _calls.clear()
        _http_statuses.clear()
        _http_latency_ms.clear()
        _http_errors = 0