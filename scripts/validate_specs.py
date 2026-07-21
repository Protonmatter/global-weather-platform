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
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def load_frontmatter(path: Path) -> dict[str, Any]:
    match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
    if not match:
        raise ValueError("missing YAML front matter")
    loaded = yaml.safe_load(match.group(1))
    if not isinstance(loaded, dict):
        raise ValueError("front matter must be an object")
    return loaded


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    seen_requirements: dict[str, Path] = {}
    failures: list[str] = []

    for path in sorted(SPEC_ROOT.rglob("SPEC-*.md")):
        try:
            data = load_frontmatter(path)
        except ValueError as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
            continue
        for error in validator.iter_errors(data):
            location = ".".join(str(item) for item in error.path)
            failures.append(f"{path.relative_to(ROOT)}:{location}: {error.message}")
        for requirement in data.get("requirements", []):
            requirement_id = requirement["id"]
            previous = seen_requirements.get(requirement_id)
            if previous is not None:
                failures.append(
                    f"duplicate requirement {requirement_id}: "
                    f"{previous.relative_to(ROOT)} and {path.relative_to(ROOT)}"
                )
            seen_requirements[requirement_id] = path

    if failures:
        print("Specification validation failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(f"Validated {len(seen_requirements)} requirements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
