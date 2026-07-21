#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "traceability.json"
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def collect() -> dict[str, Any]:
    specs: list[dict[str, Any]] = []
    for path in sorted((ROOT / "specs").rglob("SPEC-*.md")):
        match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
        if not match:
            continue
        data = yaml.safe_load(match.group(1))
        # Skipping a malformed spec would silently regenerate an incomplete
        # artifact with exit 0; fail cleanly and point at the validator instead.
        if not isinstance(data, dict) or any(
            key not in data for key in ("spec_id", "status", "standards", "requirements")
        ):
            raise SystemExit(
                f"malformed spec front matter in {path.relative_to(ROOT)}; "
                f"run scripts/validate_specs.py for details"
            )
        specs.append(
            {
                "spec_id": data["spec_id"],
                "path": str(path.relative_to(ROOT)),
                "status": data["status"],
                "standards": data["standards"],
                "requirements": data["requirements"],
            }
        )
    verification_map = yaml.safe_load(
        (ROOT / "specs" / "verification-map.yaml").read_text(encoding="utf-8")
    )
    return {
        "schema_version": "1.1.0",
        "specifications": specs,
        "verifications": verification_map["verifications"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    encoded = json.dumps(collect(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != encoded:
            print("traceability artifact is stale; run: make traceability")
            return 1
        print("Traceability artifact is current")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(encoded, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
