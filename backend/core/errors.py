"""
backend/core/errors.py
=======================
Custom exception hierarchy + FastAPI exception handlers.

All application errors inherit from MARGError so a single handler
catches them.  HTTP status codes are declared on the exception class,
not scattered across route handlers.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


# ── Exception hierarchy ────────────────────────────────────────────────────

class MARGError(Exception):
    """Base class for all MARG application errors."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code:  str = "INTERNAL_ERROR"

    def __init__(self, detail: str = "", **extra: Any):
        super().__init__(detail)
        self.detail = detail
        self.extra  = extra

    def to_dict(self) -> Dict:
        payload: Dict[str, Any] = {
            "error":   self.error_code,
            "detail":  self.detail,
        }
        payload.update(self.extra)
        return payload


class NotFoundError(MARGError):
    status_code = status.HTTP_404_NOT_FOUND
    error_code  = "NOT_FOUND"


class ValidationError(MARGError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code  = "VALIDATION_ERROR"


class AuthError(MARGError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code  = "UNAUTHORIZED"


class ForbiddenError(MARGError):
    status_code = status.HTTP_403_FORBIDDEN
    error_code  = "FORBIDDEN"


class ServiceUnavailableError(MARGError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code  = "SERVICE_UNAVAILABLE"


class SimulationError(MARGError):
    status_code = status.HTTP_409_CONFLICT
    error_code  = "SIMULATION_ERROR"


class PredictionError(MARGError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code  = "PREDICTION_ERROR"


class OptimizationError(MARGError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code  = "OPTIMIZATION_ERROR"


class ExplanationError(MARGError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code  = "EXPLANATION_ERROR"


# ── Handlers ───────────────────────────────────────────────────────────────

def _marg_handler(request: Request, exc: MARGError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error":  "INTERNAL_ERROR",
            "detail": "An unexpected error occurred. Please try again.",
        },
    )


def register_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to the FastAPI app."""
    app.add_exception_handler(MARGError, _marg_handler)            # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unhandled_handler)        # type: ignore[arg-type]
