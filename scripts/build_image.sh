#!/usr/bin/env bash
set -euo pipefail

: "${PIP_INDEX_URL:?PIP_INDEX_URL must reference the approved internal package mirror}"
: "${BASE_IMAGE:?BASE_IMAGE must be an internally mirrored digest-pinned image}"
: "${IMAGE:?IMAGE must identify the internal output registry and tag}"

rm -rf .wheelhouse
mkdir -p .wheelhouse
python3.12 -m pip wheel --wheel-dir .wheelhouse .
docker build \
  --network=none \
  --build-arg BASE_IMAGE="$BASE_IMAGE" \
  --tag "$IMAGE" \
  --file deploy/docker/Dockerfile .
