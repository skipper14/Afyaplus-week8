# Local Pipeline Evidence

Observed 2026-10-12 with the existing Python 3.14 venv and local Docker Engine.
No paid model API or cloud account was used. All triage outputs came from
checked-in fixtures.

## Passing stages

Command:

```bash
python scripts/run_pipeline.py
```

Observed stage order and results:

```text
lint: All checks passed
tests: 14 passed
stable prompt 1.2.0 eval: urgency_agreement=1.00, human_review_agreement=1.00, safety_violations=0, threshold=0.85, passed=true
candidate prompt 1.3.0-candidate eval: urgency_agreement=1.00, human_review_agreement=1.00, safety_violations=0, threshold=0.85, passed=true
MCP initialize/tools/list/tools/call: status=ok, version=1.2.0
MCP schema SHA: 7f0d70731c2416cf556e301dcc64883e4c2072a1e480c7011da273c0e85b6d2f
required tools: search_clinics, find_available_clinics, check_stock
docker build: afyaplus-week8:v1.2.0
runtime health: status=ok, prompt=1.2.0, MCP=1.2.0, schema SHA pinned
runtime contract: triage_status=200; error_rate=0.0; p95_latency_ms=3.61; gate=passed
image id: sha256:728d13f3191b6470bce71d7d95ee3fe93546a9e2c4169a7b7542463203b4d7fc
cleanup: Compose container and network removed
```

The measured p95 is for a local fixture smoke request, not a 10x load test or
production SLO claim. The API has no real model provider configured.

## Deliberate blocked gates

Eval command:

```bash
python eval_prompts.py --simulate-regression --min-agreement 0.85
```

```text
urgency_agreement=0.75, minimum_agreement=0.85, passed=false
exit code: 1
```

MCP command:

```bash
python scripts/check_mcp_health.py --require-tool missing_required_tool
```

```text
status=failed, error=required MCP tools missing: missing_required_tool
exit code: 1
```

The CI dependency graph places build/deploy after the eval and MCP jobs, so
either failure blocks deployment. These negative controls were run locally;
the YAML also includes them. GitHub-hosted Actions and Azure DevOps executions
are not claimed in this fallback submission.