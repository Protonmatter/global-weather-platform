import argparse
import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path

IMAGE_PLACEHOLDER = "weather-platform-runtime@sha256:" + "0" * 64
_IMAGE_REFERENCE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/:+-]*@sha256:[a-f0-9]{64}$")
_GIT_SHA = re.compile(r"^[a-f0-9]{40}$")


def validate_image_reference(value: str) -> str:
    """Require a repository-qualified, immutable OCI image reference."""

    if not _IMAGE_REFERENCE.fullmatch(value):
        raise ValueError("image reference must use repository@sha256:<64 lowercase hex>")
    if value.endswith("0" * 64):
        raise ValueError("release image reference must not use the source placeholder")
    return value


def render_manifest(source: Path, output: Path, image_reference: str) -> None:
    """Replace the single source placeholder with an attested image digest."""

    image = validate_image_reference(image_reference)
    content = source.read_text(encoding="utf-8")
    if content.count(IMAGE_PLACEHOLDER) != 1:
        raise ValueError("source manifest must contain exactly one image placeholder")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content.replace(IMAGE_PLACEHOLDER, image), encoding="utf-8")


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
) -> None:
    """Bind the source revision, image, dependency locks, and deployment artifact."""

    if not _GIT_SHA.fullmatch(git_sha):
        raise ValueError("git SHA must contain 40 lowercase hexadecimal characters")
    image = validate_image_reference(image_reference)
    artifacts = {
        "deployment_manifest": manifest,
        "production_lock": production_lock,
        "ci_lock": ci_lock,
    }
    for label, path in artifacts.items():
        if not path.is_file():
            raise ValueError(f"{label} does not identify a regular file")

    document = {
        "schema_version": "1.0.0",
        "git_sha": git_sha,
        "image_reference": image,
        "artifacts": {
            label: {"path": str(path), "digest": file_digest(path)}
            for label, path in artifacts.items()
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render immutable weather release evidence")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image-reference-file", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--production-lock", type=Path, required=True)
    parser.add_argument("--ci-lock", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    image_reference = args.image_reference_file.read_text(encoding="utf-8").strip()
    render_manifest(args.source, args.output, image_reference)
    write_release_metadata(
        args.metadata,
        git_sha=args.git_sha,
        image_reference=image_reference,
        manifest=args.output,
        production_lock=args.production_lock,
        ci_lock=args.ci_lock,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
