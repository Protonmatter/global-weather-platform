from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from weather_platform.domain.source_manifests import (
    ByteSelection,
    SliceVerification,
    SourceSliceManifest,
    UpstreamObject,
)

NOW = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def manifest(**overrides: object) -> SourceSliceManifest:
    payload: dict[str, object] = {
        "provider": "noaa",
        "dataset": "gfs",
        "product": "0p25",
        "cycle": NOW,
        "forecast_hour": 6,
        "upstream": UpstreamObject(
            bucket="noaa-gfs-bdp-pds",
            key="gfs.20260812/18/atmos/gfs.t18z.pgrb2.0p25.f006",
            etag='"provider-etag"',
            content_length=10_000,
        ),
        "selection": ByteSelection(byte_start=100, byte_end=499),
        "verification": SliceVerification(
            index_digest=DIGEST_A,
            payload_digest=DIGEST_B,
            transport_verified=True,
        ),
        "discovered_at": NOW,
        "download_started_at": NOW + timedelta(seconds=1),
        "received_at": NOW + timedelta(seconds=2),
        "retained_at": NOW + timedelta(seconds=3),
    }
    payload.update(overrides)
    return SourceSliceManifest.model_validate(payload)


def test_manifest_accepts_a_bounded_inclusive_range() -> None:
    item = manifest()
    assert item.selection.length == 400
    assert item.verification.payload_digest == DIGEST_B


def test_byte_selection_rejects_negative_or_reversed_ranges() -> None:
    with pytest.raises(ValidationError):
        ByteSelection(byte_start=-1, byte_end=5)
    with pytest.raises(ValidationError):
        ByteSelection(byte_start=10, byte_end=9)


def test_manifest_rejects_range_beyond_upstream_object() -> None:
    with pytest.raises(ValidationError, match="content length"):
        manifest(selection=ByteSelection(byte_start=9_900, byte_end=10_000))


def test_manifest_rejects_non_sha256_content_identity() -> None:
    with pytest.raises(ValidationError):
        SliceVerification(
            index_digest="etag:abc",
            payload_digest=DIGEST_B,
            transport_verified=True,
        )


def test_manifest_rejects_non_monotonic_acquisition_times() -> None:
    with pytest.raises(ValidationError, match="acquisition timestamps"):
        manifest(received_at=NOW, download_started_at=NOW + timedelta(seconds=1))


def test_provider_etag_is_metadata_not_content_identity() -> None:
    item = manifest()
    assert item.upstream.etag == '"provider-etag"'
    assert item.verification.payload_digest != item.upstream.etag
