import os
import re
import stat
from pathlib import Path
from tempfile import NamedTemporaryFile

from weather_platform.provenance import sha256_digest

DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
DEFAULT_MAX_SOURCE_RECORD_BYTES = 64 * 1024 * 1024


class RawSourceStore:
    """Content-addressed, write-once store for immutable source records.

    Production implementations will replace this with immutable object storage
    while preserving content addressing and write-once behavior.
    """

    def __init__(
        self,
        root: Path,
        *,
        max_record_bytes: int = DEFAULT_MAX_SOURCE_RECORD_BYTES,
    ) -> None:
        if max_record_bytes <= 0:
            raise ValueError("max_record_bytes must be positive")
        self.root = root
        self.max_record_bytes = max_record_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, digest: str) -> Path:
        return self.root / digest.removeprefix("sha256:")

    @staticmethod
    def _validate_digest(digest: str) -> str:
        if not DIGEST_PATTERN.match(digest):
            raise ValueError("invalid source record digest")
        return digest

    def _open_regular_file(self, path: Path, digest: str) -> int | None:
        """Open one retained record without following a substituted link."""
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ValueError(
                f"retained source record {digest} is not an accessible regular file"
            ) from exc
        try:
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"retained source record {digest} is not a regular file")
            if metadata.st_size > self.max_record_bytes:
                raise ValueError(
                    f"retained source record {digest} exceeds the "
                    f"{self.max_record_bytes}-byte retention limit"
                )
        except Exception:
            os.close(descriptor)
            raise
        return descriptor

    def _read_regular_file(self, path: Path, digest: str) -> bytes | None:
        descriptor = self._open_regular_file(path, digest)
        if descriptor is None:
            return None
        with os.fdopen(descriptor, "rb") as record:
            payload = record.read(self.max_record_bytes + 1)
        if len(payload) > self.max_record_bytes:
            raise ValueError(
                f"retained source record {digest} exceeds the "
                f"{self.max_record_bytes}-byte retention limit"
            )
        return payload

    @staticmethod
    def _verify_payload(digest: str, payload: bytes) -> None:
        if sha256_digest(payload) != digest:
            raise ValueError(f"retained source record {digest} failed integrity verification")

    def store(self, payload: bytes) -> str:
        """Retain the payload and return its content-addressed digest.

        Storing bytes that are already retained verifies the retained copy and
        is otherwise a no-op; retained records are never rewritten.
        """
        if len(payload) > self.max_record_bytes:
            raise ValueError(
                f"source record exceeds the {self.max_record_bytes}-byte retention limit"
            )
        digest = sha256_digest(payload)
        destination = self._path_for(digest)
        existing = self._read_regular_file(destination, digest)
        if existing is not None:
            self._verify_payload(digest, existing)
            return digest
        with NamedTemporaryFile("wb", dir=self.root, delete=False) as tmp:
            temporary_path = Path(tmp.name)
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        temporary_path.chmod(0o440)
        published = False
        try:
            try:
                # A hard-link publish is atomic and never replaces an entry
                # inserted between the initial read and this operation.
                os.link(temporary_path, destination, follow_symlinks=False)
            except FileExistsError as exc:
                existing = self._read_regular_file(destination, digest)
                if existing is None:
                    raise ValueError(
                        f"retained source record {digest} disappeared during store"
                    ) from exc
                self._verify_payload(digest, existing)
            else:
                published = True
        finally:
            temporary_path.unlink(missing_ok=True)
        if published:
            # Persist both the destination link and removal of the temporary
            # name as one durable directory state.
            self._fsync_root()
        return digest

    def _fsync_root(self) -> None:
        # Rename durability requires syncing the containing directory on POSIX.
        directory_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    def exists(self, digest: str) -> bool:
        validated = self._validate_digest(digest)
        descriptor = self._open_regular_file(self._path_for(validated), validated)
        if descriptor is None:
            return False
        os.close(descriptor)
        return True

    def retrieve(self, digest: str) -> bytes:
        validated = self._validate_digest(digest)
        payload = self._read_regular_file(self._path_for(validated), validated)
        if payload is None:
            raise ValueError(f"unknown source record {digest}")
        self._verify_payload(validated, payload)
        return payload
