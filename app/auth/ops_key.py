import hmac
import os

from fastapi import Request

from app.auth.api_key import UnauthorizedError

OPS_KEY_HEADER = "X-DecisionDoc-Ops-Key"


def require_ops_key(request: Request) -> None:
    expected = os.getenv("DECISIONDOC_OPS_KEY", "").strip()
    provided = request.headers.get(OPS_KEY_HEADER, "")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise UnauthorizedError("Authentication required.")
