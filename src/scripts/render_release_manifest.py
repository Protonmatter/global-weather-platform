import re
from pathlib import Path

_PLACEHOLDER = "weather-platform-runtime@sha256:" + "0" * 64
_IMAGE_REFERENCE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._/:+-]+@sha256:[a-f0-9]{64}$")


def validate_image_reference(value: str) -> str:
    if not _IMAGE_REFERENCE.fullmatch(value):
        raise ValueError("image reference must use repository@sha256:<64 lowercase hex>")
    if value.endswith("0" * 64):
        raise ValueError("release image reference must not use the source placeholder")
    return value


def render_manifest(source: Path, output: Path, image_reference: str) -> None:
    image = validate_image_reference(image_reference)
    content = source.read_text(encoding="utf-8")
    if content.count(_PLACEHOLDER) != 1:
        raise ValueError("source manifest must contain exactly one image placeholder")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content.replace(_PLACEHOLDER, image), encoding="utf-8")
