import fcntl
import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from weather_platform.domain.model_catalog import GuidanceOrigin, ModelGuidanceCycle
from weather_platform.provenance import sha256_digest


@dataclass(frozen=True)
class _CatalogEntry:
    mutation_id: UUID | None
    cycle: ModelGuidanceCycle


class ModelGuidanceCatalog:
    """Append-only catalog of external and platform model cycles.

    Re-registering a cycle key appends a new entry; queries return the latest
    entry per key, so a cycle that fills in from partial to complete updates in
    place without losing its history. Production implementations will replace
    this with an indexed catalog while preserving the append-only history.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = Path(f"{path}.lock")
        self._lock = threading.RLock()
        self._lock_fd: int | None = None
        self._lock_depth = 0
        with self._transaction():
            if self.path.exists():
                self._repair_incomplete_tail()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """Serialize repair and append operations across threads and processes."""

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
    def _decode_record(payload: object) -> _CatalogEntry:
        if isinstance(payload, dict) and "mutation_id" in payload:
            mutation_id = UUID(str(payload["mutation_id"]))
            cycle = ModelGuidanceCycle.model_validate(payload.get("cycle"))
        else:
            mutation_id = None
            cycle = ModelGuidanceCycle.model_validate(payload)
        return _CatalogEntry(mutation_id=mutation_id, cycle=cycle)

    def _repair_incomplete_tail(self) -> None:
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
                self._decode_record(json.loads(bytes(tail)))
            except (TypeError, ValueError):
                os.ftruncate(descriptor, tail_start)
            else:
                os.lseek(descriptor, 0, os.SEEK_END)
                if os.write(descriptor, b"\n") != 1:
                    raise OSError("model catalog newline write made no progress")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def register(self, cycle: ModelGuidanceCycle, *, mutation_id: UUID | None = None) -> None:
        if mutation_id is None:
            payload = cycle.model_dump(mode="json")
        else:
            payload = {
                "mutation_id": str(mutation_id),
                "cycle": cycle.model_dump(mode="json"),
            }
        encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        with self._transaction():
            # Another process may have crashed after this instance was
            # constructed. Repair its unterminated tail before extending it.
            if self.path.exists():
                self._repair_incomplete_tail()
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
            original_size = os.fstat(fd).st_size
            try:
                offset = 0
                while offset < len(encoded):
                    written = os.write(fd, encoded[offset:])
                    if written == 0:
                        raise OSError("model catalog write made no progress")
                    offset += written
                os.fsync(fd)
            except OSError:
                os.ftruncate(fd, original_size)
                os.fsync(fd)
                raise
            finally:
                os.close(fd)

    def _iter_records(self) -> Iterator[_CatalogEntry]:
        with self._transaction():
            if not self.path.exists():
                return
            with self.path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    try:
                        payload = json.loads(line)
                        yield self._decode_record(payload)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"invalid model cycle at line {line_number}") from exc

    def _iter_entries(self) -> Iterator[ModelGuidanceCycle]:
        for record in self._iter_records():
            yield record.cycle

    def contains_mutation(self, mutation_id: UUID, content_digest: str) -> bool:
        """Return whether the exact mutation durably appended the expected cycle."""

        return any(
            record.mutation_id == mutation_id
            and sha256_digest(record.cycle.model_dump_json().encode("utf-8")) == content_digest
            for record in self._iter_records()
        )

    def _latest_by_key(self) -> dict[tuple[str, str, str, str], ModelGuidanceCycle]:
        latest: dict[tuple[str, str, str, str], ModelGuidanceCycle] = {}
        for cycle in self._iter_entries():
            latest[cycle.cycle_key()] = cycle
        return latest

    def list(
        self,
        *,
        model_id: str | None = None,
        guidance_origin: GuidanceOrigin | None = None,
        limit: int = 100,
    ) -> list[ModelGuidanceCycle]:
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        selected: list[ModelGuidanceCycle] = []
        for cycle in self._latest_by_key().values():
            if model_id is not None and cycle.model_id != model_id:
                continue
            if guidance_origin is not None and cycle.guidance_origin != guidance_origin:
                continue
            selected.append(cycle)
            if len(selected) >= limit:
                break
        return selected
