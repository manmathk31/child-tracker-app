"""Custom exception classes and global FastAPI exception handlers."""

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id

logger = logging.getLogger("childtrack.exceptions")


# ==============================================================================
# Domain & Application Exception Hierarchy
# ==============================================================================

class ChildTrackException(Exception):
    """Base exception for all ChildTrack domain and operational errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class NotFoundError(ChildTrackException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource: str, identifier: Any, details: Optional[Dict[str, Any]] = None) -> None:
        message = f"{resource} with identifier '{identifier}' was not found."
        super().__init__(
            message=message,
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ConflictError(ChildTrackException):
    """Raised when an operation conflicts with existing state (e.g. duplicate unique key)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class ValidationError(ChildTrackException):
    """Raised when domain-level or payload validation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
        )


class UnauthorizedError(ChildTrackException):
    """Raised when authentication is missing or invalid."""

    def __init__(self, message: str = "Authentication credentials were not provided or are invalid.") -> None:
        super().__init__(
            message=message,
            code="UNAUTHORIZED",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(ChildTrackException):
    """Raised when an authenticated user lacks permission for the action."""

    def __init__(self, message: str = "You do not have permission to perform this action.") -> None:
        super().__init__(
            message=message,
            code="FORBIDDEN",
            status_code=status.HTTP_403_FORBIDDEN,
        )


class DatabaseUnavailableError(ChildTrackException):
    """Raised when database connectivity cannot be established."""

    def __init__(self, message: str = "Database service is currently unreachable.") -> None:
        super().__init__(
            message=message,
            code="DATABASE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ==============================================================================
# Global Exception Handlers
# ==============================================================================

def _is_api_request(request: Request) -> bool:
    """Check if the incoming request expects a JSON API response."""
    return (
        request.url.path.startswith("/api")
        or request.url.path == "/health"
        or "application/json" in request.headers.get("accept", "")
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register uniform global exception handlers on the FastAPI application."""

    @app.exception_handler(ChildTrackException)
    async def childtrack_exception_handler(request: Request, exc: ChildTrackException) -> JSONResponse:
        logger.warning(
            "Application exception [%s] on %s %s: %s (details: %s)",
            exc.code,
            request.method,
            request.url.path,
            exc.message,
            exc.details,
            extra={"request_id": get_request_id()},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": get_request_id(),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.warning(
            "Request validation error on %s %s: %s",
            request.method,
            request.url.path,
            exc.errors(),
            extra={"request_id": get_request_id()},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_ERROR",
                    "message": "The submitted payload failed validation.",
                    "details": {"validation_errors": exc.errors()},
                    "request_id": get_request_id(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.info(
            "HTTP exception [%s] on %s %s: %s",
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
            extra={"request_id": get_request_id()},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"HTTP_{exc.status_code}",
                    "message": str(exc.detail),
                    "details": {},
                    "request_id": get_request_id(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled server error on %s %s: %s",
            request.method,
            request.url.path,
            str(exc),
            extra={"request_id": get_request_id()},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected server error occurred. Please contact system administrator.",
                    "details": {},
                    "request_id": get_request_id(),
                }
            },
        )
