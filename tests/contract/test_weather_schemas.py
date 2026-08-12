import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from weather_platform.domain.grid_assets import GridFieldAsset
from weather_platform.domain.source_manifests import SourceSliceManifest

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


def schema(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def validator(path: str) -> Draft202012Validator:
    target = schema(path)
    provenance = schema("schemas/common/provenance.schema.json")
    registry = Registry().with_resources(
        [("urn:weather:provenance:1", Resource.from_contents(provenance))]
    )
    return Draft202012Validator(
        target,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def source_record() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "provider": "noaa",
        "dataset": "gfs",
        "product": "0p25",
        "cycle": NOW.isoformat().replace("+00:00", "Z"),
        "forecast_hour": 6,
        "upstream": {
            "bucket": "noaa-gfs-bdp-pds",
            "key": "gfs.20260812/18/atmos/gfs.t18z.pgrb2.0p25.f006",
            "etag": "provider-etag",
            "content_length": 1000,
        },
        "selection": {"byte_start": 100, "byte_end": 299},
        "verification": {
            "index_digest": DIGEST_A,
            "payload_digest": DIGEST_B,
            "transport_verified": True,
        },
        "discovered_at": NOW.isoformat().replace("+00:00", "Z"),
        "download_started_at": (NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
        "received_at": (NOW + timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
        "retained_at": (NOW + timedelta(seconds=3)).isoformat().replace("+00:00", "Z"),
    }


def grid_record() -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "asset_id": str(uuid4()),
        "model_id": "noaa-gfs",
        "model_version": "v16.3",
        "guidance_origin": "imported",
        "initialized_at": NOW.isoformat().replace("+00:00", "Z"),
        "valid_at": (NOW + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
        "lead_seconds": 21600,
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
        "longitude_convention": "0_360",
        "storage_encoding": "zarr-v3",
        "source_record_digest": DIGEST_A,
        "normalized_digest": DIGEST_B,
        "source_revision": "gfs.20260812/18/f006",
        "decoder_version": "grib-field-decoder/0.2.0+eccodes/2.38.3",
        "quality_disposition": "accept",
        "quality_flags": [],
        "provenance": {
            "source_id": "noaa-gfs",
            "source_record_digest": DIGEST_A,
            "digest_verification": "platform",
            "ingested_at": (NOW + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
            "decoder_version": "grib-field-decoder/0.2.0+eccodes/2.38.3",
        },
    }


def test_source_slice_model_and_schema_accept_the_same_record() -> None:
    record = source_record()
    model = SourceSliceManifest.model_validate(record)
    serialized = json.loads(model.model_dump_json())
    assert list(validator("schemas/manifests/source-slice.schema.json").iter_errors(serialized)) == []


def test_grid_asset_model_and_schema_accept_the_same_record() -> None:
    record = grid_record()
    model = GridFieldAsset.model_validate(record)
    serialized = json.loads(model.model_dump_json())
    assert list(validator("schemas/grids/grid-field-asset.schema.json").iter_errors(serialized)) == []


def test_schemas_reject_out_of_bounds_range_and_time_mismatch() -> None:
    source = source_record()
    source["selection"] = {"byte_start": 900, "byte_end": 1000}
    assert list(validator("schemas/manifests/source-slice.schema.json").iter_errors(source))

    grid = grid_record()
    grid["valid_at"] = (NOW + timedelta(hours=7)).isoformat().replace("+00:00", "Z")
    assert list(validator("schemas/grids/grid-field-asset.schema.json").iter_errors(grid))
