import fcntl
import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from weather_platform.domain.models import Observation, QualityDisposition


class JsonlObservationStore:
    """Small append-only store for the first vertical slice.

    Production implementations will replace this with immutable object storage and
    indexed canonical stores while preserving this append-only behavior.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = Path(str(self.path) + ".lock")
        # Reentrant in-process exclusion; the flock adds cross-process exclusion.
        self._lock = threading.RLock()
        self._lock_fd: int | None = None
        self._lock_depth = 0

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Hold an exclusive lock across a read-modify-write sequence.

        Reentrant within a process (RLock) and exclusive across processes
        (advisory flock), so the admission check-then-append is atomic even
        with multiple workers or a concurrent compaction.
        """
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

    def append(self, observation: Observation) -> None:
        encoded = observation.model_dump_json() + "\n"
        with self.transaction():
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
            try:
                os.write(fd, encoded.encode("utf-8"))
                os.fsync(fd)
            finally:
                os.close(fd)

    def iter_observations(self) -> Iterator[Observation]:
        # Reads need no lock: appends write one complete line via O_APPEND and
        # compaction swaps the file atomically, so a reader never sees a torn line.
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield Observation.model_validate_json(line)
                except ValueError as exc:
                    raise ValueError(f"invalid observation at line {line_number}") from exc

    def list(
        self,
        phenomenon: str | None = None,
        limit: int = 100,
        *,
        include_quarantined: bool = False,
    ) -> list[Observation]:
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        selected: list[Observation] = []
        for observation in self.iter_observations():
            # Quarantined records are retained and queryable, but held out of the
            # default serving path until a reviewer clears their quality state.
            if (
                not include_quarantined
                and observation.quality_disposition == QualityDisposition.QUARANTINE
            ):
                continue
            if phenomenon is None or observation.phenomenon == phenomenon:
                selected.append(observation)
            if len(selected) >= limit:
                break
        return selected

    def compact_atomically(self) -> None:
        """Rewrite valid records atomically without changing record semantics."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction():
            with NamedTemporaryFile(
                "w", dir=self.path.parent, delete=False, encoding="utf-8"
            ) as tmp:
                temporary_path = Path(tmp.name)
                for observation in self.iter_observations():
                    tmp.write(
                        json.dumps(observation.model_dump(mode="json"), separators=(",", ":"))
                    )
                    tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            temporary_path.replace(self.path)
