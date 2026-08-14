import json
import os
from collections.abc import Iterator
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

    def register(self, cycle: ModelGuidanceCycle, *, mutation_id: UUID | None = None) -> None:
        if mutation_id is None:
            payload = cycle.model_dump(mode="json")
        else:
            payload = {
                "mutation_id": str(mutation_id),
                "cycle": cycle.model_dump(mode="json"),
            }
        encoded = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            offset = 0
            while offset < len(encoded):
                written = os.write(fd, encoded[offset:])
                if written == 0:
                    raise OSError("model catalog write made no progress")
                offset += written
            os.fsync(fd)
        finally:
            os.close(fd)

    def _iter_records(self) -> Iterator[_CatalogEntry]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                    if isinstance(payload, dict) and "mutation_id" in payload:
                        mutation_id = UUID(str(payload["mutation_id"]))
                        cycle = ModelGuidanceCycle.model_validate(payload.get("cycle"))
                    else:
                        mutation_id = None
                        cycle = ModelGuidanceCycle.model_validate(payload)
                    yield _CatalogEntry(mutation_id=mutation_id, cycle=cycle)
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
