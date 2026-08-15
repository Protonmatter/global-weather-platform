import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path

_PLACEHOLDER = "weather-platform-runtime@sha256:" + "0" * 64
_NAME_COMPONENT = r"[a-z0-9]+(?:(?:[._]|__|-+)[a-z0-9]+)*"
_REPOSITORY = re.compile(
    rf"^(?P<name>{_NAME_COMPONENT})(?::(?P<port>[0-9]{{1,5}}))?(?:/{_NAME_COMPONENT})*$"
)
_IMAGE_REFERENCE = re.compile(
    rf"^(?P<repository>{_NAME_COMPONENT}(?::[0-9]{{1,5}})?(?:/{_NAME_COMPONENT})*)"
    r"@sha256:(?P<digest>[a-f0-9]{64})$"
)
_GIT_SHA = re.compile(r"^[a-f0-9]{40}$")


def _validate_repository(value: str) -> str:
    match = _REPOSITORY.fullmatch(value)
    if match is None or len(value) > 255:
        raise ValueError("image repository must use a normalized OCI repository name")
    port = match.group("port")
    if port is not None and not 1 <= int(port) <= 65535:
        raise ValueError("image repository port must be between 1 and 65535")
    return value


def validate_image_reference(
    value: str,
    *,
    expected_repository: str | None = None,
) -> str:
    match = _IMAGE_REFERENCE.fullmatch(value)
    if match is None:
        raise ValueError("image reference must use repository@sha256:<64 lowercase hex>")
    repository = _validate_repository(match.group("repository"))
    if match.group("digest") == "0" * 64:
        raise ValueError("release image reference must not use the source placeholder")
    if expected_repository is not None:
        expected = _validate_repository(expected_repository)
        if repository != expected:
            raise ValueError("image reference does not match the expected repository")
    return value


def render_manifest(
    source: Path,
    output: Path,
    image_reference: str,
    *,
    expected_repository: str | None = None,
) -> None:
    image = validate_image_reference(
        image_reference,
        expected_repository=expected_repository,
    )
    content = source.read_text(encoding="utf-8")
    if content.count(_PLACEHOLDER) != 1:
        raise ValueError("source manifest must contain exactly one image placeholder")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content.replace(_PLACEHOLDER, image), encoding="utf-8")


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def write_release_metadata(
    output: Path,
    *,
    git_sha: str,
    image_reference: str,
    manifest: Path,
    production_lock: Path,
    ci_lock: Path,
    expected_repository: str | None = None,
) -> None:
    if not _GIT_SHA.fullmatch(git_sha):
        raise ValueError("git SHA must contain 40 lowercase hexadecimal characters")
    image = validate_image_reference(
        image_reference,
        expected_repository=expected_repository,
    )
    files = {
        "deployment_manifest": manifest,
        "production_lock": production_lock,
        "ci_lock": ci_lock,
    }
    for label, path in files.items():
        if not path.is_file():
            raise ValueError(f"{label} does not identify a regular file")

    document = {
        "schema_version": "1.0.0",
        "git_sha": git_sha,
        "image_reference": image,
        "artifacts": {
            label: {
                "path": str(path),
                "digest": file_digest(path),
            }
            for label, path in files.items()
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render immutable weather release evidence")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-reference-file", type=Path, required=True)
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--production-lock", type=Path, required=True)
    parser.add_argument("--ci-lock", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    image_reference = args.image_reference_file.read_text(encoding="utf-8").strip()
    render_manifest(
        args.source,
        args.output,
        image_reference,
        expected_repository=args.expected_repository,
    )
    write_release_metadata(
        args.metadata,
        git_sha=args.git_sha,
        image_reference=image_reference,
        manifest=args.output,
        production_lock=args.production_lock,
        ci_lock=args.ci_lock,
        expected_repository=args.expected_repository,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
