from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


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
