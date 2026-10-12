"""Probe the local MCP stdio handshake and every required tool; exit nonzero on failure."""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from check_prompt_pin import PinValidationError, validate_pin

REQUIRED_TOOLS = ("search_clinics", "find_available_clinics", "check_stock")
SAMPLE_ARGUMENTS = {
    "search_clinics": {"query": "diagnostics", "country": "KE"},
    "find_available_clinics": {"min_slots": 1, "country": "KE"},
    "check_stock": {"item_id": "oral_rehydration_salts", "clinic_id": "KE-NBO-001"},
}


class MCPHealthError(RuntimeError):
    """Raised when protocol negotiation or a required tool probe fails."""


def _response_for(responses: list[dict[str, Any]], request_id: int) -> dict[str, Any]:
    for response in responses:
        if response.get("id") == request_id:
            if "error" in response:
                raise MCPHealthError(f"MCP request {request_id} failed: {response['error']}")
            return response.get("result", {})
    raise MCPHealthError(f"MCP server did not answer request {request_id}")


def probe_mcp(required_tools: tuple[str, ...] = REQUIRED_TOOLS, expected_version: str = "1.2.0") -> dict[str, Any]:
    try:
        release = validate_pin()
    except PinValidationError as error:
        raise MCPHealthError(f"release/MCP schema pin failed: {error}") from error
    requests: list[dict[str, Any]] = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "afyaplus-ci-probe", "version": "1.0.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    call_ids: dict[str, int] = {}
    next_id = 3
    for tool_name in required_tools:
        if tool_name not in SAMPLE_ARGUMENTS:
            continue
        call_ids[tool_name] = next_id
        requests.append({"jsonrpc": "2.0", "id": next_id, "method": "tools/call", "params": {"name": tool_name, "arguments": SAMPLE_ARGUMENTS[tool_name]}})
        next_id += 1

    command = [sys.executable, str(ROOT / "logistics_mcp_versioned.py")]
    input_data = "".join(json.dumps(request, separators=(",", ":")) + "\n" for request in requests)
    try:
        completed = subprocess.run(command, input=input_data, text=True, capture_output=True, timeout=8, cwd=ROOT, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MCPHealthError(f"could not complete stdio handshake: {error}") from error
    if completed.returncode != 0:
        raise MCPHealthError(f"MCP server exited {completed.returncode}: {completed.stderr.strip()}")
    try:
        responses = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        raise MCPHealthError(f"MCP stdout contained invalid JSON: {error}") from error

    initialize = _response_for(responses, 1)
    server_info = initialize.get("serverInfo", {})
    if initialize.get("protocolVersion") != "2024-11-05":
        raise MCPHealthError("MCP protocol version mismatch")
    if server_info.get("version") != expected_version:
        raise MCPHealthError(f"MCP server version mismatch: {server_info.get('version')}")

    tools_result = _response_for(responses, 2)
    tools = tools_result.get("tools", [])
    available = {tool.get("name") for tool in tools}
    missing = sorted(set(required_tools) - available)
    if missing:
        raise MCPHealthError(f"required MCP tools missing: {', '.join(missing)}")

    for tool_name, request_id in call_ids.items():
        call_result = _response_for(responses, request_id)
        if call_result.get("isError"):
            raise MCPHealthError(f"tool {tool_name} returned isError")
        structured = call_result.get("structuredContent")
        if not isinstance(structured, dict) or structured.get("ok") is not True:
            raise MCPHealthError(f"tool {tool_name} returned no successful structured result")

    return {"status": "ok", "server": server_info.get("name"), "version": server_info["version"], "schema_sha256": release["mcp_schema_sha256"], "protocol": initialize["protocolVersion"], "tools": sorted(available), "probed": list(required_tools), "transport": "stdio-jsonrpc-local-fixture"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-version", default="1.2.0")
    parser.add_argument("--require-tool", action="append", default=[], help="add a required tool; useful for negative gate verification")
    args = parser.parse_args()
    required_tools = tuple(dict.fromkeys((*REQUIRED_TOOLS, *args.require_tool)))
    try:
        print(json.dumps(probe_mcp(required_tools, args.expected_version), sort_keys=True))
    except MCPHealthError as error:
        print(json.dumps({"status": "failed", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())