import json
import os
from collections.abc import Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile

from weather_platform.domain.models import Observation


class JsonlObservationStore:
    """Small append-only store for the first vertical slice.

    Production implementations will replace this with immutable object storage and
    indexed canonical stores while preserving this append-only behavior.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, observation: Observation) -> None:
        encoded = observation.model_dump_json() + "\n"
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(fd, encoded.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

    def iter_observations(self) -> Iterator[Observation]:
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
        with NamedTemporaryFile("w", dir=self.path.parent, delete=False, encoding="utf-8") as tmp:
            temporary_path = Path(tmp.name)
            for observation in self.iter_observations():
                tmp.write(json.dumps(observation.model_dump(mode="json"), separators=(",", ":")))
                tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        temporary_path.replace(self.path)
