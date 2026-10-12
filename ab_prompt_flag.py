"""Stable, deterministic prompt canary assignment; never logs the key."""

import hashlib


def prompt_for_request(
    staging_key: str | None,
    environment: str,
    canary_enabled: bool,
    canary_percent: int = 10,
    stable_version: str = "1.2.0",
    candidate_version: str = "1.3.0-candidate",
) -> str:
    if not 0 <= canary_percent <= 100:
        raise ValueError("canary_percent must be between 0 and 100")
    if not canary_enabled or environment != "staging" or not staging_key:
        return stable_version
    bucket = int.from_bytes(hashlib.sha256(staging_key.encode("utf-8")).digest()[:8], "big") % 100
    return candidate_version if bucket < canary_percent else stable_version