import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from weather_platform.domain.models import Observation
from weather_platform.provenance import sha256_digest

ROOT = Path(__file__).resolve().parents[2]


def load_observation() -> dict[str, object]:
    return json.loads((ROOT / "testdata/observations/temperature.json").read_text())


def test_observation_accepts_valid_record() -> None:
    observation = Observation.model_validate(load_observation())
    assert observation.phenomenon == "air_temperature"
    assert observation.geometry.coordinates[:2] == (-74.006, 40.7128)


def test_observation_rejects_latitude_outside_range() -> None:
    record = load_observation()
    record["geometry"] = {"type": "Point", "coordinates": [-74.0, 95.0]}
    with pytest.raises(ValidationError):
        Observation.model_validate(record)


def test_accept_disposition_cannot_have_flags() -> None:
    record = load_observation()
    record["quality_flags"] = ["range_suspect"]
    with pytest.raises(ValidationError):
        Observation.model_validate(record)


def test_sha256_digest_is_content_addressed() -> None:
    assert sha256_digest(b"weather") == (
        "sha256:e5e72beb4e3c6926d3dc9e3e2ef7833ba50cd919c2460a782b244fd071e920de"
    )


def test_provenance_requires_content_addressed_source_uri() -> None:
    record = load_observation()
    record["provenance"]["source_object_uri"] = "https://example.com/raw"
    with pytest.raises(ValidationError):
        Observation.model_validate(record)
