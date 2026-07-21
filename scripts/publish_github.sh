#!/usr/bin/env bash
set -euo pipefail

OWNER="${GITHUB_OWNER:-Protonmatter}"
REPO="${GITHUB_REPOSITORY_NAME:-global-weather-platform}"
VISIBILITY="${GITHUB_VISIBILITY:-private}"
DESCRIPTION="${GITHUB_REPOSITORY_DESCRIPTION:-Spec-driven global probabilistic Earth-system forecasting platform}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required: https://cli.github.com/" >&2
  exit 127
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Authenticate first with: gh auth login" >&2
  exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Run this script from inside the repository." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Refusing to publish a dirty working tree." >&2
  git status --short >&2
  exit 1
fi

if gh repo view "${OWNER}/${REPO}" >/dev/null 2>&1; then
  echo "Repository ${OWNER}/${REPO} already exists; configuring origin and pushing main."
  git remote remove origin >/dev/null 2>&1 || true
  git remote add origin "https://github.com/${OWNER}/${REPO}.git"
  git push -u origin main
else
  gh repo create "${OWNER}/${REPO}" \
    "--${VISIBILITY}" \
    --description "${DESCRIPTION}" \
    --source . \
    --remote origin \
    --push
fi

echo "Published: https://github.com/${OWNER}/${REPO}"
