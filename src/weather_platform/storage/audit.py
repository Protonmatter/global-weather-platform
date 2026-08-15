import fcntl
import os
import sqlite3
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from weather_platform.domain.audit import MutationAuditEvent, MutationResult


class AuthoritativeAuditStore:
    """Append-only JSONL storage for authoritative mutation events."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = Path(f"{path}.lock")
        self._index_path = Path(f"{path}.index.sqlite3")
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
        self._repair_incomplete_ledger_tail()
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield MutationAuditEvent.model_validate_json(line)
                except ValueError as exc:
                    raise ValueError(f"invalid audit event at line {line_number}") from exc

    def _repair_incomplete_ledger_tail(self) -> None:
        """Remove only an invalid final record that lacks the required newline."""

        descriptor = os.open(self.path, os.O_RDWR)
        try:
            size = os.fstat(descriptor).st_size
            if size == 0:
                return
            os.lseek(descriptor, size - 1, os.SEEK_SET)
            if os.read(descriptor, 1) == b"\n":
                return

            tail_start = 0
            position = size
            while position > 0:
                read_start = max(0, position - 8192)
                os.lseek(descriptor, read_start, os.SEEK_SET)
                chunk = os.read(descriptor, position - read_start)
                newline = chunk.rfind(b"\n")
                if newline >= 0:
                    tail_start = read_start + newline + 1
                    break
                position = read_start

            os.lseek(descriptor, tail_start, os.SEEK_SET)
            tail = bytearray()
            remaining = size - tail_start
            while remaining > 0:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                tail.extend(chunk)
                remaining -= len(chunk)
            try:
                MutationAuditEvent.model_validate_json(bytes(tail))
            except ValueError:
                os.ftruncate(descriptor, tail_start)
                os.fsync(descriptor)
            else:
                os.lseek(descriptor, 0, os.SEEK_END)
                self._write_all(descriptor, b"\n")
                os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @contextmanager
    def _event_index(self) -> Iterator[sqlite3.Connection]:
        """Open the derived event-ID index used by mutation hot paths."""

        descriptor = os.open(self._index_path, os.O_CREAT | os.O_RDWR, 0o640)
        try:
            os.fchmod(descriptor, 0o640)
        finally:
            os.close(descriptor)
        connection = sqlite3.connect(self._index_path, timeout=30)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_index_metadata (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
                """
            )
            columns = {
                str(row[1]) for row in connection.execute("PRAGMA table_info(audit_event_ids)")
            }
            required_columns = {
                "event_id",
                "event_json",
                "occurred_at_utc",
                "result_order",
            }
            if columns and not required_columns.issubset(columns):
                # This is a derived cache. Rebuild once when upgrading from the
                # identity-only schema rather than replaying on every read.
                connection.execute("DROP TABLE audit_event_ids")
                connection.execute("DELETE FROM audit_index_metadata")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_event_ids (
                    event_id TEXT PRIMARY KEY,
                    event_json TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    result_order INTEGER NOT NULL
                )
                """
            )
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _synchronize_event_index(self, connection: sqlite3.Connection) -> None:
        """Index only ledger bytes added since the last durable checkpoint."""

        if self.path.exists():
            self._repair_incomplete_ledger_tail()
            ledger_size = self.path.stat().st_size
        else:
            ledger_size = 0

        row = connection.execute(
            "SELECT value FROM audit_index_metadata WHERE key = 'ledger_size'"
        ).fetchone()
        indexed_size = int(row[0]) if row is not None else 0
        if indexed_size < 0 or indexed_size > ledger_size:
            connection.execute("DELETE FROM audit_event_ids")
            indexed_size = 0

        if indexed_size < ledger_size:
            with self.path.open("rb") as handle:
                handle.seek(indexed_size)
                while line := handle.readline():
                    line_end = handle.tell()
                    if not line.strip():
                        indexed_size = line_end
                        continue
                    try:
                        event = MutationAuditEvent.model_validate_json(line)
                    except ValueError as exc:
                        raise ValueError(
                            f"invalid audit event at byte offset {indexed_size}"
                        ) from exc
                    encoded = event.model_dump_json()
                    existing = connection.execute(
                        "SELECT event_json FROM audit_event_ids WHERE event_id = ?",
                        (str(event.event_id),),
                    ).fetchone()
                    if existing is not None and str(existing[0]) != encoded:
                        raise ValueError(f"conflicting audit event id {event.event_id}")
                    connection.execute(
                        "INSERT OR IGNORE INTO audit_event_ids("
                        "event_id, event_json, occurred_at_utc, result_order"
                        ") VALUES (?, ?, ?, ?)",
                        (
                            str(event.event_id),
                            encoded,
                            event.occurred_at.astimezone(UTC).isoformat(timespec="microseconds"),
                            0 if event.result == MutationResult.ATTEMPTED else 1,
                        ),
                    )
                    indexed_size = line_end

        connection.execute(
            "INSERT INTO audit_index_metadata(key, value) VALUES ('ledger_size', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (indexed_size,),
        )

    def _indexed_ledger_event(self, event_id: UUID) -> MutationAuditEvent | None:
        """Look up an identity without replaying the complete append-only ledger."""

        with self._transaction(), self._event_index() as connection:
            self._synchronize_event_index(connection)
            row = connection.execute(
                "SELECT event_json FROM audit_event_ids WHERE event_id = ?",
                (str(event_id),),
            ).fetchone()
        if row is None:
            return None
        return MutationAuditEvent.model_validate_json(str(row[0]))

    def _indexed_ledger_event_ids(self, event_ids: set[UUID]) -> set[UUID]:
        if not event_ids:
            return set()
        with self._transaction(), self._event_index() as connection:
            self._synchronize_event_index(connection)
            return {
                event_id
                for event_id in event_ids
                if connection.execute(
                    "SELECT 1 FROM audit_event_ids WHERE event_id = ?",
                    (str(event_id),),
                ).fetchone()
                is not None
            }

    def _outbox_file(self, event_id: UUID, state: str) -> Path:
        return self._outbox_path / f"{event_id}.{state}.json"

    def _write_outbox_event(self, event: MutationAuditEvent, target: Path) -> None:
        encoded = event.model_dump_json().encode("utf-8")
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._outbox_path,
            prefix=f".{event.event_id}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            try:
                os.fchmod(descriptor, 0o640)
                self._write_all(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, target)
            self._fsync_directory(self._outbox_path)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

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
            candidates = sorted(self._outbox_path.glob("*.pending.json"))
            ledger_event_ids = self._indexed_ledger_event_ids(
                {UUID(path.name.removesuffix(".pending.json")) for path in candidates}
            )
            snapshot = [
                self._read_outbox_event(path)
                for path in candidates
                if not path.with_name(
                    f"{path.name.removesuffix('.pending.json')}.committed.json"
                ).exists()
                and UUID(path.name.removesuffix(".pending.json")) not in ledger_event_ids
            ]
        yield from snapshot

    def _applied_events(self) -> Iterator[MutationAuditEvent]:
        """Return requests with durable handler-completion receipts."""

        with self._transaction():
            candidates = sorted(self._outbox_path.glob("*.applied.json"))
            ledger_event_ids = self._indexed_ledger_event_ids(
                {UUID(path.name.removesuffix(".applied.json")) for path in candidates}
            )
            snapshot = [
                self._read_outbox_event(path)
                for path in candidates
                if not path.with_name(
                    f"{path.name.removesuffix('.applied.json')}.committed.json"
                ).exists()
                and UUID(path.name.removesuffix(".applied.json")) not in ledger_event_ids
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

        # Applied receipts are mutation-specific evidence written by the
        # request only after its handler returns successfully. They avoid
        # inferring completion from canonical state that may predate a request.
        for event in self._applied_events():
            self.commit_terminal(event.event_id)
        for event in self.pending_events():
            if canonical_state_contains(event):
                self.commit_terminal(event.event_id)

    def append(self, event: MutationAuditEvent) -> None:
        encoded = (event.model_dump_json() + "\n").encode("utf-8")
        with self._transaction():
            if self._indexed_ledger_event(event.event_id) is not None:
                raise ValueError(f"duplicate audit event id {event.event_id}")
            flags = os.O_WRONLY | os.O_APPEND
            created = False
            try:
                descriptor = os.open(self.path, flags | os.O_CREAT | os.O_EXCL, 0o640)
                created = True
            except FileExistsError:
                descriptor = os.open(self.path, flags)
            original_size = os.fstat(descriptor).st_size
            try:
                self._write_all(descriptor, encoded)
                os.fsync(descriptor)
                if created:
                    self._fsync_directory(self.path.parent)
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
        pending = self._outbox_file(event.event_id, "pending")
        applied = self._outbox_file(event.event_id, "applied")
        committed = self._outbox_file(event.event_id, "committed")
        with self._transaction():
            if (
                pending.exists()
                or applied.exists()
                or committed.exists()
                or self._indexed_ledger_event(event.event_id) is not None
            ):
                raise ValueError(f"duplicate audit event id {event.event_id}")
            self._write_outbox_event(event, pending)
        return event.event_id

    def discard_terminal(self, event_id: UUID) -> None:
        """Remove a prepared success after the corresponding mutation fails."""

        with self._transaction():
            pending = self._outbox_file(event_id, "pending")
            if pending.exists():
                pending.unlink()
                self._fsync_directory(self._outbox_path)

    def _append_committed_event(self, event: MutationAuditEvent, committed: Path) -> None:
        try:
            self.append(event)
        except OSError:
            # The committed outbox file is already an authoritative, durable
            # terminal event. A later append/maintenance pass may compact it.
            return
        except ValueError:
            if self._indexed_ledger_event(event.event_id) != event:
                raise

        try:
            with self._transaction():
                committed.unlink(missing_ok=True)
                self._fsync_directory(self._outbox_path)
        except OSError:
            # Replay deduplicates the JSONL and outbox copies by event ID.
            return

    def mark_applied(self, event_id: UUID) -> None:
        """Durably record that one prepared mutation handler completed."""

        pending = self._outbox_file(event_id, "pending")
        applied = self._outbox_file(event_id, "applied")
        committed = self._outbox_file(event_id, "committed")
        with self._transaction():
            if applied.exists() or committed.exists():
                return
            if not pending.exists():
                if self._indexed_ledger_event(event_id) is not None:
                    return
                raise ValueError(f"unknown prepared audit event {event_id}")
            os.replace(pending, applied)
            self._fsync_directory(self._outbox_path)

    @staticmethod
    def _same_mutation(left: MutationAuditEvent, right: MutationAuditEvent) -> bool:
        return (
            left.event_id == right.event_id
            and left.request_id == right.request_id
            and left.actor == right.actor
            and left.action == right.action
            and left.resource_type == right.resource_type
            and left.resource_id == right.resource_id
            and left.software_version == right.software_version
        )

    def commit_failure(self, event_id: UUID, event: MutationAuditEvent) -> None:
        """Durably record failure, including when terminal preparation failed."""

        if event.event_id != event_id or event.result != MutationResult.FAILED:
            raise ValueError("failed event must match the prepared terminal identity")
        pending = self._outbox_file(event_id, "pending")
        committed = self._outbox_file(event_id, "committed")
        with self._transaction():
            if committed.exists():
                existing = self._read_outbox_event(committed)
                if existing != event:
                    raise ValueError(f"conflicting committed audit event {event_id}")
            elif pending.exists():
                prepared = self._read_outbox_event(pending)
                if not self._same_mutation(prepared, event):
                    raise ValueError(f"failed audit event does not match prepared event {event_id}")
                try:
                    self._write_outbox_event(event, committed)
                except OSError:
                    # Terminal preparation may fail because the outbox is no
                    # longer writable while the ledger remains available.
                    # Persist the observed failure directly rather than
                    # leaving only an attempted lifecycle event.
                    self.append(event)
                    try:
                        pending.unlink(missing_ok=True)
                        self._fsync_directory(self._outbox_path)
                    except OSError:
                        # pending_events() ignores identities already made
                        # authoritative in the ledger.
                        pass
                    return
            else:
                indexed_existing = self._indexed_ledger_event(event_id)
                if indexed_existing == event:
                    return
                if indexed_existing is not None:
                    raise ValueError(f"conflicting audit event {event_id}")
                # prepare_terminal() can fail before a pending file exists.
                # The mutation has not run, so the ledger is the appropriate
                # durable path for its terminal failure.
                self.append(event)
                return
            try:
                pending.unlink(missing_ok=True)
                self._fsync_directory(self._outbox_path)
            except OSError:
                # The committed terminal event is authoritative; a stale
                # prepared copy is ignored and can be cleaned up later.
                pass

        self._append_committed_event(event, committed)

    def commit_terminal(
        self,
        event_id: UUID,
        *,
        occurred_at: datetime | None = None,
    ) -> None:
        """Publish a prepared success, retaining it in the outbox if JSONL append fails."""

        pending = self._outbox_file(event_id, "pending")
        applied = self._outbox_file(event_id, "applied")
        committed = self._outbox_file(event_id, "committed")
        with self._transaction():
            if committed.exists():
                event = self._read_outbox_event(committed)
            elif applied.exists() or pending.exists():
                prepared_path = applied if applied.exists() else pending
                prepared = self._read_outbox_event(prepared_path)
                event = prepared.model_copy(
                    update={"occurred_at": occurred_at or datetime.now(UTC)}
                )
                self._write_outbox_event(event, committed)
            else:
                if self._indexed_ledger_event(event_id) is not None:
                    return
                raise ValueError(f"unknown prepared audit event {event_id}")
            try:
                pending.unlink(missing_ok=True)
                applied.unlink(missing_ok=True)
                self._fsync_directory(self._outbox_path)
            except OSError:
                # The committed terminal event is authoritative; a stale
                # prepared copy is ignored and can be cleaned up later.
                pass

        self._append_committed_event(event, committed)

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

    def iter_recent_events(self, limit: int) -> Iterator[MutationAuditEvent]:
        """Return newest events with ledger work bounded by the requested limit."""

        if limit < 1 or limit > 1_000:
            raise ValueError("limit must be between 1 and 1000")
        with self._transaction(), self._event_index() as connection:
            self._synchronize_event_index(connection)
            rows = connection.execute(
                "SELECT event_json FROM audit_event_ids "
                "ORDER BY occurred_at_utc DESC, result_order DESC, event_id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            events = {
                event.event_id: event
                for row in rows
                for event in [MutationAuditEvent.model_validate_json(str(row[0]))]
            }
            for committed_event in self._iter_committed_events():
                indexed = connection.execute(
                    "SELECT event_json FROM audit_event_ids WHERE event_id = ?",
                    (str(committed_event.event_id),),
                ).fetchone()
                if indexed is not None:
                    ledger_event = MutationAuditEvent.model_validate_json(str(indexed[0]))
                    if ledger_event != committed_event:
                        raise ValueError(f"conflicting audit event id {committed_event.event_id}")
                events[committed_event.event_id] = committed_event
            snapshot = sorted(
                events.values(),
                key=lambda event: (
                    event.occurred_at,
                    0 if event.result == MutationResult.ATTEMPTED else 1,
                    str(event.event_id),
                ),
                reverse=True,
            )[:limit]
        yield from snapshot
