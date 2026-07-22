import os
from collections.abc import Iterator
from pathlib import Path

from weather_platform.scientific.verification import VerificationCase


class VerificationLedger:
    """Append-only ledger of verification cases.

    Production implementations will replace this with an indexed, versioned
    ledger while preserving the append-only, availability-recording behavior.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, case: VerificationCase) -> None:
        encoded = (case.model_dump_json() + "\n").encode("utf-8")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o640)
        try:
            os.write(fd, encoded)
            os.fsync(fd)
        finally:
            os.close(fd)

    def iter_cases(self) -> Iterator[VerificationCase]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    yield VerificationCase.model_validate_json(line)
                except ValueError as exc:
                    raise ValueError(f"invalid verification case at line {line_number}") from exc

    def list(self, *, baseline_id: str | None = None, limit: int = 100) -> list[VerificationCase]:
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")
        selected: list[VerificationCase] = []
        for case in self.iter_cases():
            if baseline_id is not None and case.baseline_id != baseline_id:
                continue
            selected.append(case)
            if len(selected) >= limit:
                break
        return selected
