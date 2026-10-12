import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import check_prompt_pin
from ab_prompt_flag import prompt_for_request
from check_prompt_pin import ROOT, PinValidationError, validate_pin
from eval_prompts import evaluate
from logistics_mcp_versioned import REQUIRED_TOOLS
from prompt_app import app
from scripts.check_mcp_health import MCPHealthError, probe_mcp
from scripts.retrain_stub import update_model_version
from tool_metrics import record_tool_call, reset, snapshot


def test_release_pin_aligns_prompt_config_image_and_mcp() -> None:
    release = validate_pin()

    assert release["release_tag"] == "v1.2.0"
    assert release["image_tag"] == "afyaplus-week8:v1.2.0"
    assert release["prompt_version"] == release["mcp_server_version"] == "1.2.0"
    assert len(release["prompt_sha256"]) == 64


def test_pin_fails_closed_when_prompt_changes(tmp_path: Path) -> None:
    copy = tmp_path / "repo"
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", ".ruff_cache"))
    prompt = copy / "prompts" / "triage_system_v1.2.0.txt"
    prompt.write_text(prompt.read_text(encoding="utf-8") + "Unauthorized edit.\n", encoding="utf-8")

    with pytest.raises(PinValidationError, match="SHA mismatch"):
        validate_pin(root=copy)


def test_health_exposes_runtime_version_and_hash() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["release_tag"] == "v1.2.0"
    assert body["prompt_version"] == "1.2.0"
    assert len(body["prompt_sha256"]) == 64
    assert len(body["mcp_schema_sha256"]) == 64
    assert set(REQUIRED_TOOLS).issubset(body["mcp_required_tools"])
    assert body["inference_mode"] == "fixture_stub_no_provider_calls"


def test_metrics_report_error_rate_and_p95_without_payloads() -> None:
    reset()
    with TestClient(app) as client:
        client.get("/health")
        metrics = client.get("/metrics").json()["http"]
    assert metrics["requests"] == 1
    assert metrics["error_rate"] == 0
    assert metrics["p95_latency_ms"] >= 0
    reset()


def test_prompt_version_override_supports_same_image_rollback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPT_VERSION", "1.2.0")
    with TestClient(app) as client:
        response = client.get("/health")
        triage = client.post("/triage", json={"case_id": "breathing-emergency-001", "symptoms": "severe chest pain and trouble breathing"})

    assert response.status_code == 200
    assert response.json()["prompt_version"] == "1.2.0"
    assert triage.status_code == 200
    assert triage.json()["prompt_version"] == "1.2.0"


def test_triage_uses_fixture_schema() -> None:
    with TestClient(app) as client:
        response = client.post("/triage", json={"case_id": "breathing-emergency-001", "symptoms": "severe chest pain and trouble breathing"})

    assert response.status_code == 200
    body = response.json()
    assert body["urgency"] == "emergency"
    assert body["human_review_required"] is True
    assert body["prompt_version"] == "1.2.0"
    assert body["trace_id"]


def test_unpinned_prompt_override_fails_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROMPT_VERSION", "9.9.9")
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 503


def test_staging_canary_is_stable_and_never_routes_production() -> None:
    assignments = [prompt_for_request(f"key-{index}", "staging", True) for index in range(1000)]
    candidate_count = assignments.count("1.3.0-candidate")

    assert 50 <= candidate_count <= 150
    assert prompt_for_request("key-1", "production", True) == "1.2.0"
    assert prompt_for_request("key-1", "staging", False) == "1.2.0"
    assert prompt_for_request("key-1", "staging", True) == prompt_for_request("key-1", "staging", True)


def test_golden_gate_passes_and_injected_regression_fails() -> None:
    assert evaluate(minimum_agreement=0.85)["passed"] is True
    failed = evaluate(minimum_agreement=0.85, simulate_regression=True)
    assert failed["urgency_agreement"] == 0.75
    assert failed["passed"] is False


def test_mcp_stdio_handshake_calls_required_tools() -> None:
    result = probe_mcp()

    assert result["status"] == "ok"
    assert result["version"] == "1.2.0"
    assert set(REQUIRED_TOOLS).issubset(result["probed"])


def test_missing_mcp_tool_fails_health_gate() -> None:
    with pytest.raises(MCPHealthError, match="tools missing"):
        probe_mcp((*REQUIRED_TOOLS, "missing_required_tool"))


def test_mcp_schema_drift_fails_release_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(check_prompt_pin, "tool_schema_sha256", lambda: "0" * 64)
    with pytest.raises(PinValidationError, match="MCP tool schema SHA"):
        validate_pin()


def test_metrics_aggregate_without_payloads() -> None:
    reset()
    record_tool_call("search_clinics", "1.2.0", "ok")
    record_tool_call("search_clinics", "1.2.0", "ok")

    metrics = snapshot()
    assert metrics["total_calls"] == 2
    assert metrics["calls"] == [{"tool": "search_clinics", "server_version": "1.2.0", "outcome": "ok", "calls": 2}]
    reset()


def test_retrain_stub_changes_version_and_logs_no_weights(tmp_path: Path) -> None:
    config_path = tmp_path / "triage.yaml"
    changelog_path = tmp_path / "CHANGELOG.md"
    config_path.write_text("model_version: stub-weights-1.0.0\n", encoding="utf-8")
    changelog_path.write_text("# Changelog\n", encoding="utf-8")

    line = update_model_version(config_path, changelog_path, "stub-weights-1.1.0", apply=True)

    assert "no weights trained" in line
    assert "stub-weights-1.1.0" in config_path.read_text(encoding="utf-8")
    assert "no weights trained" in changelog_path.read_text(encoding="utf-8")


def test_pin_file_is_valid_json() -> None:
    json.loads((ROOT / "prompts" / "pin.json").read_text(encoding="utf-8"))