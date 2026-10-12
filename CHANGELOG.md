# Changelog

## v1.2.0 - 2026-10-12

- Pin triage prompt 1.2.0 SHA, config 1.2.0, image tag `afyaplus-week8:v1.2.0`, and MCP server 1.2.0.
- Add a fixture-backed FastAPI triage endpoint with version/SHA health reporting.
- Add golden-set, MCP stdio, prompt pin, rollback, and metrics gates.
- No model weights were trained; the model identifier is `fixture/triage-stub`.

## 1.3.0-candidate - not released

- Add a candidate prompt for a deterministic 10% staging canary.
- Candidate remains opt-in, pinned by SHA, and blocked from production routing.
- No weights were trained and no live model calls were made.