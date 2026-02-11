import hmac
import os

from fastapi import Request

API_KEY_HEADER = "X-DecisionDoc-Api-Key"


class UnauthorizedError(Exception):
    pass


def require_api_key(request: Request) -> None:
    expected = os.getenv("DECISIONDOC_API_KEY", "")
    if not expected:
        return

    provided = request.headers.get(API_KEY_HEADER, "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise UnauthorizedError("Authentication required.")
