import re
from uuid import uuid4

from fastapi import FastAPI, Request

SAFE_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
REQUEST_ID_HEADER = "X-Request-Id"


def install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):  # type: ignore[override]
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if SAFE_REQUEST_ID_PATTERN.fullmatch(incoming) else str(uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id

        return response
