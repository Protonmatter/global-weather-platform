import fcntl
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from weather_platform.domain.audit import MutationAuditEvent


class AuthoritativeAuditStore:
    """Append-only JSONL storage for authoritative mutation events."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = Path(f"{path}.lock")
        self._lock = threading.RLock()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            descriptor = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o640)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX)
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)

    def append(self, event: MutationAuditEvent) -> None:
        encoded = (event.model_dump_json() + "\n").encode("utf-8")
        with self._transaction():
            if any(existing.event_id == event.event_id for existing in self.iter_events()):
                raise ValueError(f"duplicate audit event id {event.event_id}")
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
            try:
                os.write(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    def iter_events(self) -> Iterator[MutationAuditEvent]:
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
