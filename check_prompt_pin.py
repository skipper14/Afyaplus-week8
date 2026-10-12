"""Validate prompt hashes and release/config/MCP version alignment."""

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from logistics_mcp_versioned import MCP_SERVER_VERSION, tool_schema_sha256

ROOT = Path(__file__).resolve().parent


class PinValidationError(ValueError):
    """Raised when the runtime bundle differs from its release pin."""


def load_release(root: Path = ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    pin_path = root / "prompts" / "pin.json"
    config_path = root / "config" / "triage.yaml"
    try:
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise PinValidationError(f"cannot load release config: {error}") from error
    if not isinstance(pin, dict) or not isinstance(config, dict):
        raise PinValidationError("pin and config must be objects")
    return pin, config


def validate_pin(prompt_version: str | None = None, root: Path = ROOT) -> dict[str, Any]:
    pin, config = load_release(root)
    required = {"release_tag", "image_tag", "config_version", "mcp_server_version", "mcp_schema_sha256", "default_prompt_version", "prompts"}
    if not required.issubset(pin):
        raise PinValidationError("pin.json is missing required release fields")
    expected_release = f"v{pin['default_prompt_version']}"
    expected_image = f"afyaplus-week8:{expected_release}"
    if pin["release_tag"] != expected_release or pin["image_tag"] != expected_image:
        raise PinValidationError("release tag, image tag, and default prompt version are not aligned")
    for key in ("config_version", "release_tag", "image_tag", "mcp_server_version"):
        if config.get(key) != pin[key]:
            raise PinValidationError(f"config {key} does not match prompts/pin.json")
    actual_mcp_schema_sha = tool_schema_sha256()
    if MCP_SERVER_VERSION != pin["mcp_server_version"]:
        raise PinValidationError("logistics_mcp_versioned.MCP_SERVER_VERSION does not match the pin")
    if actual_mcp_schema_sha != pin["mcp_schema_sha256"] or config.get("mcp_schema_sha256") != pin["mcp_schema_sha256"]:
        raise PinValidationError("MCP tool schema SHA does not match prompts/pin.json and config/triage.yaml")
    if config.get("prompt_version") != pin["default_prompt_version"]:
        raise PinValidationError("config prompt_version does not match default_prompt_version")
    if not isinstance(pin["prompts"], dict) or not pin["prompts"]:
        raise PinValidationError("pin must contain at least one prompt")

    for version, record in pin["prompts"].items():
        prompt_path = root / record.get("path", "")
        try:
            actual_sha = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
        except OSError as error:
            raise PinValidationError(f"prompt {version} is unavailable: {error}") from error
        if actual_sha != record.get("sha256"):
            raise PinValidationError(f"prompt SHA mismatch for {version}")

    selected_version = prompt_version or pin["default_prompt_version"]
    if selected_version not in pin["prompts"]:
        raise PinValidationError(f"prompt version is not pinned: {selected_version}")
    selected = pin["prompts"][selected_version]
    return {
        "release_tag": pin["release_tag"],
        "image_tag": pin["image_tag"],
        "config_version": pin["config_version"],
        "mcp_server_version": pin["mcp_server_version"],
        "mcp_schema_sha256": pin["mcp_schema_sha256"],
        "prompt_version": selected_version,
        "prompt_sha256": selected["sha256"],
        "prompt_path": selected["path"],
        "model_id": config["model_id"],
        "model_version": config["model_version"],
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-version")
    args = parser.parse_args()
    print(json.dumps(validate_pin(args.prompt_version), sort_keys=True))