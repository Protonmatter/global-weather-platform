#!/usr/bin/env bash
set -euo pipefail

: "${PIP_INDEX_URL:?PIP_INDEX_URL must reference the approved internal package mirror}"
: "${BASE_IMAGE:?BASE_IMAGE must be an internally mirrored digest-pinned image}"
: "${IMAGE:?IMAGE must identify the internal output registry and tag}"
: "${INTERNAL_REGISTRY:?INTERNAL_REGISTRY must identify the approved internal registry}"

OCI_NAME_COMPONENT='[a-z0-9]+(([._]|__|-+)[a-z0-9]+)*'
REGISTRY_PATTERN="^${OCI_NAME_COMPONENT}(:[0-9]{1,5})?$"
IMAGE_REFERENCE_PATTERN="^(${OCI_NAME_COMPONENT}(:[0-9]{1,5})?)(/${OCI_NAME_COMPONENT})+@sha256:[a-f0-9]{64}$"

[[ "${INTERNAL_REGISTRY}" =~ ${REGISTRY_PATTERN} ]] || {
  echo "INTERNAL_REGISTRY must use a normalized OCI registry name" >&2
  exit 78
}
if [[ "${INTERNAL_REGISTRY}" =~ :([0-9]+)$ ]]; then
  registry_port="${BASH_REMATCH[1]}"
  (( 10#${registry_port} >= 1 && 10#${registry_port} <= 65535 )) || {
    echo "INTERNAL_REGISTRY port must be between 1 and 65535" >&2
    exit 78
  }
fi
[[ "${BASE_IMAGE}" =~ ${IMAGE_REFERENCE_PATTERN} ]] || {
  echo "BASE_IMAGE must use a normalized repository-qualified immutable sha256 reference" >&2
  exit 78
}
[[ "${BASH_REMATCH[1]}" == "${INTERNAL_REGISTRY}" ]] || {
  echo "BASE_IMAGE must use the approved internal registry" >&2
  exit 78
}
test -f requirements/production.lock

BUILD_TMP_ROOT="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
BUILD_TMP_ROOT="$(cd "$BUILD_TMP_ROOT" && pwd -P)"
BUILD_VENV="$(mktemp -d "$BUILD_TMP_ROOT/weather-build-venv.XXXXXX")"
cleanup_build_venv() {
  case "${BUILD_VENV:-}" in
    "$BUILD_TMP_ROOT"/weather-build-venv.*) rm -rf -- "$BUILD_VENV" ;;
    *) echo "refusing to remove unexpected build environment path" >&2 ;;
  esac
}
trap cleanup_build_venv EXIT
python3.12 -m venv "$BUILD_VENV"
BUILD_PYTHON="$BUILD_VENV/bin/python"

rm -rf .wheelhouse
mkdir -p .wheelhouse

"$BUILD_PYTHON" -m pip install \
  --disable-pip-version-check \
  --require-hashes \
  --requirement requirements/production.lock
"$BUILD_PYTHON" -m pip download \
  --disable-pip-version-check \
  --require-hashes \
  --only-binary=:all: \
  --dest .wheelhouse \
  --requirement requirements/production.lock
"$BUILD_PYTHON" -m pip wheel \
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
