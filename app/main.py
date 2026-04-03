"""Redline Service — Document editing and search API for documents."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import close_pool, init_db, init_pool
from app.errors import AppError, app_error_handler, unhandled_error_handler
from app.routers import documents, search, suggestions
from app.seed import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: initialize database schema, pool, and seed data
    init_db()
    init_pool()
    seed_database()
    yield
    # Shutdown: close the connection pool
    close_pool()


app = FastAPI(
    title="Redline Service",
    description="Document redlining and search API for legal documents",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, unhandled_error_handler)  # type: ignore[arg-type]


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return validation errors in the same format as other API errors."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation error",
            "code": 422,
            "detail": exc.errors(),
        },
    )


app.include_router(documents.router)
app.include_router(search.router)
app.include_router(suggestions.router)


app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)


@app.get("/")
def root() -> JSONResponse:
    """Redirect root to the frontend UI."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/static/index.html")  # type: ignore[return-value]


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
