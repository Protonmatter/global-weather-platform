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

    @staticmethod
    def _write_all(descriptor: int, payload: bytes) -> None:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written == 0:
                raise OSError("observation write made no progress")
            offset += written

    def _ingestion_marker(self, mutation_id: UUID) -> Path:
        return self._ingestion_path / f"{mutation_id}.json"

    @staticmethod
    def _observation_evidence(observation: Observation) -> dict[str, str]:
        return {
            "content_digest": sha256_digest(observation.model_dump_json().encode("utf-8")),
            "observation_id": str(observation.observation_id),
        }

    def _ingestion_payload(
        self,
        mutation_id: UUID,
        source_digest: str,
        observations: list[Observation],
    ) -> dict[str, object]:
        evidence = sorted(
            (self._observation_evidence(observation) for observation in observations),
            key=lambda item: item["observation_id"],
        )
        return {
            "mutation_id": str(mutation_id),
            "observations": evidence,
            "record_type": "ingestion_mutation",
            "source_record_digest": source_digest,
        }

    @staticmethod
    def _parse_ingestion_payload(raw: object, location: str) -> dict[str, object] | None:
        if not isinstance(raw, dict) or raw.get("record_type") != "ingestion_mutation":
            return None
        if set(raw) != {
            "mutation_id",
            "observations",
            "record_type",
            "source_record_digest",
        }:
            raise ValueError(f"invalid ingestion receipt {location}")
        mutation_id = raw.get("mutation_id")
        source_digest = raw.get("source_record_digest")
        observations = raw.get("observations")
        if (
            not isinstance(mutation_id, str)
            or not isinstance(source_digest, str)
            or not isinstance(observations, list)
        ):
            raise ValueError(f"invalid ingestion receipt {location}")
        for item in observations:
            if (
                not isinstance(item, dict)
                or set(item) != {"content_digest", "observation_id"}
                or not all(isinstance(value, str) for value in item.values())
            ):
                raise ValueError(f"invalid ingestion receipt {location}")
        return raw

    def _decode_entry(self, encoded: str | bytes, location: str) -> Observation | dict[str, object]:
        try:
            raw = json.loads(encoded)
            receipt = self._parse_ingestion_payload(raw, location)
            if receipt is not None:
                return receipt
            return Observation.model_validate(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid observation store entry {location}") from exc

    def _repair_incomplete_tail(self) -> None:
        if not self.path.exists():
            return
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
                self._decode_entry(bytes(tail), "at incomplete tail")
            except ValueError:
                os.ftruncate(descriptor, tail_start)
            else:
                os.lseek(descriptor, 0, os.SEEK_END)
                self._write_all(descriptor, b"\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def _iter_entries(self) -> Iterator[Observation | dict[str, object]]:
        if not self.path.exists():
            return
        self._repair_incomplete_tail()
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line.strip():
                    yield self._decode_entry(line, f"at line {line_number}")

    def _append_encoded(self, encoded: bytes) -> None:
        with self.transaction():
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

    def record_ingestion_mutation(
        self,
        mutation_id: UUID,
        *,
        source_digest: str,
        observations: list[Observation],
    ) -> None:
        """Compatibility helper for recording evidence without new observations."""

        self.commit_ingestion_batch(
            mutation_id,
            source_digest=source_digest,
            appended_observations=[],
            canonical_observations=observations,
        )

    def commit_ingestion_batch(
        self,
        mutation_id: UUID,
        *,
        source_digest: str,
        appended_observations: list[Observation],
        canonical_observations: list[Observation],
    ) -> None:
        """Append canonical observations and their receipt in one ledger payload."""

        receipt = self._ingestion_payload(mutation_id, source_digest, canonical_observations)
        lines = [observation.model_dump_json() for observation in appended_observations]
        lines.append(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
        encoded = ("\n".join(lines) + "\n").encode("utf-8")
        with self.transaction():
            for entry in self._iter_entries():
                if isinstance(entry, dict) and entry["mutation_id"] == str(mutation_id):
                    if entry != receipt:
                        raise ValueError(f"conflicting ingestion marker {mutation_id}")
                    return
            legacy_marker = self._ingestion_marker(mutation_id)
            if legacy_marker.exists():
                try:
                    legacy = json.loads(legacy_marker.read_text(encoding="utf-8"))
                    if isinstance(legacy, dict):
                        legacy["record_type"] = "ingestion_mutation"
                    parsed_legacy = self._parse_ingestion_payload(legacy, legacy_marker.name)
                except (OSError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid ingestion marker {legacy_marker.name}") from exc
                if parsed_legacy != receipt:
                    raise ValueError(f"conflicting ingestion marker {mutation_id}")
                return
            self._append_encoded(encoded)

    def contains_ingestion_mutation(self, mutation_id: UUID, source_digest: str) -> bool:
        """Verify one ingestion marker against the original canonical observations."""

        marker = self._ingestion_marker(mutation_id)
        with self.transaction():
            payload = next(
                (
                    entry
                    for entry in self._iter_entries()
                    if isinstance(entry, dict) and entry["mutation_id"] == str(mutation_id)
                ),
                None,
            )
            if payload is None and marker.exists():
                try:
                    legacy = json.loads(marker.read_text(encoding="utf-8"))
                    if isinstance(legacy, dict):
                        legacy["record_type"] = "ingestion_mutation"
                    payload = self._parse_ingestion_payload(legacy, marker.name)
                except (OSError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid ingestion marker {marker.name}") from exc
            if (
                payload is None
                or payload.get("source_record_digest") != source_digest
                or not isinstance(payload.get("observations"), list)
            ):
                return False
            observations = payload["observations"]
            assert isinstance(observations, list)
            expected = {
                str(item["observation_id"]): str(item["content_digest"])
                for item in observations
                if isinstance(item, dict)
            }
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
        encoded = (observation.model_dump_json() + "\n").encode("utf-8")
        self._append_encoded(encoded)

    def iter_observations(self) -> Iterator[Observation]:
        with self.transaction():
            snapshot = [entry for entry in self._iter_entries() if isinstance(entry, Observation)]
        yield from snapshot

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
                for entry in self._iter_entries():
                    if isinstance(entry, Observation):
                        encoded = json.dumps(entry.model_dump(mode="json"), separators=(",", ":"))
                    else:
                        encoded = json.dumps(entry, separators=(",", ":"), sort_keys=True)
                    tmp.write(encoded)
                    tmp.write("\n")
                tmp.flush()
                os.fsync(tmp.fileno())
            temporary_path.replace(self.path)
