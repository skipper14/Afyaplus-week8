"""Small stdio JSON-RPC MCP server backed only by local clinic/stock fixtures."""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from tool_metrics import record_tool_call

MCP_SERVER_VERSION = "1.2.0"
PROTOCOL_VERSION = "2024-11-05"
ROOT = Path(__file__).resolve().parent
REQUIRED_TOOLS = ("search_clinics", "find_available_clinics", "check_stock")

TOOL_DEFINITIONS = [
    {
        "name": "search_clinics",
        "description": "Search the local clinic catalog by name, city, service, or clinic ID.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "minLength": 2}, "country": {"type": "string", "minLength": 2, "maxLength": 2}},
            "required": ["query"],
        },
    },
    {
        "name": "find_available_clinics",
        "description": "Find local clinics with at least the requested appointment slots.",
        "inputSchema": {
            "type": "object",
            "properties": {"min_slots": {"type": "integer", "minimum": 1}, "country": {"type": "string", "minLength": 2, "maxLength": 2}},
        },
    },
    {
        "name": "check_stock",
        "description": "Check the deterministic sample inventory fixture; not a prescribing recommendation.",
        "inputSchema": {
            "type": "object",
            "properties": {"item_id": {"type": "string"}, "clinic_id": {"type": "string"}},
            "required": ["item_id"],
        },
    },
]


def tool_schema_sha256() -> str:
    """Hash the canonical tool names/descriptions/input schemas for release pinning."""
    canonical = json.dumps(TOOL_DEFINITIONS, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _load_json(filename: str) -> list[dict[str, Any]]:
    value = json.loads((ROOT / filename).read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{filename} must contain a list of objects")
    return value


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in REQUIRED_TOOLS:
        raise ValueError(f"unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise TypeError("tool arguments must be an object")
    if name == "search_clinics":
        query = arguments.get("query")
        country = arguments.get("country")
        if not isinstance(query, str) or len(query.strip()) < 2:
            raise ValueError("query must contain at least two characters")
        if country is not None and (not isinstance(country, str) or len(country) != 2 or not country.isupper()):
            raise ValueError("country must be a two-letter uppercase code")
        matches = [clinic for clinic in _load_json("clinics.json") if (country is None or clinic.get("country") == country) and query.casefold() in json.dumps(clinic).casefold()]
        result = {"ok": True, "count": len(matches), "clinics": matches}
    elif name == "find_available_clinics":
        minimum = arguments.get("min_slots", 1)
        country = arguments.get("country")
        if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
            raise ValueError("min_slots must be a positive integer")
        if country is not None and (not isinstance(country, str) or len(country) != 2 or not country.isupper()):
            raise ValueError("country must be a two-letter uppercase code")
        matches = [clinic for clinic in _load_json("clinics.json") if clinic.get("available_slots", 0) >= minimum and (country is None or clinic.get("country") == country)]
        result = {"ok": True, "count": len(matches), "clinics": matches}
    else:
        item_id = arguments.get("item_id")
        clinic_id = arguments.get("clinic_id")
        if not isinstance(item_id, str) or not item_id.strip():
            raise ValueError("item_id is required")
        matches = [stock for stock in _load_json("fixtures/stocks.json") if stock.get("item_id") == item_id and (clinic_id is None or stock.get("clinic_id") == clinic_id)]
        result = {"ok": True, "count": len(matches), "stock": matches}
    record_tool_call(name, MCP_SERVER_VERSION, "ok")
    return result


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "afyaplus-logistics", "version": MCP_SERVER_VERSION}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOL_DEFINITIONS}}
    if method == "tools/call":
        try:
            result = call_tool(params.get("name", ""), params.get("arguments", {}))
        except (ValueError, OSError, json.JSONDecodeError) as error:
            record_tool_call(str(params.get("name", "unknown")), MCP_SERVER_VERSION, "error")
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(error)}}
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": json.dumps(result, separators=(",", ":"))}], "structuredContent": result, "isError": False}}
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"method not found: {method}"}}


def main() -> int:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise TypeError("request must be a JSON object")
            response = handle_message(message)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(error)}}
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())