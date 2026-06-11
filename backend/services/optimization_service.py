"""
backend/services/optimization_service.py
==========================================
Bridges the FastAPI optimization endpoints to the services/optimizer package.
Translates Pydantic request models → optimizer dataclasses → Pydantic responses.
"""
from __future__ import annotations

import sys, os, time
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "optimizer"))

from core.errors import OptimizationError
from core.logging import get_logger
from models.requests import OptimizationRequest, SectionStateRequest, TrainStateRequest
from models.responses import ConflictResponse, DecisionResponse, OptimizationResponse

log = get_logger(__name__)

try:
    from problem import (                                     # type: ignore
        NetworkState, TrainState, SectionState,
        Decision, DecisionType, OptStatus,
    )
    from engine import OptimizationEngine                     # type: ignore
    from graph_utils import detect_conflicts                  # type: ignore
    _OPT_AVAILABLE = True
except Exception as exc:
    log.warning("Optimizer package unavailable", error=str(exc))
    _OPT_AVAILABLE = False


# ── Translators ────────────────────────────────────────────────────────────

def _to_train_state(t: TrainStateRequest) -> "TrainState":
    return TrainState(
        train_id         = t.train_id,
        category         = t.category,
        priority         = t.priority,
        direction        = t.direction,
        current_section  = t.current_section,
        current_delay    = t.current_delay,
        sched_dep_min    = t.sched_dep_min,
        remaining_route  = t.remaining_route,
        sched_arrivals   = t.sched_arrivals,
        sched_departures = t.sched_departures,
        travel_times     = t.travel_times,
    )


def _to_section_state(s: SectionStateRequest) -> "SectionState":
    return SectionState(
        section_id      = s.section_id,
        from_station    = s.from_station,
        to_station      = s.to_station,
        length_km       = s.length_km,
        capacity_per_hr = s.capacity_per_hr,
        is_single_line  = s.is_single_line,
        is_blocked      = s.is_blocked,
        block_duration  = s.block_duration,
        congestion_score = s.congestion_score,
    )


def _to_decision_response(d: "Decision") -> DecisionResponse:
    return DecisionResponse(
        decision_type    = d.decision_type.name,
        train_id         = d.train_id,
        section_id       = d.section_id,
        detail           = d.detail,
        delay_saved_min  = d.delay_saved_min,
        hold_minutes     = d.hold_minutes,
        alt_route        = d.alt_route,
        affected_trains  = d.affected_trains or [],
        confidence       = d.confidence,
    )


# ── Service ────────────────────────────────────────────────────────────────

class OptimizationService:
    """
    Singleton created at startup.  The underlying OptimizationEngine is
    stateless so a single instance serves all requests.
    """

    def __init__(self):
        self._engine = OptimizationEngine() if _OPT_AVAILABLE else None

    def optimize(self, req: OptimizationRequest) -> Tuple[OptimizationResponse, List[ConflictResponse]]:
        if not _OPT_AVAILABLE or self._engine is None:
            return self._stub_response(req), []

        try:
            trains   = {k: _to_train_state(v)   for k, v in req.trains.items()}
            sections = {k: _to_section_state(v) for k, v in req.sections.items()}
            state    = NetworkState(
                timestamp_min = req.timestamp_min,
                trains        = trains,
                sections      = sections,
                horizon_min   = req.horizon_min,
                min_headway   = req.min_headway,
            )

            result, conflicts = self._engine.optimize(state)

            decisions = [_to_decision_response(d) for d in result.decisions]
            conflict_resp = [
                ConflictResponse(
                    section_id    = c.section_id,
                    conflict_type = c.conflict_type,
                    trains        = list(c.trains),
                    severity      = c.severity,
                )
                for c in conflicts
            ]

            return (
                OptimizationResponse(
                    status          = result.status.name,
                    decisions       = decisions,
                    baseline_delay  = result.baseline_delay,
                    optimized_delay = result.objective_value,
                    delay_saved     = result.delay_saved,
                    solve_time_sec  = result.solve_time_sec,
                    n_conflicts     = result.n_conflicts,
                ),
                conflict_resp,
            )

        except Exception as exc:
            log.error("Optimization failed", error=str(exc))
            raise OptimizationError(f"Optimization engine error: {exc}") from exc

    def _stub_response(self, req: OptimizationRequest) -> OptimizationResponse:
        """Fallback when optimizer package is unavailable."""
        return OptimizationResponse(
            status="UNAVAILABLE", decisions=[],
            baseline_delay=0.0, optimized_delay=0.0,
            delay_saved=0.0, solve_time_sec=0.0, n_conflicts=0,
        )
