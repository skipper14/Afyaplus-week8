**AfyaPlus Week 8 **

**Overview**

This project demonstrates controlled changes to AfyaPlus triage prompts and
read-only clinic MCP tools. The active release is prompt/config/MCP 1.2.0;
prompt 1.3.0-candidate is opt-in for 10% of staging keys only. CI uses
fixture responses, never sends symptoms to a paid provider, fails closed on
hash/evaluation/MCP/runtime regressions, and ends in an ephemeral Docker
Compose deployment stub. The app's structured triage response is a deterministic
fallback, not live LLM inference or medical diagnosis.

**Versions**
prompts: prompt 1.2.0 SHA pinned in prompts/pin.json (with 1.3.0-candidate opt-in for 10% of staging keys only)
config / model_version: config 1.2.0 (and model_version label updated via scripts/retrain_stub.py)
mcp server: MCP server 1.2.0 (with tool-schema SHA separately pinned in both release files)
image tag: afyaplus-week8:v1.2.0 (resolving to local image ID sha256:728d13f3191b6470bce71d7d95ee3fe93546a9e2c4169a7b7542463203b4d7fc)

**CI and release pipeline**

GitHub Actions is defined in [`.github/workflows/ci.yml`](.github/workflows/ci.yml):
pull requests and `main` run lint/tests, then stable/candidate golden eval,
then MCP health; only after those succeed can the image build and main/tag
deploy stub run. `workflow_dispatch` is also available. The
[`azure-pipelines.yml`](azure-pipelines.yml) mirrors those gates as
config-as-code. No Azure organization or cloud deployment is claimed.

The same stages can be run locally in the repository venv:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/run_pipeline.py
```

The runner ends with a local Docker Compose health/deployment check, records the
image ID and health response, then tears the service down. Use
`--skip-docker` where Docker is unavailable. To run only lint/tests/eval/MCP:

```bash
python3 -m ruff check .
python3 -m pytest -q
python3 eval_prompts.py --min-agreement 0.85
python3 scripts/check_mcp_health.py
```

**Eval gate and blocking controls**

[`evals/golden.jsonl`](evals/golden.jsonl) has four explicitly labelled,
synthetic routing fixtures. [`eval_prompts.py`](eval_prompts.py) prints
urgency agreement and fails unless it is at least 0.85, human-review
agreement is 1.00, and forbidden-phrase violations are 0. The same
score gate runs for stable and candidate prompts. This small golden set is a
regression smoke test, not proof of clinical quality.

The MCP probe performs a stdio JSON-RPC initialize, lists the required tools,
and calls `search_clinics`, `find_available_clinics`, and `check_stock` using
local fixtures. It exits nonzero on handshake errors, missing tools, bad
schema/results, or version mismatch, so deploy depends on this stage. Negative
controls:

```bash
python eval_prompts.py --simulate-regression --min-agreement 0.85
python scripts/check_mcp_health.py --require-tool missing_required_tool
```

Both commands must exit 1. Evidence/results are recorded in
[`evidence/pipeline_dry_run.md`](evidence/pipeline_dry_run.md).


**Runtime, rollback, and observability**

- Set `PROMPT_VERSION=1.2.0` on the same image to roll back; `/health` returns
  the actual active version and SHA. Unpinned versions return 503.
- The candidate is assigned by a stable hash to 10% of staging keys only;
  production stays on the stable pin. Never log staging keys or symptom text.
- `/metrics` reports HTTP count, status, error rate, and p95 latency;
  `/metrics/tools` exposes process-local MCP counters. Neither stores request
  bodies. The runtime smoke gate requires error rate **<0.10** and p95 **<2s**.
- Docker Compose uses `CostCenter=afyaplus-ai-platform`, environment and
  workload labels, plus CPU/memory limits. Companion Week 7 budget examples
  remain config-only; alerts do not stop spend.
- `scripts/retrain_stub.py` only proposes or applies a `model_version` label
  and changelog entry. **No GPU weights were trained.**

 **fallbacks**

- No paid model/API calls; deterministic fixtures use the same output schema.
- No GPU/retraining; the stub explicitly records that no weights changed.
- No Kubernetes, registry push, paid cloud or Azure organization; deployment
  stops at a local image build, Compose health check, and recorded image ID.
- GitHub Actions is supplied and can be manually dispatched, but this
  submission's run evidence is the local Python/Docker dry run, not a hosted
  Actions run.
- Configure branch protection to require `lint-test`, `eval`, and
  `mcp-health` plus clinical-ops and ML-engineering approval. 

Clinical prompts need clinical-owner approval; MCP schema changes need
clinical operations and engineering review. The system is recommend-against
autonomous clinical decisions: route uncertain or emergency cases to qualified
human care. See [`runbook.md`](runbook.md) and
[`clinical_ops_change_brief.md`](clinical_ops_change_brief.md).

## Local verification snapshot

The 2026-10-12 local dry run passed Ruff, **14 tests**, stable and candidate
evaluations at **1.00** (minimum 0.85), all three MCP tools, image build,
Compose health, and runtime contract checks, including the pinned MCP schema
SHA. The fixture smoke reported **0.0 error rate** and **3.61 ms p95**; image
ID was `sha256:728d13f3191b6470bce71d7d95ee3fe93546a9e2c4169a7b7542463203b4d7fc`.
This p95 is not a load test. See
[`evidence/pipeline_dry_run.md`](evidence/pipeline_dry_run.md) for passing and
deliberate-failure transcripts. The local tag guard confirmed `v1.2.0` matches
the prompt/config/MCP/image pins.

**Not claimed:** a hosted GitHub Actions/Azure run, paid cloud deployment,
live model inference, GPU training, clinical sign-off.
