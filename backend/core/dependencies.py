"""
backend/core/dependencies.py
=============================
Shared FastAPI dependency-injection providers.
Services are singletons created at startup and stored on app.state.
"""
from __future__ import annotations

from starlette.requests import HTTPConnection

from services.simulation_service  import SimulationService
from services.prediction_service  import PredictionService
from services.optimization_service import OptimizationService
from services.explanation_service  import ExplanationService


def get_simulation(conn: HTTPConnection) -> SimulationService:
    return conn.app.state.simulation


def get_prediction(conn: HTTPConnection) -> PredictionService:
    return conn.app.state.prediction


def get_optimization(conn: HTTPConnection) -> OptimizationService:
    return conn.app.state.optimization


def get_explanation(conn: HTTPConnection) -> ExplanationService:
    return conn.app.state.explanation
