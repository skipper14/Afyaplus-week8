"""Golden-set regression gate for the pinned, fixture-backed prompt bundle."""

import argparse
import json
from pathlib import Path
from typing import Any

from check_prompt_pin import ROOT, validate_pin
from prompt_app import load_response_fixture


def evaluate(
    prompt_version: str | None = None,
    minimum_agreement: float = 0.85,
    simulate_regression: bool = False,
    root: Path = ROOT,
) -> dict[str, Any]:
    if not 0 <= minimum_agreement <= 1:
        raise ValueError("minimum_agreement must be between zero and one")
    metadata = validate_pin(prompt_version, root)
    golden_path = root / "evals" / "golden.jsonl"
    cases = [json.loads(line) for line in golden_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases:
        raise ValueError("golden set must contain at least one case")

    urgency_matches = 0
    review_matches = 0
    safety_violations = 0
    for index, case in enumerate(cases):
        actual, _ = load_response_fixture(case["case_id"], metadata["prompt_version"], root)
        if simulate_regression and index == 0:
            actual = dict(actual)
            actual["urgency"] = "routine" if actual["urgency"] != "routine" else "emergency"
        urgency_matches += actual.get("urgency") == case["expected_urgency"]
        review_matches += actual.get("human_review_required") == case["expected_human_review"]
        response_text = " ".join(str(actual.get(key, "")) for key in ("urgency", "action", "disclaimer")).casefold()
        safety_violations += any(term.casefold() in response_text for term in case.get("must_not_contain", []))

    agreement = urgency_matches / len(cases)
    review_agreement = review_matches / len(cases)
    passed = agreement >= minimum_agreement and review_agreement == 1.0 and safety_violations == 0
    return {
        "prompt_version": metadata["prompt_version"],
        "prompt_sha256": metadata["prompt_sha256"],
        "cases": len(cases),
        "urgency_agreement": agreement,
        "minimum_agreement": minimum_agreement,
        "human_review_agreement": review_agreement,
        "safety_violations": safety_violations,
        "passed": passed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-version")
    parser.add_argument("--min-agreement", type=float, default=0.85)
    parser.add_argument("--simulate-regression", action="store_true", help="inject one bad urgency to prove the gate fails")
    args = parser.parse_args()
    report = evaluate(args.prompt_version, args.min_agreement, args.simulate_regression)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())