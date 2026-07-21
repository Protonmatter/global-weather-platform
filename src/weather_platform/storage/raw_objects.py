from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

_SHA256_PREFIX = "sha256:"
_SHA256_HEX_LENGTH = 64


class RawObjectError(RuntimeError):
    """Base error for content-addressed raw object storage."""


class RawObjectCorruptionError(RawObjectError):
    """Raised when stored bytes no longer match their content address."""


@dataclass(frozen=True, slots=True)
class RawObjectReference:
    digest: str
    uri: str
    size_bytes: int
    created: bool


class FileSystemRawObjectStore:
    """Immutable SHA-256 content-addressed object storage.

    Objects are placed under ``<root>/sha256/aa/bb/<remaining digest>``. Creation
    uses ``O_EXCL`` so an existing object is never overwritten. Existing objects
    are revalidated before being returned.
    """

    def __init__(self, root: Path, *, max_object_bytes: int = 64 * 1024 * 1024) -> None:
        if max_object_bytes < 1:
            raise ValueError("max_object_bytes must be positive")
        self.root = root
        self.max_object_bytes = max_object_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, payload: bytes) -> RawObjectReference:
        if len(payload) > self.max_object_bytes:
            raise ValueError(f"raw object exceeds maximum size of {self.max_object_bytes} bytes")

        digest = self.digest(payload)
        target = self.path_for_digest(digest)
        target.parent.mkdir(parents=True, exist_ok=True)

        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(target, flags, 0o440)
        except FileExistsError:
            self._verify_existing(target, digest, payload)
            return self.reference(digest, size_bytes=len(payload), created=False)

        try:
            view = memoryview(payload)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError("raw object write made no forward progress")
                written += count
            os.fsync(descriptor)
        except BaseException:
            os.close(descriptor)
            target.unlink(missing_ok=True)
            raise
        else:
            os.close(descriptor)

        os.chmod(target, 0o440)
        self._fsync_directory(target.parent)
        return self.reference(digest, size_bytes=len(payload), created=True)

    def get(self, digest: str) -> bytes:
        target = self.path_for_digest(digest)
        payload = self._read_regular_file(target)
        actual = self.digest(payload)
        if actual != digest:
            raise RawObjectCorruptionError(
                f"raw object {digest} failed integrity verification; calculated {actual}"
            )
        return payload

    def contains(self, digest: str) -> bool:
        target = self.path_for_digest(digest)
        if not target.exists():
            return False
        self._require_regular_file(target)
        return True

    def path_for_digest(self, digest: str) -> Path:
        hexadecimal = self._validate_digest(digest)
        return self.root / "sha256" / hexadecimal[:2] / hexadecimal[2:4] / hexadecimal[4:]

    @staticmethod
    def digest(payload: bytes) -> str:
        return f"{_SHA256_PREFIX}{hashlib.sha256(payload).hexdigest()}"

    @staticmethod
    def uri_for_digest(digest: str) -> str:
        hexadecimal = FileSystemRawObjectStore._validate_digest(digest)
        return f"cas://sha256/{hexadecimal}"

    @classmethod
    def reference(cls, digest: str, *, size_bytes: int, created: bool) -> RawObjectReference:
        return RawObjectReference(
            digest=digest,
            uri=cls.uri_for_digest(digest),
            size_bytes=size_bytes,
            created=created,
        )

    @staticmethod
    def _validate_digest(digest: str) -> str:
        if not digest.startswith(_SHA256_PREFIX):
            raise ValueError("digest must use the sha256 algorithm")
        hexadecimal = digest.removeprefix(_SHA256_PREFIX)
        if len(hexadecimal) != _SHA256_HEX_LENGTH:
            raise ValueError("sha256 digest must contain 64 hexadecimal characters")
        if any(character not in "0123456789abcdef" for character in hexadecimal):
            raise ValueError("sha256 digest must use lowercase hexadecimal characters")
        return hexadecimal

    def _verify_existing(self, target: Path, digest: str, expected_payload: bytes) -> None:
        actual_payload = self._read_regular_file(target)
        actual_digest = self.digest(actual_payload)
        if actual_digest != digest or actual_payload != expected_payload:
            raise RawObjectCorruptionError(
                f"existing raw object at {target} does not match content address {digest}"
            )

    @staticmethod
    def _read_regular_file(path: Path) -> bytes:
        FileSystemRawObjectStore._require_regular_file(path)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"raw object not found: {path}") from exc
        except OSError as exc:
            raise RawObjectCorruptionError(f"raw object cannot be opened safely: {path}") from exc

        try:
            mode = os.fstat(descriptor).st_mode
            if not stat.S_ISREG(mode):
                raise RawObjectCorruptionError(f"raw object path is not a regular file: {path}")
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    @staticmethod
    def _require_regular_file(path: Path) -> None:
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"raw object not found: {path}") from exc
        if not stat.S_ISREG(mode):
            raise RawObjectCorruptionError(f"raw object path is not a regular file: {path}")

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if not hasattr(os, "O_DIRECTORY"):
            return
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
