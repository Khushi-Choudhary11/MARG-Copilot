"""
backend/main.py
================
FastAPI application factory.

Start dev server:
    cd backend
    uvicorn main:app --reload --port 8000

Production:
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
"""
from __future__ import annotations

import sys
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Make `backend/` importable as the root package
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from api.v1.router import v1_router
from config import get_settings
from core.errors import register_handlers
from core.logging import configure_logging, get_logger
from services.explanation_service import ExplanationService
from services.optimization_service import OptimizationService
from services.prediction_service import PredictionService
from services.simulation_service import SimulationService

log = get_logger(__name__)


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()

    configure_logging(
        level=cfg.log_level,
        json=not cfg.debug,
    )
    log.info("MARG backend starting", version=cfg.app_version)

    # ── Initialise services ───────────────────────────────────────────────
    app.state.simulation  = SimulationService(speed_factor=cfg.sim_tick_seconds)
    app.state.prediction  = PredictionService(model_dir=cfg.project_root / cfg.ml_model_dir)
    app.state.optimization = OptimizationService()
    app.state.explanation  = ExplanationService(
        api_key   = cfg.anthropic_api_key,
        model     = cfg.claude_model,
        use_redis = cfg.use_redis_cache,
        redis_url = cfg.redis_url,
    )

    log.info("All services initialised")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────
    app.state.simulation.stop()
    log.info("MARG backend stopped")


# ── App factory ───────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    cfg = get_settings()

    app = FastAPI(
        title        = cfg.app_name,
        version      = cfg.app_version,
        description  = (
            "MARG — Machine-learning Assisted Railway Guidance.\n\n"
            "Real-time decision-support for Indian Railways section controllers: "
            "delay prediction, congestion forecasting, CP-SAT optimisation, "
            "and Claude-powered plain-English justifications."
        ),
        docs_url     = "/docs",
        redoc_url    = "/redoc",
        openapi_url  = "/openapi.json",
        lifespan     = lifespan,
    )

    # ── Middleware ────────────────────────────────────────────────────────
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    # When cors_origins is ["*"] we must NOT set allow_credentials=True
    # (browser rejects credentialed wildcard CORS). Use explicit origins for
    # credentialed requests in production; wildcard is fine for demo tunnels.
    wildcard = cfg.cors_origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins     = cfg.cors_origins,
        allow_credentials = not wildcard,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )

    # Request timing middleware
    @app.middleware("http")
    async def add_timing(request: Request, call_next):
        t0       = time.monotonic()
        response = await call_next(request)
        ms       = (time.monotonic() - t0) * 1000
        response.headers["X-Process-Time-Ms"] = f"{ms:.1f}"
        return response

    # ── Exception handlers ────────────────────────────────────────────────
    register_handlers(app)

    # ── Routers ───────────────────────────────────────────────────────────
    app.include_router(v1_router)

    # ── Health + root ─────────────────────────────────────────────────────
    @app.get("/", include_in_schema=False)
    def root():
        return {"service": cfg.app_name, "version": cfg.app_version, "docs": "/docs"}

    @app.get("/health", tags=["health"], summary="Service health check")
    def health(request: Request):
        sim  = getattr(request.app.state, "simulation",  None)
        pred = getattr(request.app.state, "prediction",  None)
        opt  = getattr(request.app.state, "optimization",None)
        expl = getattr(request.app.state, "explanation", None)

        return {
            "status":  "ok",
            "version": cfg.app_version,
            "services": {
                "simulation":    sim.status if sim  else "unavailable",
                "prediction":    "loaded"   if pred and pred._predictor else "heuristic",
                "optimization":  "ready"    if opt  and opt._engine     else "unavailable",
                "explainability":"live"     if expl and expl._explainer and
                                             getattr(expl._explainer, "_client", None)
                                            else "template",
            },
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    cfg = get_settings()
    uvicorn.run(
        "main:app",
        host    = cfg.host,
        port    = cfg.port,
        reload  = cfg.debug,
        workers = cfg.workers if not cfg.debug else 1,
        log_level = cfg.log_level.lower(),
    )
