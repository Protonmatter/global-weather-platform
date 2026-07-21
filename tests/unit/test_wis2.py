import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from weather_platform.api import main
from weather_platform.ingestion.adapters.json_observation import JsonObservationAdapter
from weather_platform.ingestion.wis2 import (
    Wis2IntegrityError,
    Wis2NotificationConsumer,
    Wis2NotificationError,
    validate_wis2_topic,
)
from weather_platform.provenance import sha256_digest
from weather_platform.storage.jsonl import JsonlObservationStore
from weather_platform.storage.raw import RawSourceStore

ROOT = Path(__file__).resolve().parents[2]
TOPIC = "origin/a/wis2/de-dwd/data/core/weather/surface-based-observations/synop"
DATA_URL = "https://gts.example/data/temperature.json"
RECEIVED_AT = datetime(2026, 7, 20, 18, 0, 41, tzinfo=UTC)


def load_payload() -> bytes:
    return (ROOT / "testdata/observations/temperature.json").read_bytes()


def notification_for(payload: bytes, *, integrity: bool = True, method: str = "sha256") -> bytes:
    message = {
        "id": "8bb4b78d-4b21-4a71-9d99-6dd2f6b2c0a4",
        "conformsTo": ["http://wis.wmo.int/spec/wnm/1/conf/core"],
        "type": "Feature",
        "geometry": None,
        "properties": {
            "data_id": "wis2/de-dwd/data/core/synop/temperature",
            "pubtime": "2026-07-20T18:00:30Z",
            "datetime": "2026-07-20T18:00:00Z",
        },
        "links": [{"href": DATA_URL, "rel": "canonical", "type": "application/json"}],
    }
    if integrity:
        digest = hashlib.new(method.replace("-", "_"), payload).digest()
        message["properties"]["integrity"] = {
            "method": method,
            "value": base64.b64encode(digest).decode("ascii"),
        }
    return json.dumps(message).encode("utf-8")


def consumer_for(tmp_path: Path, payload: bytes) -> Wis2NotificationConsumer:
    return Wis2NotificationConsumer(
        adapter=JsonObservationAdapter(),
        raw_store=RawSourceStore(tmp_path / "raw"),
        fetch={DATA_URL: payload}.__getitem__,
    )


def test_topic_validation() -> None:
    validate_wis2_topic(TOPIC)
    validate_wis2_topic("cache/a/wis2/int-wmo-test/data/core/synop")
    validate_wis2_topic("origin/a/wis2/de-dwd/data/recommended/weather/synop")
    for topic in (
        "origin/a/wis3/x/data/core/synop",
        "random/topic",
        "origin/a/wis2/de-dwd",
        "origin/a/wis2/de-dwd/foo",
        "origin/a/wis2/de-dwd/data/private/weather",
        "origin/a/wis2/de-dwd/metadata/core/discovery",
        "origin/a/wis2/de-dwd/data/core",
    ):
        with pytest.raises(ValueError, match="WIS2"):
            validate_wis2_topic(topic)


def test_notification_round_trip_binds_distinct_times(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    result = consumer.process(TOPIC, notification_for(payload), RECEIVED_AT)

    assert result.source_record_digest == sha256_digest(payload)
    assert result.upstream_integrity_verified is True
    raw_store = RawSourceStore(tmp_path / "raw")
    assert raw_store.retrieve(result.notification_digest) == notification_for(payload)
    assert raw_store.retrieve(result.source_record_digest) == payload

    observation = result.observations[0]
    provenance = observation.provenance
    assert provenance.source_id == "wis2/de-dwd/data/core/synop/temperature"
    assert str(provenance.source_uri) == DATA_URL
    assert provenance.source_record_digest == result.source_record_digest
    assert provenance.source_published_at == result.published_at
    assert provenance.received_at == RECEIVED_AT
    times = {provenance.source_published_at, provenance.received_at, provenance.ingested_at}
    assert len(times) == 3
    assert provenance.digest_verification.value == "upstream"


def test_integrity_mismatch_fails_closed_but_retains_evidence(tmp_path: Path) -> None:
    payload = load_payload()
    notification = notification_for(b"different-bytes-than-fetched")
    consumer = consumer_for(tmp_path, payload)
    with pytest.raises(Wis2IntegrityError) as excinfo:
        consumer.process(TOPIC, notification, RECEIVED_AT)
    assert RawSourceStore(tmp_path / "raw").retrieve(excinfo.value.source_record_digest) == payload


def test_sha3_integrity_methods_are_accepted(tmp_path: Path) -> None:
    payload = load_payload()
    for method in ("sha3-256", "sha3-384", "sha3-512", "sha384", "sha512"):
        consumer = consumer_for(tmp_path / method.replace("-", "_"), payload)
        result = consumer.process(TOPIC, notification_for(payload, method=method), RECEIVED_AT)
        assert result.upstream_integrity_verified is True


def test_non_https_canonical_link_is_rejected(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    message = json.loads(notification_for(payload))
    message["links"] = [{"href": "http://gts.example/data/temperature.json", "rel": "canonical"}]
    with pytest.raises(Wis2NotificationError):
        consumer.process(TOPIC, json.dumps(message).encode("utf-8"), RECEIVED_AT)


def test_non_canonical_links_may_use_other_schemes(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    message = json.loads(notification_for(payload))
    message["links"].append({"href": "http://mirror.example/alt", "rel": "via"})
    result = consumer.process(TOPIC, json.dumps(message).encode("utf-8"), RECEIVED_AT)
    assert result.observations


def test_missing_integrity_is_recorded_as_unverified(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    result = consumer.process(TOPIC, notification_for(payload, integrity=False), RECEIVED_AT)
    assert result.upstream_integrity_verified is False
    assert result.observations[0].provenance.digest_verification.value == "platform"


def test_notification_without_wnm_envelope_is_rejected(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)

    missing_marker = json.loads(notification_for(payload))
    del missing_marker["conformsTo"]
    missing_geometry = json.loads(notification_for(payload))
    del missing_geometry["geometry"]
    wrong_marker = json.loads(notification_for(payload))
    wrong_marker["conformsTo"] = ["not-wnm"]
    both_markers = json.loads(notification_for(payload))
    both_markers["version"] = "v04"
    missing_temporal = json.loads(notification_for(payload))
    del missing_temporal["properties"]["datetime"]
    empty_geometry = json.loads(notification_for(payload))
    empty_geometry["geometry"] = {}
    wrong_geometry = json.loads(notification_for(payload))
    wrong_geometry["geometry"] = {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}
    non_numeric_point = json.loads(notification_for(payload))
    non_numeric_point["geometry"] = {"type": "Point", "coordinates": ["x"]}
    short_polygon_ring = json.loads(notification_for(payload))
    short_polygon_ring["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [0, 0]]],
    }
    unclosed_polygon_ring = json.loads(notification_for(payload))
    unclosed_polygon_ring["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
    }
    start_only_interval = json.loads(notification_for(payload))
    del start_only_interval["properties"]["datetime"]
    start_only_interval["properties"]["start_datetime"] = "2026-07-20T17:00:00Z"

    for message in (
        missing_marker,
        missing_geometry,
        wrong_marker,
        both_markers,
        missing_temporal,
        empty_geometry,
        wrong_geometry,
        non_numeric_point,
        short_polygon_ring,
        unclosed_polygon_ring,
        start_only_interval,
    ):
        with pytest.raises(Wis2NotificationError):
            consumer.process(TOPIC, json.dumps(message).encode("utf-8"), RECEIVED_AT)


def test_legacy_version_and_point_geometry_are_accepted(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    message = json.loads(notification_for(payload))
    del message["conformsTo"]
    message["version"] = "v04"
    message["geometry"] = {"type": "Point", "coordinates": [-74.006, 40.7128]}
    result = consumer.process(TOPIC, json.dumps(message).encode("utf-8"), RECEIVED_AT)
    assert result.observations


def test_closed_polygon_geometry_is_accepted(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    message = json.loads(notification_for(payload))
    message["geometry"] = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
    }
    result = consumer.process(TOPIC, json.dumps(message).encode("utf-8"), RECEIVED_AT)
    assert result.observations


def test_interval_temporal_description_is_accepted(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    message = json.loads(notification_for(payload))
    del message["properties"]["datetime"]
    message["properties"]["start_datetime"] = "2026-07-20T17:00:00Z"
    message["properties"]["end_datetime"] = "2026-07-20T18:00:00Z"
    result = consumer.process(TOPIC, json.dumps(message).encode("utf-8"), RECEIVED_AT)
    assert result.observations


def test_canonical_link_with_credentials_is_rejected(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    message = json.loads(notification_for(payload))
    message["links"] = [
        {"href": "https://user:secret@gts.example/data/temperature.json", "rel": "canonical"}
    ]
    with pytest.raises(Wis2NotificationError):
        consumer.process(TOPIC, json.dumps(message).encode("utf-8"), RECEIVED_AT)


def test_malformed_notification_is_retained_before_failing(tmp_path: Path) -> None:
    consumer = consumer_for(tmp_path, load_payload())
    with pytest.raises(Wis2NotificationError) as excinfo:
        consumer.process(TOPIC, b"not-a-notification", RECEIVED_AT)
    digest = excinfo.value.notification_digest
    assert RawSourceStore(tmp_path / "raw").retrieve(digest) == b"not-a-notification"


def test_notification_without_exactly_one_canonical_link_is_rejected(tmp_path: Path) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    for links in (
        [{"href": DATA_URL, "rel": "via"}],
        [
            {"href": DATA_URL, "rel": "canonical"},
            {"href": "https://mirror.example/other", "rel": "canonical"},
        ],
    ):
        message = json.loads(notification_for(payload))
        message["links"] = links
        with pytest.raises(Wis2NotificationError):
            consumer.process(TOPIC, json.dumps(message).encode("utf-8"), RECEIVED_AT)


def test_invalid_topic_never_fetches(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fetch(url: str) -> bytes:
        fetched.append(url)
        return b""

    consumer = Wis2NotificationConsumer(
        adapter=JsonObservationAdapter(),
        raw_store=RawSourceStore(tmp_path / "raw"),
        fetch=fetch,
    )
    with pytest.raises(ValueError, match="WIS2"):
        consumer.process("random/topic", notification_for(b""), RECEIVED_AT)
    assert fetched == []


def test_redelivery_does_not_duplicate_canonical_observations(tmp_path: Path, monkeypatch) -> None:
    payload = load_payload()
    consumer = consumer_for(tmp_path, payload)
    monkeypatch.setattr(main, "store", JsonlObservationStore(tmp_path / "observations.jsonl"))

    first = consumer.process(TOPIC, notification_for(payload), RECEIVED_AT)
    later = datetime(2026, 7, 20, 18, 5, 0, tzinfo=UTC)
    second = consumer.process(TOPIC, notification_for(payload), later)
    assert second.source_record_digest == first.source_record_digest
    main._admit_observations(first.observations)
    main._admit_observations(second.observations)
    stored = main.store.list()
    assert len(stored) == 1
    assert stored[0].provenance.received_at == RECEIVED_AT
