# Change-control brief (clinical_ops)

**Decision requested:** approve a staging-only, 10% test of the candidate
triage wording. Do not use it for autonomous clinical decisions.

## What changes

The current prompt is **1.2.0**. Candidate wording is **1.3.0-candidate**.
Only staging requests assigned by a stable, hashed staging-key split may see
the candidate; production remains on 1.2.0. The response format and emergency
and human-review routes remain the same. The local service uses answer fixtures
and does not send patient text to an AI provider.

## What was checked

- Four labelled examples checked each prompt version for correct urgency,
  human-review routing, and phrases the answer must not contain.
- The recorded fixture score is **1.00 agreement** for the stable and candidate
  bundles against these four labels; minimum pass is **0.85**, with **zero**
  forbidden-phrase or review-label violations required. Four examples are a
  smoke gate, not proof of clinical safety or broad model quality.
- The local MCP check confirms `search_clinics`, `find_available_clinics`,
  and `check_stock` respond through the protocol handshake. A missing tool
  makes the check fail and blocks deployment.
- `/health` shows the active prompt version and SHA; the runtime stub returns
  fixtures and makes no paid model call.

## Rollback and decision

Rollback immediately by setting `PROMPT_VERSION=1.2.0` on the same image, then
confirm `/health` reports prompt 1.2.0 and its pinned SHA. Use Git tag
`v1.2.0` if the image itself must be restored.

**GO** only for the limited staging canary when the golden-set score is at
least 0.85, forbidden phrases and review routes have zero violations, the MCP
handshake includes `check_stock`, error rate stays below 0.10, and p95 response
time stays below 2 seconds. **NO-GO** for production or autonomous decisions
until clinical operations and ML engineering approve, real workload evidence
exists, and fallbacks are tested.

**Approvals:** required reviewers are clinical_ops and ml-eng. No human
approval is recorded yet; repository ruleset owners must configure and approve
the pull request before release. The runbook defines evidence and rollback.