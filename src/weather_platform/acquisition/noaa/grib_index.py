from collections.abc import Sequence
from dataclasses import dataclass


class GribIndexError(ValueError):
    """Raised when a provider GRIB index cannot be trusted."""


class MissingRequiredFieldError(GribIndexError):
    """Raised when a required canonical field has no provider message."""


class AmbiguousFieldError(GribIndexError):
    """Raised when a required canonical field matches more than one message."""


@dataclass(frozen=True, slots=True)
class FieldRequirement:
    """Exact, case-insensitive descriptor tokens identifying one provider field."""

    name: str
    tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("field requirement name must not be empty")
        if not self.tokens or any(not token.strip() for token in self.tokens):
            raise ValueError("field requirement tokens must not be empty")


@dataclass(frozen=True, slots=True)
class GribIndexEntry:
    message_number: int
    offset: int
    descriptor_fields: tuple[str, ...]
    raw_descriptor: str
    byte_start: int
    byte_end: int

    @property
    def length(self) -> int:
        return self.byte_end - self.byte_start + 1


@dataclass(frozen=True, slots=True)
class SelectedMessage:
    name: str
    message_number: int
    descriptor_fields: tuple[str, ...]
    byte_start: int
    byte_end: int

    @property
    def length(self) -> int:
        return self.byte_end - self.byte_start + 1


@dataclass(frozen=True, slots=True)
class _ParsedLine:
    message_number: int
    offset: int
    descriptor_fields: tuple[str, ...]
    raw_descriptor: str


def _parse_line(line: str, line_number: int) -> _ParsedLine:
    parts = [part.strip() for part in line.split(":")]
    while parts and not parts[-1]:
        parts.pop()
    if len(parts) < 3:
        raise GribIndexError(f"line {line_number} is not a valid GRIB index entry")

    try:
        message_number = int(parts[0])
        offset = int(parts[1])
    except ValueError as exc:
        message = f"line {line_number} contains a non-integer identity or offset"
        raise GribIndexError(message) from exc

    if message_number <= 0:
        raise GribIndexError(f"line {line_number} message number must be positive")
    if offset < 0:
        raise GribIndexError(f"line {line_number} offset must be non-negative")

    descriptor_fields = tuple(part for part in parts[2:] if part)
    if not descriptor_fields:
        raise GribIndexError(f"line {line_number} has no descriptor fields")

    return _ParsedLine(
        message_number=message_number,
        offset=offset,
        descriptor_fields=descriptor_fields,
        raw_descriptor=":".join(descriptor_fields),
    )


def parse_grib_index(text: str, *, object_size: int) -> list[GribIndexEntry]:
    """Parse a NOAA-style GRIB index and derive inclusive message byte ranges."""

    if object_size <= 0:
        raise GribIndexError("object size must be positive")

    source_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not source_lines:
        raise GribIndexError("GRIB index must contain at least one entry")

    parsed = [_parse_line(line, index) for index, line in enumerate(source_lines, start=1)]
    previous_message = 0
    previous_offset = -1
    for line_number, item in enumerate(parsed, start=1):
        if item.message_number <= previous_message:
            raise GribIndexError(f"line {line_number} message numbers must be strictly increasing")
        if item.offset <= previous_offset:
            raise GribIndexError(f"line {line_number} offsets must be strictly increasing")
        if item.offset >= object_size:
            raise GribIndexError(f"line {line_number} offset is outside the object size")
        previous_message = item.message_number
        previous_offset = item.offset

    entries: list[GribIndexEntry] = []
    for index, item in enumerate(parsed):
        next_offset = parsed[index + 1].offset if index + 1 < len(parsed) else object_size
        byte_end = next_offset - 1
        if byte_end < item.offset:
            raise GribIndexError(f"message {item.message_number} has an empty byte range")
        entries.append(
            GribIndexEntry(
                message_number=item.message_number,
                offset=item.offset,
                descriptor_fields=item.descriptor_fields,
                raw_descriptor=item.raw_descriptor,
                byte_start=item.offset,
                byte_end=byte_end,
            )
        )
    return entries


def _matches(entry: GribIndexEntry, requirement: FieldRequirement) -> bool:
    available = {field.casefold() for field in entry.descriptor_fields}
    return all(token.strip().casefold() in available for token in requirement.tokens)


def select_grib_messages(
    entries: Sequence[GribIndexEntry],
    requirements: Sequence[FieldRequirement],
) -> list[SelectedMessage]:
    """Select exactly one provider message for every required canonical field."""

    selected: list[SelectedMessage] = []
    seen_names: set[str] = set()
    for requirement in requirements:
        if requirement.name in seen_names:
            raise GribIndexError(f"duplicate field requirement {requirement.name}")
        seen_names.add(requirement.name)

        matches = [entry for entry in entries if _matches(entry, requirement)]
        if not matches:
            raise MissingRequiredFieldError(f"missing required field {requirement.name}")
        if len(matches) > 1:
            message_numbers = ", ".join(str(entry.message_number) for entry in matches)
            raise AmbiguousFieldError(
                f"required field {requirement.name} matched messages {message_numbers}"
            )

        entry = matches[0]
        selected.append(
            SelectedMessage(
                name=requirement.name,
                message_number=entry.message_number,
                descriptor_fields=entry.descriptor_fields,
                byte_start=entry.byte_start,
                byte_end=entry.byte_end,
            )
        )
    return selected
