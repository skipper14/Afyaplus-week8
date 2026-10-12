"""Smoke-check runtime version, structured triage, error rate, and p95 guardrails."""

import argparse
import json
import sys
import urllib.error
import urllib.request


def get_json(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--expected-prompt", default="1.2.0")
    parser.add_argument("--max-error-rate", type=float, default=0.10)
    parser.add_argument("--max-p95-ms", type=float, default=2000)
    args = parser.parse_args()
    try:
        health_status, health = get_json(f"{args.base_url}/health")
        if health_status != 200 or health.get("status") != "ok" or health.get("prompt_version") != args.expected_prompt:
            raise RuntimeError("health status or active prompt version is invalid")
        triage_status, triage = post_json(f"{args.base_url}/triage", {"case_id": "breathing-emergency-001", "symptoms": "severe chest pain and trouble breathing"})
        if triage_status != 200 or triage.get("urgency") != "emergency" or triage.get("human_review_required") is not True:
            raise RuntimeError("triage response contract or emergency fixture failed")
        _, metrics = get_json(f"{args.base_url}/metrics")
        http = metrics["http"]
        if http["error_rate"] >= args.max_error_rate:
            raise RuntimeError(f"error rate {http['error_rate']:.3f} is not below {args.max_error_rate:.3f}")
        if http["p95_latency_ms"] >= args.max_p95_ms:
            raise RuntimeError(f"p95 {http['p95_latency_ms']:.1f}ms is not below {args.max_p95_ms:.0f}ms")
        print(json.dumps({"status": "ok", "prompt_version": health["prompt_version"], "prompt_sha256": health["prompt_sha256"], "triage_status": triage_status, "error_rate": http["error_rate"], "p95_latency_ms": http["p95_latency_ms"], "gate": "passed"}, sort_keys=True))
        return 0
    except (OSError, urllib.error.URLError, json.JSONDecodeError, KeyError, RuntimeError) as error:
        print(json.dumps({"status": "failed", "gate": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())