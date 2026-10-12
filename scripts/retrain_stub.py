"""No-GPU retraining placeholder: bump a model label and changelog only."""

import argparse
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def update_model_version(config_path: Path, changelog_path: Path, model_version: str, apply: bool = False) -> str:
    if not model_version or any(character.isspace() for character in model_version):
        raise ValueError("model_version must be a non-empty token without spaces")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    previous = config.get("model_version", "unknown")
    line = f"- {date.today().isoformat()}: model stub version {previous} -> {model_version}; no weights trained (GPU unavailable).\n"
    if apply:
        config["model_version"] = model_version
        config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
        with changelog_path.open("a", encoding="utf-8") as changelog:
            changelog.write(line)
    return line.rstrip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--apply", action="store_true", help="write config and CHANGELOG; default only previews")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "triage.yaml")
    parser.add_argument("--changelog", type=Path, default=ROOT / "CHANGELOG.md")
    args = parser.parse_args()
    print(update_model_version(args.config, args.changelog, args.model_version, args.apply))
    if not args.apply:
        print("dry_run=true weights_trained=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())