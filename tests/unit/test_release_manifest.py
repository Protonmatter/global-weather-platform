from pathlib import Path

import pytest

from weather_platform.release import IMAGE_PLACEHOLDER, render_manifest, validate_image_reference

ROOT = Path(__file__).resolve().parents[2]


def test_image_reference_requires_immutable_digest() -> None:
    valid = "registry.example/weather/platform@sha256:" + "a" * 64
    assert validate_image_reference(valid) == valid
    for invalid in (
        "registry.example/weather/platform:latest",
        "registry.example/weather/platform@sha256:" + "0" * 64,
        "sha256:" + "a" * 64,
        "https://registry.example/weather/platform@sha256:" + "a" * 64,
        "registry.example//weather/platform@sha256:" + "a" * 64,
    ):
        with pytest.raises(ValueError):
            validate_image_reference(invalid)

    with pytest.raises(ValueError, match="expected repository"):
        validate_image_reference(
            valid,
            expected_repository="registry.example/other/platform",
        )


def test_release_renderer_replaces_source_placeholder(tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    output = tmp_path / "rendered.yaml"
    source.write_text(f"image: {IMAGE_PLACEHOLDER}\nreplicas: 0\n", encoding="utf-8")
    image = "registry.example/weather/platform@sha256:" + "b" * 64
    render_manifest(source, output, image)
    rendered = output.read_text(encoding="utf-8")
    assert f"image: {image}" in rendered
    assert IMAGE_PLACEHOLDER not in rendered


def test_checked_manifest_contains_only_release_placeholder() -> None:
    text = (ROOT / "deploy/k8s/weather-acquisition.yaml").read_text(encoding="utf-8")
    assert text.count(IMAGE_PLACEHOLDER) == 1
    assert "global-weather-platform:0.1.0" not in text
