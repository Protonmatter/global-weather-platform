#!/usr/bin/env bash
set -euo pipefail

: "${PIP_INDEX_URL:?PIP_INDEX_URL must reference the approved internal package mirror}"
: "${BASE_IMAGE:?BASE_IMAGE must be an internally mirrored digest-pinned image}"
: "${IMAGE:?IMAGE must identify the internal output registry and tag}"

[[ "${BASE_IMAGE}" =~ @sha256:[a-f0-9]{64}$ ]] || {
  echo "BASE_IMAGE must use an immutable sha256 digest" >&2
  exit 78
}
test -f requirements/production.lock

rm -rf .wheelhouse
mkdir -p .wheelhouse

python3.12 -m pip install \
  --disable-pip-version-check \
  --require-hashes \
  --requirement requirements/production.lock
python3.12 -m pip download \
  --disable-pip-version-check \
  --require-hashes \
  --only-binary=:all: \
  --dest .wheelhouse \
  --requirement requirements/production.lock
python3.12 -m pip wheel \
  --disable-pip-version-check \
  --no-build-isolation \
  --no-deps \
  --wheel-dir .wheelhouse \
  .

docker build \
  --network=none \
  --build-arg BASE_IMAGE="$BASE_IMAGE" \
  --tag "$IMAGE" \
  --file deploy/docker/Dockerfile .
