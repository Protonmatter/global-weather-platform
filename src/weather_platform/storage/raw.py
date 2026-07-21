import os
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from weather_platform.provenance import sha256_digest

DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


class RawSourceStore:
    """Content-addressed, write-once store for immutable source records.

    Production implementations will replace this with immutable object storage
    while preserving content addressing and write-once behavior.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, digest: str) -> Path:
        return self.root / digest.removeprefix("sha256:")

    @staticmethod
    def _validate_digest(digest: str) -> str:
        if not DIGEST_PATTERN.match(digest):
            raise ValueError("invalid source record digest")
        return digest

    def store(self, payload: bytes) -> str:
        """Retain the payload and return its content-addressed digest.

        Storing bytes that are already retained verifies the retained copy and
        is otherwise a no-op; retained records are never rewritten.
        """
        digest = sha256_digest(payload)
        destination = self._path_for(digest)
        if destination.exists():
            if sha256_digest(destination.read_bytes()) != digest:
                raise ValueError(f"retained source record {digest} failed integrity verification")
            return digest
        with NamedTemporaryFile("wb", dir=self.root, delete=False) as tmp:
            temporary_path = Path(tmp.name)
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
        temporary_path.chmod(0o440)
        temporary_path.replace(destination)
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
        return self._path_for(self._validate_digest(digest)).exists()

    def retrieve(self, digest: str) -> bytes:
        path = self._path_for(self._validate_digest(digest))
        if not path.exists():
            raise ValueError(f"unknown source record {digest}")
        payload = path.read_bytes()
        if sha256_digest(payload) != digest:
            raise ValueError(f"retained source record {digest} failed integrity verification")
        return payload
