"""Run CI-equivalent stages locally; optional Docker stage is the deployment stub."""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_stage(name: str, command: list[str], env: dict[str, str] | None = None) -> None:
    print(f"\n=== {name} ===", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def wait_for_health(url: str, expected_prompt: str, timeout_seconds: int = 20) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                body = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and body.get("status") == "ok" and body.get("prompt_version") == expected_prompt:
                return body
            last_error = RuntimeError(f"health response did not match the pinned prompt: {body}")
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            last_error = error
        time.sleep(0.25)
    raise RuntimeError(f"application health check failed: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-docker", action="store_true", help="run lint/test/eval/MCP stages only")
    args = parser.parse_args()
    python = sys.executable
    run_stage("lint", [python, "-m", "ruff", "check", "."])
    run_stage("test", [python, "-m", "pytest", "-q"])
    run_stage("eval-stable", [python, "eval_prompts.py", "--prompt-version", "1.2.0", "--min-agreement", "0.85"])
    run_stage("eval-candidate", [python, "eval_prompts.py", "--prompt-version", "1.3.0-candidate", "--min-agreement", "0.85"])
    run_stage("mcp-health", [python, "scripts/check_mcp_health.py"])
    if args.skip_docker:
        print("deploy_stub=skipped")
        return 0

    pin = json.loads((ROOT / "prompts" / "pin.json").read_text(encoding="utf-8"))
    image_tag = pin["image_tag"]
    environment = os.environ.copy()
    environment["IMAGE_TAG"] = image_tag.split(":", 1)[1]
    environment["HOST_PORT"] = environment.get("HOST_PORT", "18765")
    runtime_prompt = environment.get("PROMPT_VERSION") or pin["default_prompt_version"]
    environment["PROMPT_VERSION"] = runtime_prompt
    project = "afyaplus-week8-ci"
    compose = ["docker", "compose", "-p", project, "-f", "docker-compose.yml"]
    try:
        run_stage("build", compose + ["build", "--pull"], environment)
        run_stage("deploy-stub", compose + ["up", "--detach"], environment)
        health = wait_for_health(f"http://127.0.0.1:{environment['HOST_PORT']}/health", runtime_prompt)
        run_stage("runtime-contract", [python, "scripts/check_runtime.py", "--base-url", f"http://127.0.0.1:{environment['HOST_PORT']}", "--expected-prompt", runtime_prompt], environment)
        image_id = subprocess.check_output(["docker", "image", "inspect", image_tag, "--format", "{{.Id}}"], cwd=ROOT, text=True).strip()
        print(json.dumps({"deploy_stub": "healthy", "image": image_tag, "image_id": image_id, "health": health}, sort_keys=True))
    finally:
        subprocess.run(compose + ["down", "--remove-orphans"], cwd=ROOT, env=environment, check=False)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as error:
        print(f"pipeline blocked at command exit={error.returncode}: {error.cmd}", file=sys.stderr)
        raise SystemExit(error.returncode or 1)