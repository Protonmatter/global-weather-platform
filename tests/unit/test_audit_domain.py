from datetime import UTC, datetime
from importlib import import_module
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError


def audit_module():
    return import_module("weather_platform.domain.audit")


def valid_event(module):
    return module.MutationAuditEvent(
        event_id=uuid4(),
        request_id=uuid4(),
        actor="operator@example.invalid",
        action="source_record.retained",
        resource_type="source_record",
        resource_id="sha256:" + "a" * 64,
        result=module.MutationResult.ATTEMPTED,
        occurred_at=datetime(2026, 8, 13, 20, 0, tzinfo=UTC),
        software_version="0.1.0",
        detail={"byte_length": 128},
    )


def test_mutation_audit_event_is_frozen_and_serializable() -> None:
    module = audit_module()
    event = valid_event(module)
    assert UUID(str(event.event_id)) == event.event_id
    assert event.model_dump(mode="json")["result"] == "attempted"
    with pytest.raises(ValidationError):
        event.actor = "changed@example.invalid"


def test_mutation_audit_event_rejects_empty_identifiers() -> None:
    module = audit_module()
    for field in ("actor", "action", "resource_type", "resource_id", "software_version"):
        data = valid_event(module).model_dump()
        data[field] = ""
        with pytest.raises(ValidationError):
            module.MutationAuditEvent.model_validate(data)


def test_mutation_audit_detail_rejects_secret_shaped_keys() -> None:
    module = audit_module()
    data = valid_event(module).model_dump()
    data["detail"] = {"authorization": "Bearer secret"}
    with pytest.raises(ValidationError, match="sensitive"):
        module.MutationAuditEvent.model_validate(data)
