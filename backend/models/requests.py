"""
backend/models/requests.py
===========================
Pydantic v2 request schemas for all API modules.
"""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


# ── Auth ──────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    username: str = Field(..., examples=["controller"])
    password: str = Field(..., examples=["marg2026"])


# ── Simulation ────────────────────────────────────────────────────────────

class SimulationStartRequest(BaseModel):
    corridor:       str   = Field("NDLS-CNB", description="Corridor ID to simulate")
    speed_factor:   float = Field(60.0, ge=1.0, le=3600.0,
                                  description="Simulated minutes per wall-clock second")
    seed:           int   = Field(42, description="Random seed for reproducibility")
    disruptions:    bool  = Field(True, description="Enable stochastic disruption injection")


class DisruptionRequest(BaseModel):
    """Inject a manual disruption into a running simulation."""
    type:        str  = Field(..., examples=["TRACK_BLOCK", "FOG", "SIGNAL_FAIL"])
    section_id:  Optional[str]  = Field(None, description="Target section (for TRACK_BLOCK)")
    station_id:  Optional[str]  = Field(None, description="Target station (for SIGNAL_FAIL)")
    duration_min: float = Field(30.0, ge=1.0, le=240.0)
    severity:    float  = Field(1.0, ge=0.1, le=1.0)

    @model_validator(mode="after")
    def _check_target(self):
        if self.type == "TRACK_BLOCK" and not self.section_id:
            raise ValueError("section_id required for TRACK_BLOCK disruption")
        if self.type == "SIGNAL_FAIL" and not self.station_id:
            raise ValueError("station_id required for SIGNAL_FAIL disruption")
        return self


# ── Prediction ────────────────────────────────────────────────────────────

class DelayPredictionRequest(BaseModel):
    """Predict future delay for a single train-section observation."""
    train_id:               str
    section_id:             str
    current_delay_min:      float = Field(0.0, ge=0.0)
    priority:               int   = Field(2, ge=1, le=4)
    category:               str   = Field("express",
                                          examples=["superfast", "mail", "express", "goods"])
    weather:                str   = Field("CLEAR",
                                          examples=["CLEAR","RAIN","DENSE_FOG","LIGHT_FOG","STORM"])
    congestion_score:       float = Field(0.0, ge=0.0, le=1.0)
    section_is_single_line: bool  = False
    signal_failed:          bool  = False
    track_blocked:          bool  = False
    hour_of_day:            float = Field(10.0, ge=0.0, le=23.99)
    month:                  float = Field(6.0, ge=1.0, le=12.0)
    day_of_week:            float = Field(2.0, ge=0.0, le=6.0)
    sched_depart_min:       float = Field(600.0, ge=0.0, le=1439.0)


class BatchDelayRequest(BaseModel):
    observations: List[DelayPredictionRequest] = Field(..., min_length=1, max_length=500)


class CongestionRequest(BaseModel):
    """Predict congestion for a set of sections at a given time."""
    section_ids:   List[str]
    horizon_hours: int = Field(1, ge=1, le=3, description="1, 2, or 3 hours ahead")
    timestamp_min: float = Field(0.0, ge=0.0, le=1439.0)


# ── Optimization ──────────────────────────────────────────────────────────

class TrainStateRequest(BaseModel):
    train_id:          str
    category:          str   = "express"
    priority:          int   = 2
    direction:         str   = "DOWN"
    current_section:   str
    current_delay:     float = 0.0
    sched_dep_min:     float = 600.0
    remaining_route:   List[str]
    sched_arrivals:    Dict[str, float] = {}
    sched_departures:  Dict[str, float] = {}
    travel_times:      Dict[str, float] = {}


class SectionStateRequest(BaseModel):
    section_id:       str
    from_station:     str
    to_station:       str
    length_km:        float = 50.0
    capacity_per_hr:  int   = 60
    is_single_line:   bool  = False
    is_blocked:       bool  = False
    block_duration:   float = 0.0
    congestion_score: float = 0.0


class OptimizationRequest(BaseModel):
    timestamp_min: float = Field(..., ge=0.0, le=1439.0)
    horizon_min:   int   = Field(120, ge=30, le=240)
    trains:        Dict[str, TrainStateRequest]
    sections:      Dict[str, SectionStateRequest]
    min_headway:   int   = Field(3, ge=1, le=10)


# ── Explainability ────────────────────────────────────────────────────────

class ExplainRequest(BaseModel):
    """Request a Claude-powered explanation for one optimizer decision."""
    decision_type:      str   = Field(..., examples=["HOLD","REROUTE","PRECEDENCE","CROSSING"])
    train_id:           str
    section_id:         str
    detail:             str   = ""
    delay_saved_min:    float = 0.0
    hold_minutes:       float = 0.0
    alt_route:          Optional[List[str]] = None
    affected_trains:    List[str] = []
    confidence:         float = 0.9
    # Minimal context needed to build the explanation prompt
    timestamp_min:      float = 600.0
    horizon_min:        int   = 120
    trains:             Dict[str, TrainStateRequest] = {}
    sections:           Dict[str, SectionStateRequest] = {}


class BatchExplainRequest(BaseModel):
    decisions:  List[ExplainRequest] = Field(..., min_length=1, max_length=20)
    max_concurrent: int = Field(4, ge=1, le=8)
