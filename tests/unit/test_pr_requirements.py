import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "validate_pr_requirements", ROOT / "scripts/validate_pr_requirements.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pull_request_requires_specification_and_requirement_ids() -> None:
    validator = load_validator()
    body = """## Scope

Delivery controls.

## Requirement IDs

- SPEC-820
- DEL-CI-0002

## Test evidence

Complete CI.
"""
    assert validator.validate_pull_request(body, "engineer") == []
    assert (
        len(validator.validate_pull_request(body.replace("SPEC-820", "delivery"), "engineer")) == 1
    )
    assert (
        len(validator.validate_pull_request(body.replace("DEL-CI-0002", "delivery"), "engineer"))
        == 1
    )


def test_dependabot_uses_the_standing_dependency_requirement() -> None:
    validator = load_validator()
    assert validator.validate_pull_request("", "dependabot[bot]") == []
