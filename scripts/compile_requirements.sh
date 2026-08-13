#!/usr/bin/env bash
set -euo pipefail

python_bin="${PYTHON_BIN:-python3.12}"
output_dir="${1:-requirements}"
mkdir -p "${output_dir}"

compile_common=(
  --resolver=backtracking
  --generate-hashes
  --allow-unsafe
  --strip-extras
  --no-header
  --no-emit-index-url
  --no-annotate
)

"${python_bin}" -m piptools compile \
  "${compile_common[@]}" \
  --extra=build \
  --extra=eccodes \
  --output-file "${output_dir}/production.lock" \
  pyproject.toml

"${python_bin}" -m piptools compile \
  "${compile_common[@]}" \
  --extra=build \
  --extra=dev \
  --extra=eccodes \
  --output-file "${output_dir}/ci.lock" \
  pyproject.toml
