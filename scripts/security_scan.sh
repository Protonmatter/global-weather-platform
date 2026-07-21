#!/usr/bin/env bash
set -euo pipefail

required=(ruff mypy pytest)
for command in "${required[@]}"; do
  command -v "$command" >/dev/null || {
    echo "missing internally provisioned security prerequisite: $command" >&2
    exit 2
  }
done

ruff check .
mypy
pytest

# Hooks for internal SAST/SCA/container/IaC scanners. Fail rather than silently
# substituting a public SaaS scanner.
if [[ -n "${INTERNAL_SECURITY_SCAN_COMMAND:-}" ]]; then
  bash -lc "$INTERNAL_SECURITY_SCAN_COMMAND"
else
  echo "INTERNAL_SECURITY_SCAN_COMMAND is not configured" >&2
  exit 3
fi
