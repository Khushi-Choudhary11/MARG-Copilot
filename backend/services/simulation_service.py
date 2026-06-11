"""
backend/services/simulation_service.py
Bridges FastAPI to the simulation package.
Uses a daemon thread for the tick loop — works from sync or async handlers.
"""
from __future__ import annotations

import asyncio
import math
import threading
import time
import uuid
from typing import Optional, Set, List

from core.errors import SimulationError
from core.logging import get_logger
from models.responses import (
    DisruptionResponse, SnapshotResponse, TrainPositionResponse, WsFrame,
)

log = get_logger(__name__)

try:
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))
    from services.simulation.engine import SimulationEngine  # type: ignore
    _SIM_AVAILABLE = True
except Exception:
    _SIM_AVAILABLE = False


class SimulationService:
    def __init__(self, speed_factor: float = 60.0):
        self.speed_factor = speed_factor
        self._engine      = None
        self._thread: Optional[threading.Thread] = None
        self._clients: Set[asyncio.Queue] = set()
        self._loop:   Optional[asyncio.AbstractEventLoop] = None
        self._session_id: str  = str(uuid.uuid4())[:8]
        self._tick:       int  = 0
        self._running:    bool = False
        self._disruptions: List[dict] = []

    # ── Lifecycle ────────────────────────────────────────────────────────

    def start(self, corridor: str = "NDLS-CNB", seed: int = 42,
              disruptions: bool = True) -> str:
        if self._running:
            raise SimulationError("Simulation already running. Stop it first.")
        self._session_id = str(uuid.uuid4())[:8]
        self._tick       = 0
        self._disruptions.clear()
        self._engine     = None

        if _SIM_AVAILABLE:
            try:
                eng = SimulationEngine(corridor=corridor, seed=seed,
                                       enable_disruptions=disruptions)
                eng.reset()
                self._engine = eng
            except Exception as exc:
                log.warning("SimulationEngine init failed, using stub", error=str(exc))

        self._running = True
        self._thread  = threading.Thread(target=self._run_loop_sync, daemon=True)
        self._thread.start()
        log.info("Simulation started", session=self._session_id, corridor=corridor)
        return self._session_id

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        log.info("Simulation stopped", session=self._session_id)

    def pause(self) -> None:
        self._running = False

    def resume(self) -> None:
        if not self._running:
            self._running = True
            self._thread  = threading.Thread(target=self._run_loop_sync, daemon=True)
            self._thread.start()

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    # ── Disruption injection ─────────────────────────────────────────────

    def inject_disruption(self, dtype: str, section_id: Optional[str] = None,
                          station_id: Optional[str] = None, duration_min: float = 30.0,
                          severity: float = 1.0) -> DisruptionResponse:
        did = f"D{len(self._disruptions)+1:03d}"
        rec = {"disruption_id": did, "type": dtype, "section_id": section_id,
               "station_id": station_id, "duration_min": duration_min,
               "severity": severity, "status": "injected"}
        self._disruptions.append(rec)
        if self._engine:
            try:
                self._engine.inject_disruption(**rec)
            except Exception as exc:
                log.warning("Engine disruption failed", error=str(exc))
        return DisruptionResponse(**{k: v for k, v in rec.items()
                                    if k in DisruptionResponse.model_fields})

    # ── WebSocket subscription ───────────────────────────────────────────

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    # ── Tick loop (daemon thread) ────────────────────────────────────────

    def _run_loop_sync(self) -> None:
        interval = 1.0 / max(self.speed_factor, 1.0)
        while self._running:
            t0 = time.monotonic()
            self._tick += 1
            snapshot = self._build_snapshot()
            frame    = WsFrame(type="snapshot", payload=snapshot.model_dump(), tick=self._tick)
            msg      = frame.model_dump_json()
            loop = self._loop
            if loop and loop.is_running():
                for q in list(self._clients):
                    try:
                        loop.call_soon_threadsafe(q.put_nowait, msg)
                    except Exception:
                        pass
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))

    def _build_snapshot(self) -> SnapshotResponse:
        if self._engine:
            try:
                raw = self._engine.snapshot()
                trains = [
                    TrainPositionResponse(
                        train_id=t["train_id"], category=t.get("category", "express"),
                        section_id=t.get("section_id", "unknown"),
                        delay_min=t.get("delay_min", 0.0),
                        direction=t.get("direction", "DOWN"),
                        speed_kmh=t.get("speed_kmh", 70.0))
                    for t in raw.get("trains", [])
                ]
                return SnapshotResponse(tick=self._tick, trains=trains,
                                        disruptions=raw.get("disruptions", []),
                                        metrics=raw.get("metrics", {}))
            except Exception as exc:
                log.debug("Engine snapshot failed, stub fallback", error=str(exc))

        stub = [
            TrainPositionResponse(
                train_id=f"1230{i}", category="express",
                section_id=f"s{(self._tick // 10 + i) % 6 + 1}",
                delay_min=max(0.0, 5.0 * math.sin(self._tick * 0.1 + i)),
                direction="DOWN" if i % 2 == 0 else "UP", speed_kmh=70.0)
            for i in range(1, 6)
        ]
        return SnapshotResponse(
            tick=self._tick, trains=stub,
            disruptions=[d for d in self._disruptions if d["status"] == "active"],
            metrics={"total_delay_min": sum(t.delay_min for t in stub),
                     "on_time_pct": 0.75,
                     "cascade_count": float(len(self._disruptions))})

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def status(self) -> str:
        return "running" if self._running else "stopped"

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def tick(self) -> int:
        return self._tick
