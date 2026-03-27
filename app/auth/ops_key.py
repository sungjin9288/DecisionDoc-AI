import hmac
import os

from fastapi import Request

from app.auth.api_key import UnauthorizedError

OPS_KEY_HEADER = "X-DecisionDoc-Ops-Key"


def has_valid_ops_key_header(request: Request) -> bool:
    expected = os.getenv("DECISIONDOC_OPS_KEY", "").strip()
    provided = request.headers.get(OPS_KEY_HEADER, "")
    return bool(expected and provided and hmac.compare_digest(provided, expected))


def require_ops_key(request: Request) -> None:
    if not has_valid_ops_key_header(request):
        raise UnauthorizedError("Authentication required.")
