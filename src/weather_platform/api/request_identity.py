import uuid

from fastapi import Request


def request_id_from_request(request: Request) -> uuid.UUID:
    current = getattr(request.state, "request_id", None)
    if isinstance(current, uuid.UUID):
        return current
    supplied = request.headers.get("x-request-id", "").strip()
    if supplied:
        try:
            return uuid.UUID(supplied)
        except ValueError:
            pass
    return uuid.uuid4()
