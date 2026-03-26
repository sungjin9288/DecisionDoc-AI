import hmac
import os

from fastapi import Request

API_KEY_HEADER = "X-DecisionDoc-Api-Key"


class UnauthorizedError(Exception):
    pass


def get_allowed_api_keys() -> list[str]:
    raw_multiple = os.getenv("DECISIONDOC_API_KEYS")
    if raw_multiple is not None:
        return [item.strip() for item in raw_multiple.split(",") if item.strip()]

    raw_legacy = os.getenv("DECISIONDOC_API_KEY", "").strip()
    if raw_legacy:
        return [raw_legacy]
    return []


def require_api_key(request: Request) -> None:
    if request.method.upper() == "OPTIONS":
        return

    allowed_keys = get_allowed_api_keys()
    if not allowed_keys:
        return

    provided = request.headers.get(API_KEY_HEADER, "")
    ok = False
    for allowed_key in allowed_keys:
        ok |= hmac.compare_digest(provided, allowed_key)

    if not ok:
        raise UnauthorizedError("Authentication required.")


def get_tenant_from_api_key(request: Request) -> str | None:
    """If the provided API key matches a per-tenant key, return the tenant_id. Else None."""
    provided = request.headers.get(API_KEY_HEADER, "")
    if not provided or not provided.startswith("dd_"):
        return None
    try:
        tenant_store = request.app.state.tenant_store
        return tenant_store.find_tenant_by_api_key(provided)
    except Exception:
        return None
