#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

import yaml
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
EXACT_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
PINNED_ACTION = re.compile(r"^[^\s/]+/[^\s/@]+@[a-f0-9]{40}$")
LOCK_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)\s*\\$")
LOCK_HASH = re.compile(r"^\s+--hash=sha256:[a-f0-9]{64}(?:\s*\\)?$")


def _bounded(requirement: Requirement) -> bool:
    operators = {specifier.operator for specifier in requirement.specifier}
    return bool(operators & {">", ">="}) and bool(operators & {"<", "<="})


def _validate_python_manifest(failures: list[str]) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = list(project.get("dependencies", []))
    for values in project.get("optional-dependencies", {}).values():
        declared.extend(values)
    for raw in declared:
        requirement = Requirement(raw)
        if requirement.url is not None or not _bounded(requirement):
            failures.append(f"pyproject dependency must use a bounded registry range: {raw}")

    requires_python = project.get("requires-python", "")
    if not _bounded(Requirement(f"python{requires_python}")):
        failures.append("project.requires-python must have lower and upper bounds")


def _locked_names(path: Path, failures: list[str]) -> set[str]:
    names: set[str] = set()
    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith((" ", "#", "--")):
            index += 1
            continue
        match = LOCK_REQUIREMENT.fullmatch(line)
        if match is None:
            failures.append(f"{path.relative_to(ROOT)}:{index + 1}: dependency is not exact-pinned")
            index += 1
            continue
        names.add(Requirement(match.group(1)).name.casefold())
        index += 1
        hashes = 0
        while index < len(lines) and LOCK_HASH.fullmatch(lines[index]):
            hashes += 1
            index += 1
        if hashes == 0:
            failures.append(
                f"{path.relative_to(ROOT)}:{index}: {match.group(1)} has no SHA-256 hash"
            )
    if not names:
        failures.append(f"{path.relative_to(ROOT)} contains no locked dependencies")
    return names


def _validate_python_locks(failures: list[str]) -> None:
    compiler = _locked_names(ROOT / "requirements/compiler.lock", failures)
    production = _locked_names(ROOT / "requirements/production.lock", failures)
    ci = _locked_names(ROOT / "requirements/ci.lock", failures)
    missing_compiler = sorted({"pip", "pip-tools"} - compiler)
    if missing_compiler:
        failures.append(f"compiler lock omits bootstrap tools: {', '.join(missing_compiler)}")
    missing = sorted(production - ci)
    if missing:
        failures.append(f"CI lock omits production dependencies: {', '.join(missing)}")


def _validate_node(failures: list[str]) -> None:
    app = ROOT / "apps/operator-console"
    package = json.loads((app / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((app / "package-lock.json").read_text(encoding="utf-8"))
    for section in ("dependencies", "devDependencies", "overrides"):
        for name, version in package.get(section, {}).items():
            if not isinstance(version, str) or EXACT_SEMVER.fullmatch(version) is None:
                failures.append(f"operator-console {section}.{name} must use an exact version")
    if lock.get("lockfileVersion") != 3:
        failures.append("operator-console package-lock.json must use lockfileVersion 3")
    root_package = lock.get("packages", {}).get("", {})
    for section in ("dependencies", "devDependencies"):
        if root_package.get(section, {}) != package.get(section, {}):
            failures.append(f"operator-console lock root {section} is stale")
    for location, entry in lock.get("packages", {}).items():
        if not location or "link" in entry or "resolved" not in entry:
            continue
        resolved = entry.get("resolved")
        integrity = entry.get("integrity")
        if not isinstance(resolved, str) or not resolved.startswith("https://"):
            failures.append(f"operator-console lock entry {location} has a non-HTTPS source")
        if not isinstance(integrity, str) or not integrity.startswith("sha512-"):
            failures.append(f"operator-console lock entry {location} lacks SHA-512 integrity")

    node_pin = (app / ".nvmrc").read_text(encoding="utf-8").strip()
    if EXACT_SEMVER.fullmatch(node_pin) is None:
        failures.append("apps/operator-console/.nvmrc must contain an exact Node.js version")
    if node_pin not in package.get("engines", {}).get("node", ""):
        failures.append("operator-console engines.node must include the pinned Node.js version")


def _validate_automation(failures: list[str]) -> None:
    python_pin = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    if EXACT_SEMVER.fullmatch(python_pin) is None:
        failures.append(".python-version must contain an exact Python version")
    for path in sorted((ROOT / ".github/workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "actions/setup-python@" in text and "python-version-file: '.python-version'" not in text:
            failures.append(f"{path.relative_to(ROOT)} must use the repository Python pin")
        if (
            "actions/setup-node@" in text
            and "node-version-file: apps/operator-console/.nvmrc" not in text
        ):
            failures.append(f"{path.relative_to(ROOT)} must use the operator-console Node.js pin")
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("uses:"):
                continue
            target = stripped.removeprefix("uses:").strip()
            if target.startswith("./"):
                continue
            if PINNED_ACTION.fullmatch(target) is None:
                failures.append(
                    f"{path.relative_to(ROOT)}:{line_number}: action must use a 40-character commit"
                )
    dependabot = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"))
    ecosystems = {entry.get("package-ecosystem") for entry in dependabot.get("updates", [])}
    expected = {"pip", "npm", "github-actions", "docker"}
    if ecosystems != expected:
        failures.append("Dependabot must cover pip, npm, github-actions, and docker")


def validate_repository() -> list[str]:
    failures: list[str] = []
    _validate_python_manifest(failures)
    _validate_python_locks(failures)
    _validate_node(failures)
    _validate_automation(failures)
    return failures


def main() -> int:
    failures = validate_repository()
    if failures:
        print("Dependency policy validation failed:", file=sys.stderr)
        print("\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(
        "Dependency policy validated: bounded manifests, integrity locks, pinned runtimes/actions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
