from datetime import timedelta
from enum import StrEnum
from typing import Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    field_validator,
    model_validator,
)

from weather_platform.domain.model_catalog import GuidanceOrigin
from weather_platform.domain.models import Provenance, QualityDisposition

SHA256_PATTERN = r"^sha256:[a-f0-9]{64}$"


class LongitudeConvention(StrEnum):
    ZERO_TO_360 = "0_360"
    NEGATIVE_180_TO_180 = "-180_180"


class StorageEncoding(StrEnum):
    GRIB2 = "grib2"
    ZARR_V3 = "zarr-v3"
    COG = "cog"
    BINARY_VECTOR_TILE = "binary-vector-tile"


class GridFieldAsset(BaseModel):
    """Metadata for one model field, valid time, grid, level, and member."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = "1.0.0"
    asset_id: UUID
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    guidance_origin: GuidanceOrigin
    initialized_at: AwareDatetime
    valid_at: AwareDatetime
    lead_seconds: int = Field(ge=0)
    ensemble_member: str | None = Field(default=None, min_length=1)
    phenomenon: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    source_variable: str = Field(min_length=1)
    level_type: str = Field(min_length=1)
    level_value: FiniteFloat | None = None
    level_unit: str | None = Field(default=None, min_length=1)
    unit: str = Field(min_length=1)
    grid_id: str = Field(min_length=1)
    crs: str = Field(min_length=1)
    nx: int = Field(gt=0)
    ny: int = Field(gt=0)
    longitude_convention: LongitudeConvention
    storage_encoding: StorageEncoding
    source_record_digest: str = Field(pattern=SHA256_PATTERN)
    normalized_digest: str = Field(pattern=SHA256_PATTERN)
    source_revision: str = Field(min_length=1)
    decoder_version: str = Field(min_length=1)
    quality_disposition: QualityDisposition
    quality_flags: list[str] = Field(default_factory=list)
    provenance: Provenance

    @field_validator("quality_flags")
    @classmethod
    def validate_quality_flags_unique(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("quality flags must be unique")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        expected_valid_at = self.initialized_at + timedelta(seconds=self.lead_seconds)
        if self.valid_at != expected_valid_at:
            raise ValueError("valid_at must equal initialized_at plus lead_seconds")

        if (self.level_value is None) != (self.level_unit is None):
            raise ValueError("level_value and level_unit must be supplied together")

        if self.quality_disposition == QualityDisposition.ACCEPT and self.quality_flags:
            raise ValueError("accepted grid assets cannot carry unresolved quality flags")

        if self.source_record_digest != self.provenance.source_record_digest:
            raise ValueError("source_record_digest must match provenance")
        if self.decoder_version != self.provenance.decoder_version:
            raise ValueError("decoder_version must match provenance")
        return self

    @property
    def shape(self) -> tuple[int, int]:
        return self.ny, self.nx
