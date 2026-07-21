import hashlib


def sha256_digest(payload: bytes) -> str:
    """Return a content-addressed SHA-256 digest."""
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
