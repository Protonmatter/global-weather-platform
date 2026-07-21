from pathlib import Path

import pytest

from weather_platform.provenance import sha256_digest
from weather_platform.storage.raw import RawSourceStore


def test_store_and_retrieve_round_trip(tmp_path: Path) -> None:
    store = RawSourceStore(tmp_path / "raw")
    payload = b'{"phenomenon": "air_temperature"}'
    digest = store.store(payload)
    assert digest == sha256_digest(payload)
    assert store.exists(digest)
    assert store.retrieve(digest) == payload


def test_store_is_idempotent_and_write_once(tmp_path: Path) -> None:
    store = RawSourceStore(tmp_path / "raw")
    payload = b"source-record"
    digest = store.store(payload)
    assert store.store(payload) == digest
    assert store.retrieve(digest) == payload


def test_retrieve_unknown_or_invalid_digest_fails(tmp_path: Path) -> None:
    store = RawSourceStore(tmp_path / "raw")
    with pytest.raises(ValueError, match="unknown source record"):
        store.retrieve(f"sha256:{'0' * 64}")
    with pytest.raises(ValueError, match="invalid source record digest"):
        store.retrieve("not-a-digest")
    with pytest.raises(ValueError, match="invalid source record digest"):
        store.exists("sha256:../../../etc/passwd")


def test_retrieve_verifies_integrity(tmp_path: Path) -> None:
    store = RawSourceStore(tmp_path / "raw")
    digest = store.store(b"original")
    record_path = tmp_path / "raw" / digest.removeprefix("sha256:")
    record_path.chmod(0o640)
    record_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        store.retrieve(digest)


def test_store_verifies_existing_record(tmp_path: Path) -> None:
    store = RawSourceStore(tmp_path / "raw")
    digest = store.store(b"original")
    record_path = tmp_path / "raw" / digest.removeprefix("sha256:")
    record_path.chmod(0o640)
    record_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="integrity"):
        store.store(b"original")
