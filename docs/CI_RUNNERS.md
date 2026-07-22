# CI runners

GitHub Actions is enabled for this repository. Every workflow targets
**self-hosted** runners, so nothing executes until at least one runner is
registered. This is deliberate: the authoritative gates build and test against
an internal package mirror and registry, not public infrastructure. This
document is the runbook for bringing runners online.

## Workflow to runner mapping

| Workflow | `runs-on` labels | Triggers | Required configuration |
| --- | --- | --- | --- |
| `ci-bootstrap.yml` | `self-hosted, linux` | PR, push to `main` | none — uses public PyPI |
| `pr-fast.yml` | `self-hosted, linux, weather-ci` | PR, push to `main` | `PYPI_MIRROR_URL` variable |
| `spec-validation.yml` | `self-hosted, linux, weather-ci` | PR touching `specs/**`, push to `main` | `PYPI_MIRROR_URL` variable |
| `build-image.yml` | `self-hosted, linux, weather-build` | push to `main`, `v*` tags, manual | `INTERNAL_REGISTRY`, `PYTHON_BASE_IMAGE`, `PYPI_MIRROR_URL` variables; `INTERNAL_RELEASE_ATTEST_COMMAND` in the runner environment; Docker |
| `security-deep.yml` | `self-hosted, linux, weather-security` | weekly schedule, manual | `INTERNAL_SECURITY_SCAN_COMMAND` in the runner environment |

`ci-bootstrap.yml` exists so CI produces a real pass/fail the moment *any* Linux
self-hosted runner registers, before the internal mirror is wired up. It runs
lint, type check, tests (including the real ecCodes GRIB2 decode), and spec
validation against public PyPI. Once `weather-ci` runners with the internal
mirror exist, `pr-fast.yml` is the authoritative pull-request gate and this
bootstrap is redundant; it can be removed then.

A default Linux x64 runner automatically carries the labels `self-hosted`,
`Linux`, and `X64`. Label matching is case-insensitive, so such a runner already
satisfies `ci-bootstrap.yml`. Add `weather-ci` (and, for the release and
security lanes, `weather-build` / `weather-security`) to satisfy the other
workflows.

## Registering a runner

1. Set `PYPI_MIRROR_URL` under **Settings → Actions → Variables** before
   registering a runner with the `weather-ci` label. Otherwise `pr-fast` and
   `spec-validation` will dispatch and fail closed at their mirror checks.
2. Open **Settings → Actions → Runners → New self-hosted runner**. Copy the
   short-lived registration token, the runner version offered to this
   repository, and the SHA-256 for the Linux x64 package. GitHub rolls runner
   releases out progressively, so use the repository setup page rather than
   assuming the newest public release has reached this repository.
3. On a Linux x64 host that has `python3.12` and approved package egress, run as
   a dedicated non-root account:

   ```bash
   RUNNER_URL=https://github.com/Protonmatter/global-weather-platform \
   RUNNER_TOKEN=<registration-token> \
   RUNNER_LABELS=weather-ci \
   RUNNER_VERSION=<version-from-repository-setup-page> \
   RUNNER_SHA256=<official-linux-x64-sha256> \
   RUNNER_AS_SERVICE=true \
   scripts/register_runner.sh
   ```

   `scripts/register_runner.sh` downloads the selected runner release over
   HTTPS, verifies the tarball before extraction, configures it unattended, and
   installs it as a service in the recommended example. It refuses to run as
   root by default and never persists the registration token.

   | Variable | Default | Purpose |
   | --- | --- | --- |
   | `RUNNER_LABELS` | `weather-ci` | comma-separated extra labels |
   | `RUNNER_NAME` | `<hostname>-weather` | runner name shown in Settings |
   | `RUNNER_VERSION` | required | version offered on the repository runner setup page |
   | `RUNNER_SHA256` | required | official SHA-256 for the selected Linux x64 tarball |
   | `RUNNER_DIR` | `$HOME/actions-runner` | install location |
   | `RUNNER_AS_SERVICE` | `false` | install and start as a systemd service when `true` |
   | `RUNNER_ALLOW_RUNASROOT` | unset | permit running as root (discouraged) |

   The service installation invokes `sudo`; give the dedicated account only the
   elevation needed to install and manage this runner service. Do not place the
   registration token in shell history, GitHub comments, workflow logs, or
   tickets.

4. To cover more than one lane on the same host, register with multiple labels,
   e.g. `RUNNER_LABELS=weather-ci,weather-build`. The release lane additionally
   needs Docker and the internal registry variables. Separate runner groups or
   hosts are preferred where release signing and deep security scanning require
   different trust boundaries.

## Repository variables and secrets

Set these under **Settings → Actions → Variables** (they are referenced as
`vars.*`, so none are secrets today):

- `PYPI_MIRROR_URL` — approved internal PyPI mirror. Required by `pr-fast`,
  `spec-validation`, and `build-image`.
- `INTERNAL_REGISTRY` — internal OCI registry host. Required by `build-image`.
- `PYTHON_BASE_IMAGE` — internally mirrored, digest-pinned base image. Required
  by `build-image`.

Two commands are read from the runner's own environment rather than repository
variables, so the runner host controls them:

- `INTERNAL_RELEASE_ATTEST_COMMAND` — artifact policy and signing, run by
  `build-image`. The job fails closed if it is empty.
- `INTERNAL_SECURITY_SCAN_COMMAND` — internal SAST/SCA/container/IaC toolchain,
  run by `security-deep`. The job fails closed if it is empty.

## ecCodes

The GRIB2 decode tests need the ecCodes native library. It does **not** require
a system package: the `eccodes` optional dependency (installed via the
`.[dev,eccodes]` extra that the CI workflows use) bundles the native
`libeccodes` through its `eccodeslib` dependency. A runner only needs
`python3.12`; `pip install` brings the rest.

## Verifying locally

The runner steps are the `make` targets, so a runner reproduces exactly what a
developer runs:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,eccodes]'
PATH="$PWD/.venv/bin:$PATH" make lint typecheck test validate
```
