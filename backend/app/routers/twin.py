from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import TWIN_BROADCAST_INTERVAL
from app.schemas import TwinSnapshot
from app.simulation import build_snapshot
from app.ws_manager import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/twin", tags=["twin"])


@router.get("/snapshot", response_model=TwinSnapshot)
def get_snapshot():
    return build_snapshot()


@router.websocket("/ws")
async def twin_ws(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send an immediate snapshot on connect, then rely on the broadcast loop.
        await websocket.send_json(build_snapshot().model_dump())
        while True:
            # Keep the connection alive; client doesn't need to send anything.
            await asyncio.sleep(TWIN_BROADCAST_INTERVAL * 10)
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
