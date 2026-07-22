#!/usr/bin/env bash
# Register a GitHub Actions self-hosted runner for this repository.
#
# A runner registered here automatically carries the labels self-hosted, linux,
# and X64, so it satisfies ci-bootstrap.yml immediately. Add weather-ci (the
# default below) so it also satisfies pr-fast.yml once the internal mirror var
# is set. See docs/CI_RUNNERS.md.
set -euo pipefail

: "${RUNNER_URL:?set RUNNER_URL to the repository URL, e.g. https://github.com/Protonmatter/global-weather-platform}"
: "${RUNNER_TOKEN:?set RUNNER_TOKEN to a runner registration token (repo Settings > Actions > Runners > New self-hosted runner)}"

RUNNER_LABELS="${RUNNER_LABELS:-weather-ci}"
RUNNER_NAME="${RUNNER_NAME:-$(hostname)-weather}"
RUNNER_VERSION="${RUNNER_VERSION:-2.321.0}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"

if [[ "$(id -u)" == "0" && "${RUNNER_ALLOW_RUNASROOT:-}" != "1" ]]; then
  echo "Refusing to run the runner as root. Use a dedicated user, or set RUNNER_ALLOW_RUNASROOT=1." >&2
  exit 1
fi

command -v python3.12 >/dev/null || \
  echo "warning: python3.12 not found on PATH; ci-bootstrap and pr-fast require it" >&2

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

tarball="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
if [[ ! -f "$tarball" ]]; then
  curl -fsSL -o "$tarball" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${tarball}"
fi
if [[ -n "${RUNNER_SHA256:-}" ]]; then
  echo "${RUNNER_SHA256}  ${tarball}" | sha256sum -c -
else
  echo "note: set RUNNER_SHA256 to verify the runner tarball checksum" >&2
fi
tar xzf "$tarball"

./config.sh --unattended --replace \
  --url "$RUNNER_URL" \
  --token "$RUNNER_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS"

if [[ "${RUNNER_AS_SERVICE:-false}" == "true" ]]; then
  sudo ./svc.sh install
  sudo ./svc.sh start
  echo "Runner ${RUNNER_NAME} installed as a service with labels: ${RUNNER_LABELS}"
else
  echo "Starting runner ${RUNNER_NAME} (labels: ${RUNNER_LABELS}). Ctrl-C to stop."
  ./run.sh
fi
