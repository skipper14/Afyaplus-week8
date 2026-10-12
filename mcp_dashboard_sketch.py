"""Print an aggregate, PHI-free sketch of MCP tool counters."""

import json

from tool_metrics import snapshot


def main() -> None:
    metrics = snapshot()
    print(json.dumps({"total_tool_calls": metrics["total_calls"], "by_tool_version_outcome": metrics["calls"]}, indent=2))


if __name__ == "__main__":
    main()