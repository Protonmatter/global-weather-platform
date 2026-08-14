import fcntl
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from weather_platform.domain.audit import MutationAuditEvent, MutationResult


class AuthoritativeAuditStore:
    """Append-only JSONL storage for authoritative mutation events."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = Path(f"{path}.lock")
        self._outbox_path = Path(f"{path}.outbox")
        self._outbox_path.mkdir(mode=0o750, exist_ok=True)
        self._lock = threading.RLock()
        self._lock_fd: int | None = None
        self._lock_depth = 0

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            if self._lock_depth == 0:
                self._lock_fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o640)
                fcntl.flock(self._lock_fd, fcntl.LOCK_EX)
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
                if self._lock_depth == 0 and self._lock_fd is not None:
                    fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
                    os.close(self._lock_fd)
                    self._lock_fd = None

    @staticmethod
    def _write_all(descriptor: int, payload: bytes) -> None:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written == 0:
                raise OSError("audit write made no progress")
            offset += written

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _iter_ledger_events(self) -> Iterator[MutationAuditEvent]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield MutationAuditEvent.model_validate_json(line)
                except ValueError as exc:
                    raise ValueError(f"invalid audit event at line {line_number}") from exc

    def _outbox_file(self, event_id: UUID, state: str) -> Path:
        return self._outbox_path / f"{event_id}.{state}.json"

    @staticmethod
    def _read_outbox_event(path: Path) -> MutationAuditEvent:
        try:
            return MutationAuditEvent.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"invalid audit outbox event {path.name}") from exc

    def _iter_committed_events(self) -> Iterator[MutationAuditEvent]:
        for path in sorted(self._outbox_path.glob("*.committed.json")):
            yield self._read_outbox_event(path)

    def pending_events(self) -> Iterator[MutationAuditEvent]:
        """Return a stable snapshot of successes awaiting state reconciliation."""

        with self._transaction():
            snapshot = [
                self._read_outbox_event(path)
                for path in sorted(self._outbox_path.glob("*.pending.json"))
            ]
        yield from snapshot

    def reconcile_pending(
        self,
        canonical_state_contains: Callable[[MutationAuditEvent], bool],
    ) -> None:
        """Commit prepared successes proven present in canonical state.

        A false result is intentionally inconclusive: the pending entry remains
        durable for a later recovery pass rather than being converted into a
        false success or discarded without evidence.
        """

        for event in self.pending_events():
            if canonical_state_contains(event):
                self.commit_terminal(event.event_id)

    def append(self, event: MutationAuditEvent) -> None:
        encoded = (event.model_dump_json() + "\n").encode("utf-8")
        with self._transaction():
            if any(existing.event_id == event.event_id for existing in self._iter_ledger_events()):
                raise ValueError(f"duplicate audit event id {event.event_id}")
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
            original_size = os.fstat(descriptor).st_size
            try:
                self._write_all(descriptor, encoded)
                os.fsync(descriptor)
            except OSError:
                os.ftruncate(descriptor, original_size)
                os.fsync(descriptor)
                raise
            finally:
                os.close(descriptor)

    def prepare_terminal(self, event: MutationAuditEvent) -> UUID:
        """Durably reserve a terminal success before publishing canonical state."""

        if event.result != MutationResult.SUCCEEDED:
            raise ValueError("only succeeded events may be prepared for outbox commit")
        encoded = event.model_dump_json().encode("utf-8")
        pending = self._outbox_file(event.event_id, "pending")
        committed = self._outbox_file(event.event_id, "committed")
        with self._transaction():
            if (
                pending.exists()
                or committed.exists()
                or any(
                    existing.event_id == event.event_id for existing in self._iter_ledger_events()
                )
            ):
                raise ValueError(f"duplicate audit event id {event.event_id}")
            descriptor = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
            try:
                self._write_all(descriptor, encoded)
                os.fsync(descriptor)
            except Exception:
                pending.unlink(missing_ok=True)
                raise
            finally:
                os.close(descriptor)
            self._fsync_directory(self._outbox_path)
        return event.event_id

    def discard_terminal(self, event_id: UUID) -> None:
        """Remove a prepared success after the corresponding mutation fails."""

        with self._transaction():
            pending = self._outbox_file(event_id, "pending")
            if pending.exists():
                pending.unlink()
                self._fsync_directory(self._outbox_path)

    def commit_terminal(self, event_id: UUID) -> None:
        """Publish a prepared success, retaining it in the outbox if JSONL append fails."""

        pending = self._outbox_file(event_id, "pending")
        committed = self._outbox_file(event_id, "committed")
        with self._transaction():
            if pending.exists():
                event = self._read_outbox_event(pending)
                os.replace(pending, committed)
                self._fsync_directory(self._outbox_path)
            elif committed.exists():
                event = self._read_outbox_event(committed)
            else:
                if any(existing.event_id == event_id for existing in self._iter_ledger_events()):
                    return
                raise ValueError(f"unknown prepared audit event {event_id}")

        try:
            self.append(event)
        except OSError:
            # The committed outbox file is already an authoritative, durable
            # terminal event. A later append/maintenance pass may compact it.
            return
        except ValueError:
            with self._transaction():
                matching = [
                    existing
                    for existing in self._iter_ledger_events()
                    if existing.event_id == event.event_id
                ]
            if matching != [event]:
                raise

        try:
            with self._transaction():
                committed.unlink(missing_ok=True)
                self._fsync_directory(self._outbox_path)
        except OSError:
            # Replay deduplicates the JSONL and outbox copies by event ID.
            return

    def iter_events(self) -> Iterator[MutationAuditEvent]:
        with self._transaction():
            events: dict[UUID, MutationAuditEvent] = {}
            for event in self._iter_ledger_events():
                events[event.event_id] = event
            for event in self._iter_committed_events():
                existing = events.get(event.event_id)
                if existing is not None and existing != event:
                    raise ValueError(f"conflicting audit event id {event.event_id}")
                events[event.event_id] = event
            snapshot = sorted(
                events.values(),
                key=lambda event: (
                    event.occurred_at,
                    0 if event.result == MutationResult.ATTEMPTED else 1,
                    str(event.event_id),
                ),
            )
        yield from snapshot
