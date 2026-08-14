import fcntl
import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import UUID

from weather_platform.domain.models import Observation, QualityDisposition
from weather_platform.provenance import sha256_digest


class JsonlObservationStore:
    """Small append-only store for the first vertical slice.

    Production implementations will replace this with immutable object storage and
    indexed canonical stores while preserving this append-only behavior.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_path = Path(str(self.path) + ".lock")
        self._ingestion_path = Path(str(self.path) + ".ingestions")
        self._ingestion_path.mkdir(mode=0o750, exist_ok=True)
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

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _ingestion_marker(self, mutation_id: UUID) -> Path:
        return self._ingestion_path / f"{mutation_id}.json"

    @staticmethod
    def _observation_evidence(observation: Observation) -> dict[str, str]:
        return {
            "content_digest": sha256_digest(observation.model_dump_json().encode("utf-8")),
            "observation_id": str(observation.observation_id),
        }

    def record_ingestion_mutation(
        self,
        mutation_id: UUID,
        *,
        source_digest: str,
        observations: list[Observation],
    ) -> None:
        """Durably record the exact canonical output expected from one ingestion."""

        evidence = sorted(
            (self._observation_evidence(observation) for observation in observations),
            key=lambda item: item["observation_id"],
        )
        payload = {
            "mutation_id": str(mutation_id),
            "observations": evidence,
            "source_record_digest": source_digest,
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        marker = self._ingestion_marker(mutation_id)
        with self.transaction():
            if marker.exists():
                try:
                    existing = json.loads(marker.read_text(encoding="utf-8"))
                except ValueError as exc:
                    raise ValueError(f"invalid ingestion marker {marker.name}") from exc
                if existing != payload:
                    raise ValueError(f"conflicting ingestion marker {mutation_id}")
                return
            with NamedTemporaryFile(
                "w",
                dir=self._ingestion_path,
                delete=False,
                encoding="utf-8",
            ) as temporary_file:
                temporary = Path(temporary_file.name)
                temporary_file.write(encoded)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            try:
                temporary.chmod(0o640)
                os.replace(temporary, marker)
                self._fsync_directory(self._ingestion_path)
            except BaseException:
                temporary.unlink(missing_ok=True)
                raise

    def contains_ingestion_mutation(self, mutation_id: UUID, source_digest: str) -> bool:
        """Verify one ingestion marker against the original canonical observations."""

        marker = self._ingestion_marker(mutation_id)
        with self.transaction():
            if not marker.exists():
                return False
            try:
                payload = json.loads(marker.read_text(encoding="utf-8"))
                if (
                    not isinstance(payload, dict)
                    or payload.get("mutation_id") != str(mutation_id)
                    or payload.get("source_record_digest") != source_digest
                    or not isinstance(payload.get("observations"), list)
                ):
                    return False
                expected = {
                    str(item["observation_id"]): str(item["content_digest"])
                    for item in payload["observations"]
                    if isinstance(item, dict)
                    and set(item) == {"content_digest", "observation_id"}
                }
                if len(expected) != len(payload["observations"]):
                    return False
            except (OSError, TypeError, ValueError) as exc:
                raise ValueError(f"invalid ingestion marker {marker.name}") from exc
            existing = {
                str(observation.observation_id): sha256_digest(
                    observation.model_dump_json().encode("utf-8")
                )
                for observation in self.iter_observations()
            }
            return all(
                existing.get(observation_id) == digest
                for observation_id, digest in expected.items()
            )

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
