"""
backend/models/responses.py
============================
Pydantic v2 response schemas for all API modules.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    expires_in:   int            # seconds


class UserResponse(BaseModel):
    username: str
    role:     str


# ── Health ────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:   str = "ok"
    version:  str
    services: Dict[str, str]     # service_name → "ok" | "degraded" | "unavailable"


# ── Simulation ────────────────────────────────────────────────────────────

class SimulationStatusResponse(BaseModel):
    session_id:    str
    status:        str            # "running" | "paused" | "stopped"
    tick:          int            # current simulation tick (minutes)
    wall_time_s:   float
    n_trains:      int
    n_disruptions: int


class TrainPositionResponse(BaseModel):
    train_id:      str
    category:      str
    section_id:    str
    delay_min:     float
    direction:     str
    speed_kmh:     float


class SnapshotResponse(BaseModel):
    tick:          int
    trains:        List[TrainPositionResponse]
    disruptions:   List[Dict[str, Any]]
    metrics:       Dict[str, float]   # total_delay, on_time_pct, cascade_count …


class DisruptionResponse(BaseModel):
    disruption_id: str
    type:          str
    status:        str            # "injected" | "active" | "cleared"
    section_id:    Optional[str]
    duration_min:  float


# ── Prediction ────────────────────────────────────────────────────────────

class DelayPredictionResponse(BaseModel):
    train_id:    str
    section_id:  str
    pred_30:     Optional[float] = Field(None, description="Predicted delay in 30 min (minutes)")
    pred_60:     Optional[float] = None
    pred_120:    Optional[float] = None
    model_used:  str = "delay_predictor"


class BatchDelayResponse(BaseModel):
    predictions: List[DelayPredictionResponse]
    n_input:     int
    latency_ms:  float


class SectionCongestionResponse(BaseModel):
    section_id:          str
    congestion_score_h1: float = Field(..., ge=0.0, le=1.0)
    congestion_score_h2: Optional[float] = None
    congestion_score_h3: Optional[float] = None
    risk_level:          str    # "low" | "medium" | "high"


class CongestionResponse(BaseModel):
    sections:    List[SectionCongestionResponse]
    timestamp_min: float
    latency_ms:  float


# ── Optimization ──────────────────────────────────────────────────────────

class DecisionResponse(BaseModel):
    decision_type:   str
    train_id:        str
    section_id:      str
    detail:          str
    delay_saved_min: float
    hold_minutes:    float = 0.0
    alt_route:       Optional[List[str]] = None
    affected_trains: List[str] = []
    confidence:      float


class OptimizationResponse(BaseModel):
    status:          str          # "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "TIMEOUT" | "ERROR"
    decisions:       List[DecisionResponse]
    baseline_delay:  float
    optimized_delay: float
    delay_saved:     float
    solve_time_sec:  float
    n_conflicts:     int


class ConflictResponse(BaseModel):
    section_id:     str
    conflict_type:  str           # "blocked" | "crossing" | "headway"
    trains:         List[str]
    severity:       float


# ── Explainability ────────────────────────────────────────────────────────

class ExplanationResponse(BaseModel):
    train_id:    str
    section_id:  str
    action:      str             # short action label
    text:        str             # full NL justification paragraph
    risk:        str             # "Low" | "Medium" | "High"
    confidence:  float
    source:      str             # "claude" | "cache" | "template"
    latency_ms:  float


class BatchExplanationResponse(BaseModel):
    explanations: List[ExplanationResponse]
    n_input:      int
    n_claude:     int            # how many came from live Claude vs cache/template
    total_ms:     float


# ── WebSocket frames ──────────────────────────────────────────────────────

class WsFrame(BaseModel):
    """Envelope for all WebSocket messages from server → client."""
    type:    str             # "snapshot" | "disruption" | "recommendation" | "error" | "ping"
    payload: Dict[str, Any]
    tick:    int = 0
