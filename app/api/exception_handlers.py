from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth.api_key import UnauthorizedError
from app.maintenance.mode import MaintenanceModeError
from app.ops.service import OpsNotifyFailedError
from app.schemas import ErrorResponse
from app.services.generation_service import EvalLintFailedError, ProviderFailedError
from app.storage.base import StorageFailedError
from app.services.validator import DocumentValidationError


def _request_id_from_state(request: Request) -> str:
    value = getattr(request.state, "request_id", "")
    return value if isinstance(value, str) and value else "unknown-request-id"


def _error_response(request: Request, *, code: str, message: str, status_code: int) -> JSONResponse:
    request_id = _request_id_from_state(request)
    request.state.error_code = code
    body = ErrorResponse(code=code, message=message, request_id=request_id).model_dump()
    return JSONResponse(status_code=status_code, content=body)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(MaintenanceModeError)
    async def maintenance_mode_handler(request: Request, exc: MaintenanceModeError):  # noqa: ARG001
        return _error_response(
            request,
            code="MAINTENANCE_MODE",
            message="Service temporarily unavailable.",
            status_code=503,
        )

    @app.exception_handler(UnauthorizedError)
    async def unauthorized_handler(request: Request, exc: UnauthorizedError):  # noqa: ARG001
        return _error_response(
            request,
            code="UNAUTHORIZED",
            message="Authentication required.",
            status_code=401,
        )

    @app.exception_handler(ProviderFailedError)
    async def provider_failed_handler(request: Request, exc: ProviderFailedError):  # noqa: ARG001
        return _error_response(
            request,
            code="PROVIDER_FAILED",
            message="Provider request failed.",
            status_code=500,
        )

    @app.exception_handler(EvalLintFailedError)
    async def eval_lint_failed_handler(request: Request, exc: EvalLintFailedError):  # noqa: ARG001
        return _error_response(
            request,
            code="EVAL_LINT_FAILED",
            message="Quality checks failed.",
            status_code=500,
        )

    @app.exception_handler(DocumentValidationError)
    async def doc_validation_failed_handler(request: Request, exc: DocumentValidationError):  # noqa: ARG001
        return _error_response(
            request,
            code="DOC_VALIDATION_FAILED",
            message="Document validation failed.",
            status_code=500,
        )

    @app.exception_handler(StorageFailedError)
    async def storage_failed_handler(request: Request, exc: StorageFailedError):  # noqa: ARG001
        return _error_response(
            request,
            code="STORAGE_FAILED",
            message="Storage operation failed.",
            status_code=500,
        )

    @app.exception_handler(OpsNotifyFailedError)
    async def ops_notify_failed_handler(request: Request, exc: OpsNotifyFailedError):  # noqa: ARG001
        return _error_response(
            request,
            code="OPS_NOTIFY_FAILED",
            message="Incident notification failed.",
            status_code=500,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_failed_handler(request: Request, exc: RequestValidationError):  # noqa: ARG001
        return _error_response(
            request,
            code="REQUEST_VALIDATION_FAILED",
            message="Request validation failed.",
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception):  # noqa: ARG001
        return _error_response(
            request,
            code="INTERNAL_ERROR",
            message="Internal server error.",
            status_code=500,
        )
