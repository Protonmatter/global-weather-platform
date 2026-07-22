import json
from pathlib import Path

import pytest

from weather_platform.domain.models import Observation
from weather_platform.ingestion.adapters.json_observation import JsonObservationAdapter
from weather_platform.ingestion.base import ObservationAdapter
from weather_platform.ingestion.pipeline import (
    SourceDecodeError,
    derive_observation_id,
    ingest_source_record,
)
from weather_platform.provenance import sha256_digest
from weather_platform.storage.raw import RawSourceStore

ROOT = Path(__file__).resolve().parents[2]


def load_payload() -> bytes:
    return (ROOT / "testdata/observations/temperature.json").read_bytes()


def test_source_record_is_retained_and_bound_to_observations(tmp_path: Path) -> None:
    raw_store = RawSourceStore(tmp_path / "raw")
    payload = load_payload()
    result = ingest_source_record(payload, adapter=JsonObservationAdapter(), raw_store=raw_store)
    assert result.source_record_digest == sha256_digest(payload)
    assert raw_store.retrieve(result.source_record_digest) == payload
    assert len(result.observations) == 1
    assert result.observations[0].provenance.source_record_digest == result.source_record_digest


def test_observation_id_is_derived_from_source_and_supersedes_payload(tmp_path: Path) -> None:
    payload = load_payload()
    digest = sha256_digest(payload)
    decoder_version = json.loads(payload)["provenance"]["decoder_version"]
    expected = derive_observation_id(digest, decoder_version, 0)

    raw_store = RawSourceStore(tmp_path / "raw")
    result = ingest_source_record(payload, adapter=JsonObservationAdapter(), raw_store=raw_store)
    assert result.observations[0].observation_id == expected
    # The payload's own observation_id is ignored in favor of the derived one.
    assert str(expected) != json.loads(payload)["observation_id"]


def test_redelivery_derives_the_same_id_new_decoder_derives_a_new_id(tmp_path: Path) -> None:
    payload = load_payload()
    digest = sha256_digest(payload)
    first = derive_observation_id(digest, "json-observation-adapter/0.1.0", 0)
    again = derive_observation_id(digest, "json-observation-adapter/0.1.0", 0)
    newer = derive_observation_id(digest, "json-observation-adapter/0.2.0", 0)
    assert first == again
    assert first != newer


def test_client_digest_is_optional_and_superseded(tmp_path: Path) -> None:
    record = json.loads(load_payload())
    del record["provenance"]["source_record_digest"]
    payload = json.dumps(record).encode("utf-8")
    raw_store = RawSourceStore(tmp_path / "raw")
    result = ingest_source_record(payload, adapter=JsonObservationAdapter(), raw_store=raw_store)
    assert result.observations[0].provenance.source_record_digest == sha256_digest(payload)


def test_undecodable_record_is_retained_before_failing(tmp_path: Path) -> None:
    raw_store = RawSourceStore(tmp_path / "raw")
    payload = b"not-a-canonical-observation"
    with pytest.raises(SourceDecodeError, match="could not be decoded") as excinfo:
        ingest_source_record(payload, adapter=JsonObservationAdapter(), raw_store=raw_store)
    assert excinfo.value.digest == sha256_digest(payload)
    assert raw_store.retrieve(excinfo.value.digest) == payload


def test_observation_not_referencing_retained_record_fails(tmp_path: Path) -> None:
    class PassthroughAdapter(ObservationAdapter):
        """Keeps the client-asserted digest instead of stamping the payload digest."""

        def decode(self, payload: bytes) -> list[Observation]:
            return [Observation.model_validate_json(payload)]

    raw_store = RawSourceStore(tmp_path / "raw")
    synthetic_digest = json.loads(load_payload())["provenance"]["source_record_digest"]
    assert synthetic_digest != sha256_digest(load_payload())
    with pytest.raises(ValueError, match="does not reference the retained source record"):
        ingest_source_record(load_payload(), adapter=PassthroughAdapter(), raw_store=raw_store)
