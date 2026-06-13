"""
NDLS<->CNB Railway Digital Twin - MVP backend.

No Redis / Celery: live updates are produced by an in-process asyncio task
that periodically broadcasts a fresh twin snapshot to all connected
WebSocket clients via app.ws_manager.manager.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS, TWIN_BROADCAST_INTERVAL
from app.controller_state import controller_state
from app.routers import ai, analytics, auth, controller, recommendations, stations, trains, twin
from app.routers.recommendations import get_recommendations
from app.simulation import build_snapshot
from app.ws_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _broadcast_loop():
    while True:
        try:
            snapshot = build_snapshot()
            await manager.broadcast_json(snapshot.model_dump())

            if controller_state.auto_mode:
                for rec in get_recommendations():
                    if rec.severity == "critical" and not controller_state.has_actioned(rec.id):
                        controller_state.log_action(
                            recommendation=rec.model_dump(), actor="Auto-Controller", auto=True
                        )
        except Exception:
            logger.exception("Error broadcasting twin snapshot")
        await asyncio.sleep(TWIN_BROADCAST_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_broadcast_loop())
    logger.info("Started in-process twin broadcast loop (every %ss)", TWIN_BROADCAST_INTERVAL)
    yield
    task.cancel()


app = FastAPI(title="Railway Digital Twin MVP - NDLS<->CNB", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(stations.router)
app.include_router(trains.router)
app.include_router(twin.router)
app.include_router(recommendations.router)
app.include_router(analytics.router)
app.include_router(controller.router)
app.include_router(ai.router)


@app.get("/api/health")
def health():
    from app.data_store import data_store
    from app.predictor import predictor

    return {
        "status": "ok",
        "demo_date": data_store.demo_date,
        "trains_loaded": len(data_store.train_timelines),
        "model_active": predictor.is_model_loaded,
        "model_name": predictor.model_name,
    }
