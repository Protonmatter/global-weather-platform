import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from referencing import Registry, Resource

from weather_platform.domain.models import Observation

ROOT = Path(__file__).resolve().parents[2]


def observation_validator() -> Draft202012Validator:
    observation = json.loads(
        (ROOT / "schemas/observations/observation.schema.json").read_text(encoding="utf-8")
    )
    provenance = json.loads(
        (ROOT / "schemas/common/provenance.schema.json").read_text(encoding="utf-8")
    )
    registry = Registry().with_resources(
        [
            ("urn:weather:observation:1", Resource.from_contents(observation)),
            ("urn:weather:provenance:1", Resource.from_contents(provenance)),
        ]
    )
    return Draft202012Validator(
        observation,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def load_record() -> dict[str, object]:
    return json.loads((ROOT / "testdata/observations/temperature.json").read_text(encoding="utf-8"))


def test_testdata_record_conforms_to_json_schema() -> None:
    assert list(observation_validator().iter_errors(load_record())) == []


def test_model_serialization_conforms_to_json_schema() -> None:
    observation = Observation.model_validate(load_record())
    serialized = json.loads(observation.model_dump_json())
    assert list(observation_validator().iter_errors(serialized)) == []


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": "9.9.9"},
        {"vertical_coordinate": {"type": "flight_level", "value": 100.0, "unit": "hft"}},
        {
            "quality_disposition": "accept_with_flags",
            "quality_flags": ["range_suspect", "range_suspect"],
        },
        {"observation_time": "2026-07-20T18:00:00"},
    ],
)
def test_model_and_schema_reject_the_same_records(mutation: dict[str, object]) -> None:
    record = load_record()
    record.update(mutation)
    with pytest.raises(ValidationError):
        Observation.model_validate(record)
    assert list(observation_validator().iter_errors(record)) != []


@pytest.mark.parametrize(
    "provenance_mutation",
    [
        {"source_id": ""},
        {"decoder_version": ""},
        {"source_uri": "not a uri"},
        {"digest_verification": "hearsay"},
    ],
)
def test_model_and_schema_reject_the_same_provenance(provenance_mutation: dict[str, str]) -> None:
    record = load_record()
    provenance = record["provenance"]
    assert isinstance(provenance, dict)
    provenance.update(provenance_mutation)
    with pytest.raises(ValidationError):
        Observation.model_validate(record)
    assert list(observation_validator().iter_errors(record)) != []
