#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SPEC_ROOT = ROOT / "specs"
SCHEMA_PATH = SPEC_ROOT / "_schema" / "spec.schema.json"
VERIFICATION_MAP_PATH = SPEC_ROOT / "verification-map.yaml"
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
VERIFICATION_STATUSES = {"planned", "implemented"}


def load_frontmatter(path: Path) -> dict[str, Any]:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("missing YAML front matter")
    loaded = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise ValueError("front matter must be an object")
    return loaded


def load_verification_map() -> dict[str, dict[str, Any]]:
    loaded = yaml.safe_load(VERIFICATION_MAP_PATH.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("verifications"), dict):
        raise ValueError("verification map must contain a 'verifications' object")
    return loaded["verifications"]


def validate_verification_map(
    verification_map: dict[str, dict[str, Any]], referenced: set[str]
) -> list[str]:
    map_name = str(VERIFICATION_MAP_PATH.relative_to(ROOT))
    failures: list[str] = []
    for verification_id, entry in verification_map.items():
        entry_status = entry.get("status")
        if entry_status not in VERIFICATION_STATUSES:
            failures.append(f"{map_name}: {verification_id} has invalid status {entry_status!r}")
        if verification_id not in referenced:
            failures.append(f"{map_name}: {verification_id} is not referenced by any spec")
        if entry_status == "implemented":
            evidence = entry.get("evidence") or []
            if not evidence:
                failures.append(f"{map_name}: implemented {verification_id} lists no evidence")
            for item in evidence:
                item_path = Path(item)
                if item_path.is_absolute() or ".." in item_path.parts:
                    failures.append(
                        f"{map_name}: evidence {item} for {verification_id} "
                        f"must be a repository-relative path"
                    )
                elif not (ROOT / item_path).exists():
                    failures.append(f"{map_name}: evidence {item} for {verification_id} not found")
    return failures


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    seen_requirements: dict[str, Path] = {}
    failures: list[str] = []

    try:
        verification_map = load_verification_map()
    except ValueError as exc:
        print(f"Specification validation failed: {exc}", file=sys.stderr)
        return 1
    referenced_verifications: set[str] = set()

    for path in sorted(SPEC_ROOT.rglob("SPEC-*.md")):
        try:
            data = load_frontmatter(path)
        except ValueError as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        for error in validator.iter_errors(data):
            location = ".".join(str(item) for item in error.path)
            failures.append(f"{path.relative_to(ROOT)}:{location}: {error.message}")
        spec_status = data.get("status")
        for requirement in data.get("requirements", []):
            requirement_id = requirement["id"]
            previous = seen_requirements.get(requirement_id)
            if previous is not None:
                failures.append(
                    f"duplicate requirement {requirement_id}: "
                    f"{previous.relative_to(ROOT)} and {path.relative_to(ROOT)}"
                )
            seen_requirements[requirement_id] = path
            for verification_id in requirement.get("verification", []):
                referenced_verifications.add(verification_id)
                entry = verification_map.get(verification_id)
                if entry is None:
                    failures.append(
                        f"{path.relative_to(ROOT)}: {requirement_id} references "
                        f"unknown verification {verification_id}"
                    )
                elif spec_status == "implemented" and entry.get("status") != "implemented":
                    failures.append(
                        f"{path.relative_to(ROOT)}: spec is implemented but "
                        f"verification {verification_id} for {requirement_id} is "
                        f"{entry.get('status')}"
                    )

    failures.extend(validate_verification_map(verification_map, referenced_verifications))

    if failures:
        print("Specification validation failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(
        f"Validated {len(seen_requirements)} requirements "
        f"and {len(verification_map)} verification references"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
