# CI runners

Pull-request quality gates run on isolated GitHub-hosted Linux runners so every
PR receives bounded pass/fail evidence without depending on workstation or
privileged internal infrastructure. Release image construction and deep
security scanning remain on explicitly registered self-hosted runners because
they require internal registries, signing policy, or security tooling.

## Workflow to runner mapping

| Workflow | Runner | Triggers | Required configuration |
| --- | --- | --- | --- |
| `continuous-delivery.yml` | reusable hosted lanes, then `weather-build` | push to `main`, `v*` tags, manual | complete CI must pass for the exact revision before the release job is eligible |
| `continuous-integration.yml` | reusable GitHub-hosted lanes | called by continuous delivery | fans out every specification, dependency, Python, console, contract, scientific, integration, and end-to-end gate |
| `end-to-end.yml` | GitHub-hosted `ubuntu-latest` | relevant PRs, called by continuous integration | built console Worker, production FastAPI subprocess, locked Python/npm graphs |
| `pr-spec-gate.yml` | GitHub-hosted `ubuntu-latest` | PR open, edit, synchronization, reopen | PR body must name the governing specification and normative requirement IDs |
| `ci-bootstrap.yml` | GitHub-hosted `ubuntu-latest` | PR, push to `main` | none; uses locked project requirements from public PyPI |
| `pr-fast.yml` | GitHub-hosted `ubuntu-latest` | PR, push to `main` | none; installs the hash-checked CI lock and the project without dependency resolution |
| `spec-validation.yml` | GitHub-hosted `ubuntu-latest` | PR touching specifications, push to `main` | none |
| `operator-console.yml` | GitHub-hosted `ubuntu-latest` | operator-console PR/push changes | none; uses the committed npm lockfile |
| `build-image.yml` | `self-hosted, linux, weather-build` | reusable call after complete CI | protected `release` environment, internal registry/base-image/mirror variables, release attestation command, Docker |
| `security-deep.yml` | `self-hosted, linux, weather-security` | weekly schedule, manual | internal security command |

The hosted jobs pin checkout and setup actions by commit, select the exact
Python and Node.js patch releases declared in `.python-version` and
`apps/operator-console/.nvmrc`, and use committed dependency constraints. They do
not receive production deployment credentials.

`continuous-delivery.yml` is the only automatic entry into release image
construction. It calls the complete reusable CI fan-out first and calls
`build-image.yml` only after every lane succeeds for the same Git revision.
The build job is also bound to the `release` GitHub environment so repository
environment protection can require approval. The workflow delivers immutable,
scanned, signed, attested evidence; it does not activate the intentionally
scaled-to-zero acquisition workload.

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

- `PYPI_MIRROR_URL`: package-index URL under the approved internal mirror.
- `PYPI_MIRROR_ORIGIN`: exact approved HTTPS origin for
  `PYPI_MIRROR_URL`, without a path, query, fragment, or user information.
- `INTERNAL_REGISTRY`: internal OCI registry host.
- `PYTHON_BASE_IMAGE`: internally mirrored, digest-pinned base image whose
  repository is under `INTERNAL_REGISTRY`.

The image build validates both trust boundaries. It fails with exit code 78 if
the complete normalized base-image reference is outside `INTERNAL_REGISTRY` or
if `PYPI_MIRROR_URL` is outside `PYPI_MIRROR_ORIGIN`.

The runner environment, rather than repository variables, supplies:

- `INTERNAL_RELEASE_ATTEST_COMMAND` for release policy and signing.
- `INTERNAL_SECURITY_SCAN_COMMAND` for the internal security toolchain.

Both privileged jobs fail closed when their required configuration is absent.

## Dependency version handling

- Python manifests use bounded compatibility ranges; `production.lock` and
  `ci.lock` contain the exact SHA-256-checked resolution.
- Operator-console direct dependencies are exact and `package-lock.json`
  preserves registry SHA-512 integrity values.
- `.python-version`, `apps/operator-console/.nvmrc`, and immutable GitHub
  Action commit references pin build runtimes and automation code.
- Dependabot checks pip, npm, GitHub Actions, and Docker weekly. Minor and patch
  changes are grouped by ecosystem; major changes require deliberate spec and
  compatibility work.
- `make dependency-policy` fails on unbounded manifests, stale or unhashed
  locks, non-exact JavaScript dependencies, mutable actions, or missing update
  coverage.

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
PYTHON_BIN="$PWD/../../.venv/bin/python" npm run test:e2e
```
