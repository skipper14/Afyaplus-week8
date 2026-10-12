"""Fixture-backed FastAPI contract for versioned AfyaPlus triage prompts."""

import json
import os
from pathlib import Path
from time import monotonic
from typing import Literal
from uuid import uuid4

import yaml
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from ab_prompt_flag import prompt_for_request
from check_prompt_pin import ROOT, PinValidationError, validate_pin
from logistics_mcp_versioned import MCP_SERVER_VERSION, REQUIRED_TOOLS
from tool_metrics import record_http_request, snapshot


class TriageRequest(BaseModel):
    case_id: str = Field(min_length=3, max_length=80)
    symptoms: str = Field(min_length=3, max_length=2000)


class TriageResponse(BaseModel):
    case_id: str
    urgency: Literal["routine", "urgent", "emergency", "human_review"]
    action: str
    human_review_required: bool
    disclaimer: str
    prompt_version: str
    prompt_sha256: str
    model_id: str
    model_version: str
    mcp_server_version: str
    trace_id: str


def load_response_fixture(case_id: str, prompt_version: str, root: Path = ROOT) -> tuple[dict, dict]:
    metadata = validate_pin(prompt_version, root)
    fixture_path = root / "fixtures" / "responses" / f"{metadata['prompt_sha256']}.json"
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PinValidationError(f"response fixture is unavailable: {error}") from error
    if fixture.get("prompt_sha256") != metadata["prompt_sha256"]:
        raise PinValidationError("response fixture prompt SHA does not match the pin")
    response = fixture.get("responses", {}).get(case_id)
    if response is None:
        response = {
            "urgency": "human_review",
            "action": "A qualified clinician should review this case before action.",
            "human_review_required": True,
            "disclaimer": "This is routing support, not a diagnosis.",
        }
    return response, metadata


def create_app() -> FastAPI:
    app = FastAPI(title="AfyaPlus Versioned Triage Stub", version="1.2.0")
    try:
        default_metadata = validate_pin()
        config = yaml.safe_load((ROOT / "config" / "triage.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, PinValidationError) as error:
        raise RuntimeError(f"release pin validation failed: {error}") from error

    @app.middleware("http")
    async def request_metrics(request, call_next):
        started = monotonic()
        try:
            response = await call_next(request)
        except Exception:
            record_http_request(500, (monotonic() - started) * 1000)
            raise
        record_http_request(response.status_code, (monotonic() - started) * 1000)
        return response

    @app.get("/health")
    def health() -> dict:
        try:
            runtime_metadata = validate_pin(os.getenv("PROMPT_VERSION") or default_metadata["prompt_version"])
        except PinValidationError as error:
            raise HTTPException(status_code=503, detail="Runtime prompt pin is invalid") from error
        return {
            "status": "ok",
            "release_tag": runtime_metadata["release_tag"],
            "image_tag": runtime_metadata["image_tag"],
            "config_version": runtime_metadata["config_version"],
            "prompt_version": runtime_metadata["prompt_version"],
            "prompt_sha256": runtime_metadata["prompt_sha256"],
            "mcp_server_version": MCP_SERVER_VERSION,
            "mcp_schema_sha256": runtime_metadata["mcp_schema_sha256"],
            "mcp_required_tools": list(REQUIRED_TOOLS),
            "model_id": default_metadata["model_id"],
            "model_version": default_metadata["model_version"],
            "inference_mode": "fixture_stub_no_provider_calls",
        }

    @app.get("/metrics/tools")
    def tool_metrics() -> dict:
        return snapshot()

    @app.get("/metrics")
    def service_metrics() -> dict:
        return snapshot()

    @app.post("/triage", response_model=TriageResponse)
    def triage(request: TriageRequest, x_staging_key: str | None = Header(default=None)) -> TriageResponse:
        try:
            stable_metadata = validate_pin(os.getenv("PROMPT_VERSION") or default_metadata["prompt_version"])
        except PinValidationError as error:
            raise HTTPException(status_code=503, detail="Runtime prompt pin is invalid") from error
        environment = os.getenv("APP_ENV", "development")
        canary = os.getenv("PROMPT_CANARY_ENABLED", "false").casefold() == "true"
        canary_config = config.get("canary", {})
        selected_version = prompt_for_request(
            staging_key=x_staging_key,
            environment=environment,
            canary_enabled=canary and bool(canary_config.get("enabled", False)),
            canary_percent=int(canary_config.get("percent", 10)),
            stable_version=stable_metadata["prompt_version"],
            candidate_version=str(canary_config.get("candidate_prompt_version", "")),
        )
        try:
            response, metadata = load_response_fixture(request.case_id, selected_version)
        except PinValidationError as error:
            raise HTTPException(status_code=503, detail="Pinned prompt fixture unavailable") from error
        return TriageResponse(
            case_id=request.case_id,
            urgency=response["urgency"],
            action=response["action"],
            human_review_required=bool(response["human_review_required"]),
            disclaimer=response["disclaimer"],
            prompt_version=metadata["prompt_version"],
            prompt_sha256=metadata["prompt_sha256"],
            model_id=metadata["model_id"],
            model_version=metadata["model_version"],
            mcp_server_version=metadata["mcp_server_version"],
            trace_id=uuid4().hex,
        )

    return app


app = create_app()