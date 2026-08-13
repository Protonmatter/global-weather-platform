from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from weather_platform.acquisition.noaa.gfs import (
    GFS_COMPLETE_FIELDS,
    GFS_INDEX_REQUIREMENTS,
    GFS_MINIMUM_FIELDS,
)
from weather_platform.acquisition.noaa.grib_index import parse_grib_index, select_grib_messages
from weather_platform.domain.cycle_lifecycle import (
    CycleFieldArrival,
    CycleProductScope,
    CycleState,
    evaluate_cycle,
)
from weather_platform.domain.grid_assets import GridFieldAsset, GridFieldProvenance
from weather_platform.domain.model_catalog import GuidanceOrigin
from weather_platform.domain.models import QualityDisposition
from weather_platform.domain.source_manifests import (
    ByteSelection,
    SourceSliceManifest,
    UpstreamObject,
)
from weather_platform.serving.vector_tiles import decode_vector_tile, encode_vector_tile

INIT = datetime(2026, 8, 12, 18, 0, tzinfo=UTC)
DIGEST_C = "sha256:" + "c" * 64

INDEX = """1:0:d=2026081218:UGRD:10 m above ground:6 hour fcst:
2:100:d=2026081218:VGRD:10 m above ground:6 hour fcst:
3:200:d=2026081218:TMP:2 m above ground:6 hour fcst:
4:300:d=2026081218:RH:2 m above ground:6 hour fcst:
5:400:d=2026081218:PRMSL:mean sea level:6 hour fcst:
6:500:d=2026081218:GUST:surface:6 hour fcst:
7:600:d=2026081218:TCDC:entire atmosphere:6 hour fcst:
8:700:d=2026081218:APCP:surface:0-6 hour acc fcst:
"""


@pytest.mark.integration
def test_index_to_manifest_cycle_asset_and_vector_tile_path() -> None:
    entries = parse_grib_index(INDEX, object_size=800)
    selected = select_grib_messages(entries, GFS_INDEX_REQUIREMENTS)
    assert {item.name for item in selected} == GFS_COMPLETE_FIELDS

    u_message = selected[0]
    selection = ByteSelection(
        byte_start=u_message.byte_start,
        byte_end=u_message.byte_end,
    )
    source = SourceSliceManifest.from_retained_bytes(
        provider="noaa",
        dataset="gfs",
        product="0p25",
        cycle=INIT,
        forecast_hour=6,
        upstream=UpstreamObject(
            bucket="noaa-gfs-bdp-pds",
            key="gfs.20260812/18/atmos/gfs.t18z.pgrb2.0p25.f006",
            content_length=800,
        ),
        selection=selection,
        index_bytes=INDEX.encode("utf-8"),
        payload_bytes=b"\x00" * selection.length,
        transport_verified=True,
        discovered_at=INIT,
        download_started_at=INIT + timedelta(seconds=1),
        received_at=INIT + timedelta(seconds=2),
        retained_at=INIT + timedelta(seconds=3),
    )
    assert source.selection.length == 100

    scope = CycleProductScope(grid="gfs-0p25-global", lead_hours=6, member=None)
    publication = evaluate_cycle(
        (CycleFieldArrival(name=item.name, scope=scope) for item in selected),
        scope=scope,
        minimum_fields=GFS_MINIMUM_FIELDS,
        complete_fields=GFS_COMPLETE_FIELDS,
    )
    assert publication.state is CycleState.COMPLETE
    assert publication.usable

    provenance = GridFieldProvenance(
        source_id="noaa-gfs",
        source_record_digest=source.verification.payload_digest,
        ingested_at=INIT + timedelta(seconds=4),
        decoder_version="grib-field-decoder/0.2.0+eccodes/2.38.3",
    )
    asset = GridFieldAsset(
        asset_id=uuid4(),
        model_id="noaa-gfs",
        model_version="v16.3",
        guidance_origin=GuidanceOrigin.IMPORTED,
        initialized_at=INIT,
        valid_at=INIT + timedelta(hours=6),
        lead_seconds=21600,
        phenomenon="eastward_wind",
        source_variable="10u",
        level_type="height_above_ground",
        level_value=10.0,
        level_unit="m",
        unit="m s-1",
        grid_id="gfs-0p25-global",
        crs="OGC:CRS84",
        nx=2,
        ny=2,
        longitude_convention="0_360",
        storage_encoding="zarr-v3",
        source_record_digest=source.verification.payload_digest,
        normalized_digest=DIGEST_C,
        source_revision="gfs.20260812/18/f006:message-1",
        decoder_version="grib-field-decoder/0.2.0+eccodes/2.38.3",
        quality_disposition=QualityDisposition.ACCEPT,
        provenance=provenance,
    )
    assert asset.shape == (2, 2)

    payload = encode_vector_tile(
        [0.0, -10.0, 0.0, 10.0],
        [-10.0, 0.0, 10.0, 0.0],
        width=2,
        height=2,
    )
    header, u, v = decode_vector_tile(payload)
    assert (header.width, header.height) == asset.shape[::-1]
    assert v[0] < 0
    assert u[1] < 0
    assert v[2] > 0
    assert u[3] > 0
