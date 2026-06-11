"""
backend/api/v1/simulation.py
REST + WebSocket endpoints for the digital twin simulation.
"""
from __future__ import annotations

import asyncio
from typing import List

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from auth.dependencies import CurrentUser, require_auth, ws_auth
from core.dependencies import get_simulation
from core.errors import SimulationError
from models.requests import DisruptionRequest, SimulationStartRequest
from models.responses import DisruptionResponse, SimulationStatusResponse, SnapshotResponse
from services.simulation_service import SimulationService

router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.post("/start", response_model=SimulationStatusResponse)
async def start(req: SimulationStartRequest,
                svc: SimulationService = Depends(get_simulation),
                user: CurrentUser      = Depends(require_auth)):
    svc.set_event_loop(asyncio.get_event_loop())
    svc.speed_factor = req.speed_factor
    session_id = svc.start(corridor=req.corridor, seed=req.seed,
                            disruptions=req.disruptions)
    return SimulationStatusResponse(session_id=session_id, status=svc.status,
                                    tick=svc.tick, wall_time_s=0.0,
                                    n_trains=5, n_disruptions=0)


@router.post("/stop")
def stop(svc: SimulationService = Depends(get_simulation),
         user: CurrentUser      = Depends(require_auth)):
    svc.stop()
    return {"status": "stopped"}


@router.post("/pause")
def pause(svc: SimulationService = Depends(get_simulation),
          user: CurrentUser      = Depends(require_auth)):
    svc.pause()
    return {"status": "paused"}


@router.post("/resume")
async def resume(svc: SimulationService = Depends(get_simulation),
                 user: CurrentUser      = Depends(require_auth)):
    svc.set_event_loop(asyncio.get_event_loop())
    svc.resume()
    return {"status": "running"}


@router.get("/status", response_model=SimulationStatusResponse)
def status(svc: SimulationService = Depends(get_simulation),
           user: CurrentUser      = Depends(require_auth)):
    return SimulationStatusResponse(session_id=svc.session_id, status=svc.status,
                                    tick=svc.tick, wall_time_s=float(svc.tick),
                                    n_trains=5,
                                    n_disruptions=len(svc._disruptions))


@router.get("/snapshot", response_model=SnapshotResponse)
def snapshot(svc: SimulationService = Depends(get_simulation),
             user: CurrentUser      = Depends(require_auth)):
    return svc._build_snapshot()


@router.post("/disrupt", response_model=DisruptionResponse)
def disrupt(req: DisruptionRequest,
            svc: SimulationService = Depends(get_simulation),
            user: CurrentUser      = Depends(require_auth)):
    return svc.inject_disruption(dtype=req.type, section_id=req.section_id,
                                 station_id=req.station_id,
                                 duration_min=req.duration_min,
                                 severity=req.severity)


@router.get("/disruptions", response_model=List[DisruptionResponse])
def disruptions(svc: SimulationService = Depends(get_simulation),
                user: CurrentUser      = Depends(require_auth)):
    return [DisruptionResponse(
                disruption_id=d["disruption_id"], type=d["type"],
                status=d["status"], section_id=d.get("section_id"),
                duration_min=d["duration_min"])
            for d in svc._disruptions]


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket,
                      svc: SimulationService = Depends(get_simulation)):
    user = await ws_auth(websocket)
    if user is None:
        return

    await websocket.accept()
    svc.set_event_loop(asyncio.get_event_loop())
    queue = svc.subscribe()

    async def _receive():
        while True:
            try:
                msg = await websocket.receive_text()
                if msg.strip() == '{"type":"ping"}':
                    await websocket.send_text('{"type":"pong"}')
            except Exception:
                break

    async def _send():
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                frame = '{"type":"ping","payload":{},"tick":0}'
            try:
                await websocket.send_text(frame)
            except Exception:
                break

    try:
        recv_task = asyncio.create_task(_receive())
        send_task = asyncio.create_task(_send())
        done, pending = await asyncio.wait(
            {recv_task, send_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        svc.unsubscribe(queue)
