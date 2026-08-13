import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from weather_platform.domain.grid_assets import (
    GridFieldAsset,
    GridFieldProvenance,
    LongitudeConvention,
    StorageEncoding,
)
from weather_platform.domain.model_catalog import GuidanceOrigin
from weather_platform.domain.models import QualityDisposition

INIT = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def provenance(**overrides: object) -> GridFieldProvenance:
    payload: dict[str, object] = {
        "source_id": "noaa-gfs",
        "source_record_digest": DIGEST_A,
        "ingested_at": INIT + timedelta(minutes=5),
        "decoder_version": "grib-field-decoder/0.2.0+eccodes/2.38.3",
    }
    payload.update(overrides)
    return GridFieldProvenance.model_validate(payload)


def asset(**overrides: object) -> GridFieldAsset:
    payload: dict[str, object] = {
        "asset_id": uuid4(),
        "model_id": "noaa-gfs",
        "model_version": "v16.3",
        "guidance_origin": GuidanceOrigin.IMPORTED,
        "initialized_at": INIT,
        "valid_at": INIT + timedelta(hours=6),
        "lead_seconds": 6 * 3600,
        "ensemble_member": None,
        "phenomenon": "air_temperature",
        "source_variable": "2t",
        "level_type": "height_above_ground",
        "level_value": 2.0,
        "level_unit": "m",
        "unit": "K",
        "grid_id": "gfs-0p25-global",
        "crs": "OGC:CRS84",
        "nx": 1440,
        "ny": 721,
        "longitude_convention": LongitudeConvention.ZERO_TO_360,
        "storage_encoding": StorageEncoding.ZARR_V3,
        "source_record_digest": DIGEST_A,
        "normalized_digest": DIGEST_B,
        "source_revision": "gfs.20260812/18/f006",
        "decoder_version": "grib-field-decoder/0.2.0+eccodes/2.38.3",
        "quality_disposition": QualityDisposition.ACCEPT,
        "quality_flags": [],
        "provenance": provenance(),
    }
    payload.update(overrides)
    return GridFieldAsset.model_validate(payload)


def test_asset_preserves_model_cycle_and_grid_identity() -> None:
    item = asset(ensemble_member="p03")
    assert item.valid_at == item.initialized_at + timedelta(seconds=item.lead_seconds)
    assert item.ensemble_member == "p03"
    assert item.shape == (721, 1440)


def test_asset_rejects_inconsistent_valid_time() -> None:
    with pytest.raises(ValidationError, match="valid_at"):
        asset(valid_at=INIT + timedelta(hours=7))


def test_asset_rejects_non_positive_grid_dimensions() -> None:
    with pytest.raises(ValidationError):
        asset(nx=0)
    with pytest.raises(ValidationError):
        asset(ny=-1)


def test_asset_requires_level_unit_with_level_value() -> None:
    with pytest.raises(ValidationError, match="level_unit"):
        asset(level_unit=None)


def test_asset_rejects_empty_level_unit() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        asset(level_unit="")


def test_accepted_asset_cannot_carry_unresolved_flags() -> None:
    with pytest.raises(ValidationError, match="quality flags"):
        asset(quality_flags=["range_suspect"])


def test_asset_rejects_empty_quality_flag_identifier() -> None:
    with pytest.raises(ValidationError, match="quality flags must not be empty"):
        asset(
            quality_disposition=QualityDisposition.ACCEPT_WITH_FLAGS,
            quality_flags=[""],
        )


def test_asset_rejects_unknown_storage_encoding_and_bad_digest() -> None:
    with pytest.raises(ValidationError):
        asset(storage_encoding="json-grid")
    with pytest.raises(ValidationError):
        asset(normalized_digest="md5:deadbeef")


def test_asset_rejects_empty_ensemble_member_identifier() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        asset(ensemble_member="")


@pytest.mark.parametrize("level_value", [math.nan, math.inf, -math.inf])
def test_asset_rejects_non_finite_level_value(level_value: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        asset(level_value=level_value)


def test_asset_requires_decoder_version_to_match_provenance() -> None:
    with pytest.raises(ValidationError, match="decoder_version"):
        asset(
            decoder_version="grib-field-decoder/0.3.0+eccodes/2.47.0",
            provenance=provenance(),
        )


def test_asset_and_nested_evidence_are_immutable_after_validation() -> None:
    item = asset()
    assert item.quality_flags == ()

    with pytest.raises(ValidationError, match="frozen"):
        item.valid_at = INIT
    with pytest.raises(ValidationError, match="frozen"):
        item.source_record_digest = DIGEST_B
    with pytest.raises(AttributeError):
        item.quality_flags.append("range_suspect")
    with pytest.raises(ValidationError, match="frozen"):
        item.provenance.decoder_version = "grib-field-decoder/0.3.0+eccodes/2.47.0"
