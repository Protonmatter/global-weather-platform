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
: "${RUNNER_VERSION:?set RUNNER_VERSION to the version shown by the repository runner setup page}"
: "${RUNNER_SHA256:?set RUNNER_SHA256 to the official SHA-256 shown for that runner package}"

EXPECTED_RUNNER_URL="https://github.com/Protonmatter/global-weather-platform"
if [[ "${RUNNER_URL%/}" != "$EXPECTED_RUNNER_URL" ]]; then
  echo "RUNNER_URL must be ${EXPECTED_RUNNER_URL}." >&2
  exit 1
fi
RUNNER_URL="$EXPECTED_RUNNER_URL"

if [[ ! "$RUNNER_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "RUNNER_VERSION must be a semantic version without a leading v (for example, 2.334.0)." >&2
  exit 1
fi
if [[ ! "$RUNNER_SHA256" =~ ^[[:xdigit:]]{64}$ ]]; then
  echo "RUNNER_SHA256 must be exactly 64 hexadecimal characters." >&2
  exit 1
fi

RUNNER_LABELS="${RUNNER_LABELS:-weather-ci}"
RUNNER_NAME="${RUNNER_NAME:-$(hostname)-weather}"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
RUNNER_AS_SERVICE="${RUNNER_AS_SERVICE:-false}"

if [[ "$RUNNER_AS_SERVICE" != "true" && "$RUNNER_AS_SERVICE" != "false" ]]; then
  echo "RUNNER_AS_SERVICE must be true or false." >&2
  exit 1
fi

if [[ "$(id -u)" == "0" && "${RUNNER_ALLOW_RUNASROOT:-}" != "1" ]]; then
  echo "Refusing to run the runner as root. Use a dedicated user, or set RUNNER_ALLOW_RUNASROOT=1." >&2
  exit 1
fi

command -v python3.12 >/dev/null || {
  echo "python3.12 is required by ci-bootstrap and pr-fast" >&2
  exit 1
}
python3.12 -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' || {
  echo "python3.12 must resolve to Python 3.12" >&2
  exit 1
}
for required_command in curl sha256sum tar; do
  command -v "$required_command" >/dev/null || {
    echo "$required_command is required to install the runner" >&2
    exit 1
  }
done
if [[ "$RUNNER_AS_SERVICE" == "true" ]]; then
  command -v sudo >/dev/null || {
    echo "sudo is required when RUNNER_AS_SERVICE=true" >&2
    exit 1
  }
fi

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

tarball="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"
if [[ ! -f "$tarball" ]]; then
  curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
    --output "$tarball" \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${tarball}"
fi
printf '%s  %s\n' "$RUNNER_SHA256" "$tarball" | sha256sum -c -
tar xzf "$tarball"

./config.sh --unattended --replace \
  --url "$RUNNER_URL" \
  --token "$RUNNER_TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS"

if [[ "$RUNNER_AS_SERVICE" == "true" ]]; then
  sudo ./svc.sh install
  sudo ./svc.sh start
  echo "Runner ${RUNNER_NAME} installed as a service with labels: ${RUNNER_LABELS}"
else
  echo "Starting runner ${RUNNER_NAME} (labels: ${RUNNER_LABELS}). Ctrl-C to stop."
  ./run.sh
fi
