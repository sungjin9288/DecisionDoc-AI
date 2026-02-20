import os

from fastapi import Request


class MaintenanceModeError(Exception):
    pass


def is_maintenance_mode() -> bool:
    raw = os.getenv("DECISIONDOC_MAINTENANCE", "0")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def require_not_maintenance(request: Request) -> None:
    enabled = is_maintenance_mode()
    request.state.maintenance = enabled
    if enabled:
        raise MaintenanceModeError("Service temporarily unavailable.")
