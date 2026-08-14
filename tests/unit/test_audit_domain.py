import os
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


def audit_store_for_test(storage, tmp_path, monkeypatch):
    if not hasattr(os, "O_DIRECTORY"):
        monkeypatch.setattr(
            storage.AuthoritativeAuditStore,
            "_fsync_directory",
            staticmethod(lambda _path: None),
        )
    return storage.AuthoritativeAuditStore(tmp_path / "mutation-audit.jsonl")


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


def test_authoritative_audit_store_appends_and_replays(tmp_path) -> None:
    domain = audit_module()
    storage = import_module("weather_platform.storage.audit")
    store = storage.AuthoritativeAuditStore(tmp_path / "mutation-audit.jsonl")
    item = valid_event(domain)
    store.append(item)
    assert list(store.iter_events()) == [item]


def test_authoritative_audit_store_rejects_duplicate_event_identity(tmp_path) -> None:
    domain = audit_module()
    storage = import_module("weather_platform.storage.audit")
    store = storage.AuthoritativeAuditStore(tmp_path / "mutation-audit.jsonl")
    item = valid_event(domain)
    store.append(item)
    with pytest.raises(ValueError, match="duplicate"):
        store.append(item)


def test_committed_outbox_survives_a_partial_ledger_append(tmp_path, monkeypatch) -> None:
    domain = audit_module()
    storage = import_module("weather_platform.storage.audit")
    store = storage.AuthoritativeAuditStore(tmp_path / "mutation-audit.jsonl")
    attempted = valid_event(domain)
    succeeded = attempted.model_copy(
        update={
            "event_id": uuid4(),
            "result": domain.MutationResult.SUCCEEDED,
        }
    )
    store.append(attempted)
    terminal_id = store.prepare_terminal(succeeded)

    def partial_write(descriptor: int, payload: bytes) -> None:
        os.write(descriptor, payload[: len(payload) // 2])
        raise OSError("audit ledger is full")

    monkeypatch.setattr(store, "_write_all", partial_write)
    store.commit_terminal(terminal_id)

    assert list(store.iter_events()) == [attempted, succeeded]


def test_pending_success_reconciles_after_process_restart(tmp_path, monkeypatch) -> None:
    domain = audit_module()
    storage = import_module("weather_platform.storage.audit")
    store = audit_store_for_test(storage, tmp_path, monkeypatch)
    audit_path = store.path
    attempted = valid_event(domain)
    succeeded = attempted.model_copy(
        update={
            "event_id": uuid4(),
            "result": domain.MutationResult.SUCCEEDED,
        }
    )
    store.append(attempted)
    store.prepare_terminal(succeeded)

    restarted = storage.AuthoritativeAuditStore(audit_path)
    restarted.reconcile_pending(lambda event: event.resource_id == succeeded.resource_id)

    assert list(restarted.iter_events()) == [attempted, succeeded]
    assert not list(restarted.pending_events())


def test_prepare_terminal_rejects_non_success_event(tmp_path, monkeypatch) -> None:
    domain = audit_module()
    storage = import_module("weather_platform.storage.audit")
    store = audit_store_for_test(storage, tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="only succeeded"):
        store.prepare_terminal(valid_event(domain))


def test_prepare_terminal_rejects_duplicate_prepared_identity(tmp_path, monkeypatch) -> None:
    domain = audit_module()
    storage = import_module("weather_platform.storage.audit")
    store = audit_store_for_test(storage, tmp_path, monkeypatch)
    succeeded = valid_event(domain).model_copy(
        update={"event_id": uuid4(), "result": domain.MutationResult.SUCCEEDED}
    )
    store.prepare_terminal(succeeded)

    with pytest.raises(ValueError, match="duplicate"):
        store.prepare_terminal(succeeded)


def test_pending_events_reject_malformed_outbox_entry(tmp_path, monkeypatch) -> None:
    storage = import_module("weather_platform.storage.audit")
    store = audit_store_for_test(storage, tmp_path, monkeypatch)
    malformed = store._outbox_file(uuid4(), "pending")
    malformed.write_text("not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid audit outbox event"):
        list(store.pending_events())


def test_discard_unknown_terminal_is_idempotent(tmp_path, monkeypatch) -> None:
    storage = import_module("weather_platform.storage.audit")
    store = audit_store_for_test(storage, tmp_path, monkeypatch)

    store.discard_terminal(uuid4())

    assert not list(store.pending_events())


def test_commit_terminal_is_idempotent_after_ledger_append(tmp_path, monkeypatch) -> None:
    domain = audit_module()
    storage = import_module("weather_platform.storage.audit")
    store = audit_store_for_test(storage, tmp_path, monkeypatch)
    succeeded = valid_event(domain).model_copy(
        update={"event_id": uuid4(), "result": domain.MutationResult.SUCCEEDED}
    )
    terminal_id = store.prepare_terminal(succeeded)
    store.commit_terminal(terminal_id)

    store.commit_terminal(terminal_id)

    assert list(store.iter_events()) == [succeeded]


def test_commit_terminal_rejects_unknown_identity(tmp_path, monkeypatch) -> None:
    storage = import_module("weather_platform.storage.audit")
    store = audit_store_for_test(storage, tmp_path, monkeypatch)

    with pytest.raises(ValueError, match="unknown prepared audit event"):
        store.commit_terminal(uuid4())
