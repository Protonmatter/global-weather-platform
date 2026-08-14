#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

SPECIFICATION_ID = re.compile(r"\bSPEC-[0-9]{3}\b")
REQUIREMENT_ID = re.compile(r"\b[A-Z]+-[A-Z]+-[0-9]{4}\b")
SECTION = re.compile(r"^## Requirement IDs\s*$\n(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)


def validate_pull_request(body: str, actor: str) -> list[str]:
    if actor == "dependabot[bot]":
        # Automated ecosystem updates are governed by the standing dependency
        # requirement and still traverse every code, lock, and end-to-end gate.
        return []
    match = SECTION.search(body)
    if match is None:
        return ["pull request body must retain the '## Requirement IDs' section"]
    section = match.group(1)
    failures: list[str] = []
    if SPECIFICATION_ID.search(section) is None:
        failures.append("Requirement IDs section must name at least one SPEC-nnn specification")
    if REQUIREMENT_ID.search(section) is None:
        failures.append("Requirement IDs section must name at least one normative requirement ID")
    return failures


def _load_event(path: Path) -> dict[str, Any]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("GitHub event must be a JSON object")
    return loaded


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("GITHUB_EVENT_PATH is required", file=sys.stderr)
        return 2
    try:
        event = _load_event(Path(event_path))
        pull_request = event.get("pull_request", {})
        body = pull_request.get("body") or ""
        actor = event.get("sender", {}).get("login") or os.environ.get("GITHUB_ACTOR", "")
        if not isinstance(body, str) or not isinstance(actor, str):
            raise ValueError("pull request body and actor must be strings")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Cannot validate pull request requirements: {type(error).__name__}", file=sys.stderr)
        return 2

    failures = validate_pull_request(body, actor)
    if failures:
        print("Pull request specification gate failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print("Pull request references specification and requirement identifiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
