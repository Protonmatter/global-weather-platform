#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    failures: list[str] = []
    count = 0
    for path in sorted((ROOT / "schemas").rglob("*.schema.json")):
        count += 1
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
    if failures:
        print("Schema validation failed:", file=sys.stderr)
        print("\n".join(f"- {item}" for item in failures), file=sys.stderr)
        return 1
    print(f"Validated {count} JSON Schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
