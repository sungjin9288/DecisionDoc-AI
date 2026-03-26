import os

from fastapi import Request

from app.config import is_enabled


class MaintenanceModeError(Exception):
    pass


def is_maintenance_mode() -> bool:
    return is_enabled(os.getenv("DECISIONDOC_MAINTENANCE", "0"))


def require_not_maintenance(request: Request) -> None:
    enabled = is_maintenance_mode()
    request.state.maintenance = enabled
    if enabled:
        raise MaintenanceModeError("Service temporarily unavailable.")
