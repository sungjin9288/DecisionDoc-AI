import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth.api_key import UnauthorizedError
from app.maintenance.mode import MaintenanceModeError
from app.ops.service import OpsNotifyFailedError
from app.schemas import ErrorResponse
from app.services.attachment_service import AttachmentError
from app.services.generation_service import (
    BundleNotSupportedError,
    EvalLintFailedError,
    ProviderFailedError,
    provider_failure_error_code,
    is_provider_rate_limited,
    provider_failure_retry_after_seconds,
)
from app.storage.base import StorageFailedError
from app.services.validator import DocumentValidationError

_log = logging.getLogger("decisiondoc.api.errors")


def _request_id_from_state(request: Request) -> str:
    value = getattr(request.state, "request_id", "")
    return value if isinstance(value, str) and value else "unknown-request-id"


def _error_response(
    request: Request,
    *,
    code: str,
    message: str,
    status_code: int,
    errors: list[str] | None = None,
) -> JSONResponse:
    request_id = _request_id_from_state(request)
    request.state.error_code = code
    body = ErrorResponse(code=code, message=message, request_id=request_id, errors=errors).model_dump(
        exclude_none=True
    )
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
    async def provider_failed_handler(request: Request, exc: ProviderFailedError):
        message = "Provider request failed."
        status_code = 500
        errors: list[str] | None = None
        if is_provider_rate_limited(exc):
            provider_code = provider_failure_error_code(exc)
            if provider_code == "insufficient_quota":
                message = "AI provider quota is exhausted. 운영 키 또는 과금 한도를 확인하세요."
            else:
                message = "AI provider is temporarily rate limited. 잠시 후 다시 시도하세요."
            status_code = 503
            errors = []
            retry_after = provider_failure_retry_after_seconds(exc)
            if retry_after is not None:
                errors.append(f"retry_after_seconds={retry_after}")
            if provider_code:
                errors.append(f"provider_error_code={provider_code}")
            if not errors:
                errors = None
        return _error_response(
            request,
            code="PROVIDER_FAILED",
            message=message,
            status_code=status_code,
            errors=errors,
        )

    @app.exception_handler(EvalLintFailedError)
    async def eval_lint_failed_handler(request: Request, exc: EvalLintFailedError):
        return _error_response(
            request,
            code="EVAL_LINT_FAILED",
            message="Quality checks failed.",
            status_code=500,
            errors=exc.errors[:10] if exc.errors else None,
        )

    @app.exception_handler(DocumentValidationError)
    async def doc_validation_failed_handler(request: Request, exc: DocumentValidationError):
        return _error_response(
            request,
            code="DOC_VALIDATION_FAILED",
            message="Document validation failed.",
            status_code=500,
            errors=exc.missing[:10] if exc.missing else None,
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

    @app.exception_handler(AttachmentError)
    async def attachment_error_handler(request: Request, exc: AttachmentError):
        return _error_response(
            request,
            code="ATTACHMENT_ERROR",
            message=str(exc),
            status_code=422,
        )

    @app.exception_handler(BundleNotSupportedError)
    async def bundle_not_supported_handler(request: Request, exc: BundleNotSupportedError):  # noqa: ARG001
        return _error_response(
            request,
            code="BUNDLE_NOT_SUPPORTED",
            message=str(exc),
            status_code=422,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_failed_handler(request: Request, exc: RequestValidationError):
        details = [
            f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        ]
        return _error_response(
            request,
            code="REQUEST_VALIDATION_FAILED",
            message="Request validation failed.",
            status_code=422,
            errors=details[:10] if details else None,
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception):
        _log.exception(
            "Unhandled application error request_id=%s method=%s path=%s",
            _request_id_from_state(request),
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return _error_response(
            request,
            code="INTERNAL_ERROR",
            message="Internal server error.",
            status_code=500,
        )
