"""
backend/services/explanation_service.py
=========================================
Bridges FastAPI explainability endpoints to ClaudeExplainer.
Handles async ↔ sync boundary and translates Pydantic ↔ optimizer types.
"""
from __future__ import annotations

import asyncio
import sys, os, time
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "optimizer"))

from core.errors import ExplanationError
from core.logging import get_logger
from models.requests import (
    ExplainRequest, SectionStateRequest, TrainStateRequest,
)
from models.responses import BatchExplanationResponse, ExplanationResponse

log = get_logger(__name__)

try:
    from problem import (                                    # type: ignore
        Decision, DecisionType, NetworkState,
        TrainState, SectionState,
    )
    from claude_explainer import ClaudeExplainer             # type: ignore
    from explanation_cache import ExplanationCache           # type: ignore
    _EXPL_AVAILABLE = True
except Exception as exc:
    log.warning("Explainer package unavailable", error=str(exc))
    _EXPL_AVAILABLE = False


# ── Translators ────────────────────────────────────────────────────────────

def _to_decision(req: ExplainRequest) -> "Decision":
    return Decision(
        decision_type   = DecisionType[req.decision_type],
        train_id        = req.train_id,
        section_id      = req.section_id,
        detail          = req.detail,
        delay_saved_min = req.delay_saved_min,
        hold_minutes    = req.hold_minutes,
        alt_route       = req.alt_route,
        affected_trains = req.affected_trains,
        confidence      = req.confidence,
    )


def _to_train(t: TrainStateRequest) -> "TrainState":
    return TrainState(
        train_id=t.train_id, category=t.category, priority=t.priority,
        direction=t.direction, current_section=t.current_section,
        current_delay=t.current_delay, sched_dep_min=t.sched_dep_min,
        remaining_route=t.remaining_route, sched_arrivals=t.sched_arrivals,
        sched_departures=t.sched_departures, travel_times=t.travel_times,
    )


def _to_section(s: SectionStateRequest) -> "SectionState":
    return SectionState(
        section_id=s.section_id, from_station=s.from_station,
        to_station=s.to_station, length_km=s.length_km,
        capacity_per_hr=s.capacity_per_hr, is_single_line=s.is_single_line,
        is_blocked=s.is_blocked, block_duration=s.block_duration,
        congestion_score=s.congestion_score,
    )


def _to_network_state(req: ExplainRequest) -> "NetworkState":
    trains   = {k: _to_train(v)   for k, v in req.trains.items()}
    sections = {k: _to_section(v) for k, v in req.sections.items()}
    return NetworkState(
        timestamp_min=req.timestamp_min,
        trains=trains, sections=sections,
        horizon_min=req.horizon_min,
    )


# ── Service ────────────────────────────────────────────────────────────────

class ExplanationService:

    def __init__(
        self,
        api_key:   Optional[str] = None,
        model:     str  = "claude-haiku-4-5-20251001",
        use_redis: bool = False,
        redis_url: str  = "redis://localhost:6379/0",
    ):
        self._api_key  = api_key
        self._model    = model
        self._explainer: Optional[object] = None

        if _EXPL_AVAILABLE:
            cache = ExplanationCache(use_redis=use_redis)
            self._explainer = ClaudeExplainer(
                api_key   = api_key,
                model     = model,
                use_redis = use_redis,
                cache     = cache,
            )

    def explain_one(self, req: ExplainRequest) -> ExplanationResponse:
        if not _EXPL_AVAILABLE or self._explainer is None:
            return self._stub_explanation(req)
        try:
            decision = _to_decision(req)
            state    = _to_network_state(req)
            result   = asyncio.run(self._explainer.explain_one(decision, state))
            return ExplanationResponse(
                train_id   = req.train_id,
                section_id = req.section_id,
                action     = result.action,
                text       = result.text,
                risk       = result.risk,
                confidence = result.confidence,
                source     = result.source,
                latency_ms = result.latency_ms,
            )
        except Exception as exc:
            log.error("Explanation failed", error=str(exc))
            raise ExplanationError(f"Explanation engine error: {exc}") from exc

    def explain_batch(
        self,
        reqs: List[ExplainRequest],
        max_concurrent: int = 4,
    ) -> BatchExplanationResponse:
        t0 = time.monotonic()
        results = [self.explain_one(r) for r in reqs]
        n_claude = sum(1 for r in results if r.source == "claude")
        return BatchExplanationResponse(
            explanations = results,
            n_input      = len(reqs),
            n_claude     = n_claude,
            total_ms     = (time.monotonic() - t0) * 1000,
        )

    def _stub_explanation(self, req: ExplainRequest) -> ExplanationResponse:
        action_map = {
            "HOLD":       f"Hold {req.train_id} at {req.section_id}",
            "REROUTE":    f"Reroute {req.train_id} around {req.section_id}",
            "PRECEDENCE": f"Give {req.train_id} precedence at {req.section_id}",
            "CROSSING":   f"Resolve crossing for {req.train_id} at {req.section_id}",
        }
        action = action_map.get(req.decision_type, req.decision_type)
        text   = (
            f"{action}. Estimated saving: {req.delay_saved_min:.0f} weighted delay-minutes. "
            f"Confidence: {req.confidence*100:.0f}%."
        )
        return ExplanationResponse(
            train_id=req.train_id, section_id=req.section_id,
            action=action, text=text, risk="Medium",
            confidence=req.confidence, source="stub", latency_ms=0.0,
        )
