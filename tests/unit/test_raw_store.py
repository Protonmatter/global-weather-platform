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


@pytest.mark.parametrize("entry_type", ["symlink", "directory"])
def test_non_regular_digest_entry_fails_closed(tmp_path: Path, entry_type: str) -> None:
    store = RawSourceStore(tmp_path / "raw")
    payload = b"source-record"
    digest = sha256_digest(payload)
    record_path = tmp_path / "raw" / digest.removeprefix("sha256:")
    if entry_type == "symlink":
        target = tmp_path / "attacker-controlled"
        target.write_bytes(payload)
        record_path.symlink_to(target)
    else:
        record_path.mkdir()

    with pytest.raises(ValueError, match="regular file"):
        store.exists(digest)
    with pytest.raises(ValueError, match="regular file"):
        store.retrieve(digest)
    with pytest.raises(ValueError, match="regular file"):
        store.store(payload)


def test_source_record_size_limit_fails_before_retention(tmp_path: Path) -> None:
    store = RawSourceStore(tmp_path / "raw", max_record_bytes=4)

    with pytest.raises(ValueError, match="4-byte retention limit"):
        store.store(b"12345")

    assert list(store.root.iterdir()) == []
    with pytest.raises(ValueError, match="positive"):
        RawSourceStore(tmp_path / "invalid", max_record_bytes=0)


def test_oversized_existing_record_is_rejected_before_read(tmp_path: Path) -> None:
    store = RawSourceStore(tmp_path / "raw", max_record_bytes=4)
    retained_payload = b"1234"
    digest = sha256_digest(retained_payload)
    record_path = store.root / digest.removeprefix("sha256:")
    record_path.write_bytes(b"oversized-local-substitution")

    with pytest.raises(ValueError, match="4-byte retention limit"):
        store.exists(digest)
    with pytest.raises(ValueError, match="4-byte retention limit"):
        store.retrieve(digest)
    with pytest.raises(ValueError, match="4-byte retention limit"):
        store.store(retained_payload)
