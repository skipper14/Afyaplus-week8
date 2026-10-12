# LLMOps Runbook

## Release sequence

1. Open a pull request for prompt, config, fixture, or MCP schema changes.
   Attach the before/after golden-set score and explain any changed clinical
   language. Require clinical-operations and ML-engineering review through the
   repository ruleset; CODEOWNERS currently maps to the repository owner until
   those GitHub teams/users are configured.
2. CI runs lint/tests, checks prompt hashes and aligned versions, evaluates
   stable and candidate prompts, probes MCP initialize/list/call for all three
   required tools, then builds. Any nonzero gate blocks the later stages.
3. Merge to `main` runs the local deployment stub on an ephemeral runner. CI
   records its image tag/ID, health response, and Compose logs as an artifact.
   No cloud account or paid model is required.
4. For release `v1.2.0`, the Git tag, `config/triage.yaml`, `prompts/pin.json`,
   prompt hash, MCP server version/schema hash, and image tag must agree.
   Release tags or tool-schema edits with a mismatched pin fail.

## Local pipeline dry run

```bash
python -m pip install -r requirements.txt
python scripts/run_pipeline.py
```

The runner executes Ruff, pytest, stable/candidate golden evaluation, MCP
health, image build, Compose startup, and `/health` plus runtime contract
checks. It records the image ID and always tears down its temporary service.
To run only the non-Docker gates, use
`python scripts/run_pipeline.py --skip-docker`.

To prove the eval gate blocks:

```bash
python eval_prompts.py --simulate-regression --min-agreement 0.85
```

Expected exit code is 1: urgency agreement falls to 0.75. To prove the MCP
gate blocks, run `python scripts/check_mcp_health.py --require-tool
missing_required_tool`; expected exit code is 1. These negative controls must
never be converted to `continue-on-error` in CI.

## Canary and rollback

The candidate prompt is pinned at `1.3.0-candidate`. Canary assignment is a
stable hash of the staging key: 10% of staging keys receive the candidate when
`APP_ENV=staging` and `PROMPT_CANARY_ENABLED=true`; production always uses the
stable pin. Never log the staging key. Keep the canary small until safety,
error-rate, and response-time reviews are complete.

Rollback uses the same image and a previously pinned prompt:

```bash
IMAGE_TAG=v1.2.0 PROMPT_VERSION=1.2.0 docker compose -f docker-compose.yml up --detach --no-build
curl -fsS http://127.0.0.1:8000/health
```

Health must report prompt 1.2.0 and its SHA. If that prompt or fixture is not
pinned, the app returns 503 rather than silently selecting another version.
The matching release marker is Git tag `v1.2.0`; tag rollback/redeploy is
reserved for image or dependency regressions.

The runtime p95/error-rate check in the local deploy stub uses only a few
fixture requests. Its timings verify the endpoint contract, not production
capacity; run an approved load test before making an SLO claim.

## Monitoring, cost, and governance

- `/health` reports release/image/config/prompt SHA, model stub, MCP version,
  and MCP tool-schema SHA. A schema change requires a new fingerprint and
  versioned review.
- `/metrics` reports request count, HTTP errors, error rate, p95 response time,
  and status counts. `/metrics/tools` adds in-memory MCP tool counts. No request
  body, symptoms, key, or patient identifier is retained in those counters.
- Logs should be collected from the CI artifact or container stdout. Tag
  deployment spend by `CostCenter=afyaplus-ai-platform`, environment, workload,
  release, and prompt version. Apply alert thresholds in the companion Week 7
  budget config; alerts are not spend kill switches.
- Prompt edits need clinical review; MCP schema/tool changes need clinical
  operations and ML engineering review. Do not treat this fixture stub as a
  diagnosis or live-model evaluation.
- The retrain stub only bumps `model_version` and writes a changelog line. It
  performs no training and produces no weights because there is no GPU.

## Definition of Done: Prompt or MCP pull request

- [ ] Prompt/config/MCP versions and SHA are pinned; image/release tags align.
- [ ] Golden fixtures have clinical-owner labels and harmful-claim exclusions.
- [ ] Stable and candidate evals pass threshold with no new safety violations.
- [ ] MCP initialize, tool list, and every required tool call pass; negative
  missing-tool probe fails as expected.
- [ ] API response schema, health versions, rollback override, and metrics tests pass.
- [ ] CI is green and image ID/deploy health evidence is attached.
- [ ] Clinical operations and ML engineering have approved the change.
- [ ] Release notes, cost/observability tags, canary plan, and rollback command
  are included.