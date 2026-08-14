# CI runners

Pull-request quality gates run on isolated GitHub-hosted Linux runners so every
PR receives bounded pass/fail evidence without depending on workstation or
privileged internal infrastructure. Release image construction and deep
security scanning remain on explicitly registered self-hosted runners because
they require internal registries, signing policy, or security tooling.

## Workflow to runner mapping

| Workflow | Runner | Triggers | Required configuration |
| --- | --- | --- | --- |
| `ci-bootstrap.yml` | GitHub-hosted `ubuntu-latest` | PR, push to `main` | none; uses locked project requirements from public PyPI |
| `pr-fast.yml` | GitHub-hosted `ubuntu-latest` | PR, push to `main` | none; installs the hash-checked CI lock and the project without dependency resolution |
| `spec-validation.yml` | GitHub-hosted `ubuntu-latest` | PR touching specifications, push to `main` | none |
| `operator-console.yml` | GitHub-hosted `ubuntu-latest` | operator-console PR/push changes | none; uses the committed npm lockfile |
| `build-image.yml` | `self-hosted, linux, weather-build` | push to `main`, `v*` tags, manual | internal registry/base-image/mirror variables, release attestation command, Docker |
| `security-deep.yml` | `self-hosted, linux, weather-security` | weekly schedule, manual | internal security command |

The hosted jobs pin checkout and setup actions by commit, select Python 3.12 or
Node.js 22.13.1 explicitly, and use committed dependency constraints. They do
not receive production deployment credentials.

## Registering privileged runners

1. Open **Settings → Actions → Runners → New self-hosted runner**. Copy the
   short-lived registration token, offered runner version, and official SHA-256
   for the Linux x64 package.
2. On an approved Linux x64 host, run as a dedicated non-root account:

   ```bash
   RUNNER_URL=https://github.com/Protonmatter/global-weather-platform \
   RUNNER_TOKEN=<registration-token> \
   RUNNER_LABELS=weather-build \
   RUNNER_VERSION=<version-from-repository-setup-page> \
   RUNNER_SHA256=<official-linux-x64-sha256> \
   RUNNER_AS_SERVICE=true \
   scripts/register_runner.sh
   ```

   Register the security lane separately with
   `RUNNER_LABELS=weather-security`. Separate runner groups or hosts are
   preferred because release signing and security scanning have different
   trust boundaries.

3. The helper downloads into a temporary file, verifies the supplied digest,
   atomically extracts the runner, configures it unattended, and never persists
   the registration token. Do not place the token in shell history, workflow
   logs, comments, or tickets.

## Privileged workflow configuration

Set these repository variables for `build-image.yml`:

- `PYPI_MIRROR_URL`: approved internal Python mirror.
- `INTERNAL_REGISTRY`: internal OCI registry host.
- `PYTHON_BASE_IMAGE`: internally mirrored, digest-pinned base image.

The runner environment, rather than repository variables, supplies:

- `INTERNAL_RELEASE_ATTEST_COMMAND` for release policy and signing.
- `INTERNAL_SECURITY_SCAN_COMMAND` for the internal security toolchain.

Both privileged jobs fail closed when their required configuration is absent.

## Verifying locally

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/ci.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
PATH="$PWD/.venv/bin:$PATH" make lint typecheck test validate

cd apps/operator-console
npm ci
npm run lint
npm run typecheck
npm test
```
