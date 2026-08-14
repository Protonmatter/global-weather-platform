from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

_ALLOWED_DETAIL_KEYS = frozenset(
    {
        "byte_length",
        "completeness",
        "content_digest",
        "error_type",
        "guidance_origin",
        "phenomenon",
        "quality_disposition",
        "retained",
        "source_digest",
    }
)


class MutationResult(StrEnum):
    ATTEMPTED = "attempted"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class MutationAuditEvent(BaseModel):
    """One immutable mutation-lifecycle event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: UUID
    request_id: UUID
    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_id: str = Field(min_length=1)
    result: MutationResult
    occurred_at: AwareDatetime
    software_version: str = Field(min_length=1)
    detail: dict[str, Any] = Field(default_factory=dict)

    @field_validator("detail")
    @classmethod
    def validate_detail_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        unsupported = set(value) - _ALLOWED_DETAIL_KEYS
        if unsupported:
            raise ValueError("audit detail contains sensitive or unsupported keys")
        return value
