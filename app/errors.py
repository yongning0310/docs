from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    status_code: int = 500
    message: str = "Internal server error"

    def __init__(self, detail: str | None = None):
        self.detail = detail or self.message
        super().__init__(self.detail)


class DocumentNotFound(AppError):
    status_code = 404
    message = "Document not found"


class VersionConflict(AppError):
    status_code = 409
    message = "Document has been modified by another request"


class InvalidChangeRequest(AppError):
    status_code = 422
    message = "Invalid change request"


class OccurrenceNotFound(AppError):
    status_code = 422
    message = "Target text occurrence not found"


class RangeOutOfBounds(AppError):
    status_code = 422
    message = "Range is out of document bounds"


class SuggestionNotFound(AppError):
    status_code = 404
    message = "Suggestion not found"


class SuggestionAlreadyResolved(AppError):
    status_code = 409
    message = "Suggestion has already been resolved"


class SuggestionConflict(AppError):
    status_code = 409
    message = "Document text has changed since the suggestion was created"


class DocumentFrozen(AppError):
    """Raised when trying to directly edit a frozen document."""
    status_code = 403
    message = "Document is frozen. Use suggestions for changes."


class DocumentNotFrozen(AppError):
    """Raised when trying to suggest on a non-frozen document."""
    status_code = 400
    message = "Document is not frozen yet. Edit directly instead."


class SelfApproval(AppError):
    """Raised when a user tries to approve their own suggestion."""
    status_code = 403
    message = "Cannot approve your own suggestion."


async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "code": exc.status_code},
    )


async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "code": 500},
    )
