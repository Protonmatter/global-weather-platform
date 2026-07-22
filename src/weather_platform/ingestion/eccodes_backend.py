"""Real ecCodes GRIB2 decode backend for the model guidance catalog (DATA-003).

GRIB2 carries gridded model output, so a message maps to a catalogued
``ModelCycleField`` (variable, level, grid, lead), not to a point observation.
Decoding a cycle's GRIB2 messages therefore yields the cycle's real available
field inventory, which drives MODEL-001 completeness from the actual bytes.

ecCodes is an optional dependency (native library); import lazily so the
package works without it. The decoder records the ecCodes version it ran with,
read at runtime, so the definition-table version in provenance is never stale.
"""

import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from weather_platform.domain.model_catalog import ModelCycleField


class EccodesUnavailableError(RuntimeError):
    """Raised when a decode is attempted but ecCodes is not installed."""


def _import_eccodes() -> ModuleType:
    try:
        import eccodes  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise EccodesUnavailableError(
            "GRIB2 decoding requires the 'eccodes' extra (native ecCodes library)"
        ) from exc
    return cast(ModuleType, eccodes)


def eccodes_available() -> bool:
    try:
        _import_eccodes()
    except EccodesUnavailableError:
        return False
    return True


def runtime_decoder_version() -> str:
    """Return the decoder id including the ecCodes version actually loaded."""
    eccodes = _import_eccodes()
    return f"grib-field-decoder/0.1.0+eccodes/{eccodes.codes_get_api_version()}"


def _message_field(eccodes: ModuleType, gid: Any) -> ModelCycleField:
    level_value = float(eccodes.codes_get(gid, "level"))
    return ModelCycleField(
        variable=str(eccodes.codes_get(gid, "shortName")),
        level_type=str(eccodes.codes_get(gid, "typeOfLevel")),
        level_value=level_value,
        grid=(
            f"{eccodes.codes_get(gid, 'gridType')}:"
            f"{eccodes.codes_get(gid, 'Ni')}x{eccodes.codes_get(gid, 'Nj')}"
        ),
        lead_hours=int(eccodes.codes_get(gid, "endStep")),
    )


def grib_field_inventory(payload: bytes) -> list[ModelCycleField]:
    """Decode every GRIB2 message in the payload into its catalogued field identity."""
    eccodes = _import_eccodes()
    fields: list[ModelCycleField] = []
    with tempfile.NamedTemporaryFile("wb", delete=False) as handle:
        handle.write(payload)
        path = Path(handle.name)
    try:
        with path.open("rb") as stream:
            while True:
                try:
                    gid = eccodes.codes_grib_new_from_file(stream)
                except Exception as exc:  # malformed message
                    raise ValueError("undecodable GRIB2 message") from exc
                if gid is None:
                    break
                try:
                    fields.append(_message_field(eccodes, gid))
                finally:
                    eccodes.codes_release(gid)
    finally:
        path.unlink(missing_ok=True)
    if not fields:
        raise ValueError("no GRIB2 messages found in payload")
    return fields
