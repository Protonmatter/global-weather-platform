from __future__ import annotations

import json
import os
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO

from weather_platform.domain.models import Observation

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised only on non-POSIX platforms
    fcntl = None  # type: ignore[assignment]


class JsonlObservationStore:
    """Append-only canonical observation store for the first vertical slice.

    Writes are idempotent by canonical observation ID. POSIX deployments use an
    advisory file lock around read-check-append so multiple worker processes do
    not append the same derived observation concurrently.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_lock = threading.RLock()

    def append(self, observation: Observation) -> bool:
        return self.append_many([observation]) == 1

    def append_many(self, observations: Iterable[Observation]) -> int:
        pending = list(observations)
        if not pending:
            return 0

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with (
            self._thread_lock,
            self.path.open("a+", encoding="utf-8") as handle,
            self._exclusive_lock(handle),
        ):
            handle.seek(0)
            existing_ids = {
                observation.observation_id for observation in self._iter_handle(handle)
            }
            selected: list[Observation] = []
            selected_ids = set(existing_ids)
            for observation in pending:
                if observation.observation_id in selected_ids:
                    continue
                selected.append(observation)
                selected_ids.add(observation.observation_id)
            if not selected:
                return 0

            handle.seek(0, os.SEEK_END)
            encoded = "".join(
                observation.model_dump_json() + "\n" for observation in selected
            )
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            return len(selected)

    def iter_observations(self) -> Iterator[Observation]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            yield from self._iter_handle(handle)

    def list(self, phenomenon: str | None = None, limit: int = 100) -> list[Observation]:
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        selected: list[Observation] = []
        for observation in self.iter_observations():
            if phenomenon is None or observation.phenomenon == phenomenon:
                selected.append(observation)
            if len(selected) >= limit:
                break
        return selected

    def compact_atomically(self) -> None:
        """Rewrite valid records atomically without changing record semantics."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
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

    @staticmethod
    def _iter_handle(handle: IO[str]) -> Iterator[Observation]:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield Observation.model_validate_json(line)
            except ValueError as exc:
                raise ValueError(f"invalid observation at line {line_number}") from exc

    @staticmethod
    @contextmanager
    def _exclusive_lock(handle: IO[str]) -> Iterator[None]:
        if fcntl is None:
            yield
            return
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
