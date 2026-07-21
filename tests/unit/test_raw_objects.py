from pathlib import Path

import pytest

from weather_platform.storage.raw_objects import (
    FileSystemRawObjectStore,
    RawObjectCorruptionError,
)


def test_raw_object_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    store = FileSystemRawObjectStore(tmp_path / "raw")
    payload = b"exact source bytes\x00\x01"

    first = store.put(payload)
    second = store.put(payload)

    assert first.digest == FileSystemRawObjectStore.digest(payload)
    assert first.uri == f"cas://sha256/{first.digest.removeprefix('sha256:')}"
    assert first.created is True
    assert second.created is False
    assert second == first.__class__(
        digest=first.digest,
        uri=first.uri,
        size_bytes=len(payload),
        created=False,
    )
    assert store.get(first.digest) == payload
    assert store.contains(first.digest) is True
    assert len(list((tmp_path / "raw" / "sha256").rglob("*"))) == 3


def test_existing_object_is_revalidated_before_reuse(tmp_path: Path) -> None:
    store = FileSystemRawObjectStore(tmp_path / "raw")
    reference = store.put(b"original")
    path = store.path_for_digest(reference.digest)
    path.chmod(0o640)
    path.write_bytes(b"tampered")

    with pytest.raises(RawObjectCorruptionError, match="does not match content address"):
        store.put(b"original")
    with pytest.raises(RawObjectCorruptionError, match="integrity verification"):
        store.get(reference.digest)


def test_symlink_is_never_treated_as_a_raw_object(tmp_path: Path) -> None:
    store = FileSystemRawObjectStore(tmp_path / "raw")
    payload = b"source"
    digest = store.digest(payload)
    target = store.path_for_digest(digest)
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(payload)
    target.symlink_to(outside)

    with pytest.raises(RawObjectCorruptionError, match="not a regular file"):
        store.put(payload)


def test_digest_and_size_validation_fail_closed(tmp_path: Path) -> None:
    store = FileSystemRawObjectStore(tmp_path / "raw", max_object_bytes=3)
    with pytest.raises(ValueError, match="maximum size"):
        store.put(b"four")
    with pytest.raises(ValueError, match="sha256 algorithm"):
        store.get("md5:abcd")
    with pytest.raises(ValueError, match="64 hexadecimal"):
        store.get("sha256:abcd")
    with pytest.raises(ValueError, match="lowercase hexadecimal"):
        store.get("sha256:" + "A" * 64)
