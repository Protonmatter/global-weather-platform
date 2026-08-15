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
TRACEABILITY_PATH = Path(__file__).resolve().parents[1] / "artifacts/traceability.json"


def _load_requirement_registry(path: Path = TRACEABILITY_PATH) -> dict[str, set[str]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    specifications = loaded.get("specifications") if isinstance(loaded, dict) else None
    if not isinstance(specifications, list):
        raise ValueError("traceability specifications must be a list")
    registry: dict[str, set[str]] = {}
    for specification in specifications:
        if not isinstance(specification, dict):
            raise ValueError("traceability specification must be an object")
        spec_id = specification.get("spec_id")
        requirements = specification.get("requirements")
        if not isinstance(spec_id, str) or not isinstance(requirements, list):
            raise ValueError("traceability specification identity is invalid")
        requirement_ids: set[str] = set()
        for requirement in requirements:
            requirement_id = requirement.get("id") if isinstance(requirement, dict) else None
            if not isinstance(requirement_id, str):
                raise ValueError("traceability requirement identity is invalid")
            requirement_ids.add(requirement_id)
        registry[spec_id] = requirement_ids
    return registry


def validate_pull_request(body: str, actor: str) -> list[str]:
    registry = _load_requirement_registry()
    if actor == "dependabot[bot]":
        # Automated ecosystem updates are governed by the standing dependency
        # requirement and still traverse every code, lock, and end-to-end gate.
        if "DEL-DEP-0005" in registry.get("SPEC-820", set()):
            return []
        return ["standing Dependabot requirement SPEC-820/DEL-DEP-0005 is unavailable"]
    match = SECTION.search(body)
    if match is None:
        return ["pull request body must retain the '## Requirement IDs' section"]
    section = match.group(1)
    failures: list[str] = []
    specification_ids = set(SPECIFICATION_ID.findall(section))
    requirement_ids = set(REQUIREMENT_ID.findall(section))
    if not specification_ids:
        failures.append("Requirement IDs section must name at least one SPEC-nnn specification")
    if not requirement_ids:
        failures.append("Requirement IDs section must name at least one normative requirement ID")
    unknown_specifications = sorted(specification_ids - registry.keys())
    if unknown_specifications:
        failures.append(f"unknown specification IDs: {', '.join(unknown_specifications)}")
    known_requirement_ids = set().union(*registry.values()) if registry else set()
    unknown_requirements = sorted(requirement_ids - known_requirement_ids)
    if unknown_requirements:
        failures.append(f"unknown requirement IDs: {', '.join(unknown_requirements)}")
    valid_specification_ids = specification_ids & registry.keys()
    if valid_specification_ids:
        referenced_requirements = set().union(
            *(registry[spec_id] for spec_id in valid_specification_ids)
        )
        mismatched_requirements = sorted(
            requirement_ids - set(unknown_requirements) - referenced_requirements
        )
        if mismatched_requirements:
            failures.append(
                "requirement IDs do not belong to the named specifications: "
                + ", ".join(mismatched_requirements)
            )
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

    try:
        failures = validate_pull_request(body, actor)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Cannot validate requirement registry: {type(error).__name__}", file=sys.stderr)
        return 2
    if failures:
        print("Pull request specification gate failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print("Pull request references specification and requirement identifiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
