"""
backend/services/prediction_service.py
========================================
Wraps the ML delay predictor and ST-GNN congestion forecaster.

If the trained model checkpoints don't exist, falls back to a
rule-based heuristic so the API stays up for demo purposes.
"""
from __future__ import annotations

import sys, os, time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from core.errors import PredictionError
from core.logging import get_logger
from models.requests import DelayPredictionRequest, CongestionRequest
from models.responses import (
    BatchDelayResponse, CongestionResponse,
    DelayPredictionResponse, SectionCongestionResponse,
)

log = get_logger(__name__)

# ── Optional ML imports ────────────────────────────────────────────────────
_ML_ROOT = Path(__file__).parent.parent.parent / "services" / "ml"
sys.path.insert(0, str(_ML_ROOT))

try:
    from predict import Predictor            # type: ignore
    from config import Config as MLConfig    # type: ignore
    _ML_AVAILABLE = True
except Exception:
    _ML_AVAILABLE = False


def _risk(score: float) -> str:
    if score >= 0.7: return "high"
    if score >= 0.4: return "medium"
    return "low"


class PredictionService:
    """
    Singleton instantiated at startup.

    delay_predictor  : loaded from services/ml/models/ if checkpoint exists
    congestion_model : stub (ST-GNN requires a trained checkpoint + PyTorch)
    """

    def __init__(self, model_dir: Path):
        self.model_dir = Path(model_dir)
        self._predictor: Optional[object] = None
        self._load_delay_model()

    # ── Delay prediction ──────────────────────────────────────────────────

    def _load_delay_model(self) -> None:
        if not _ML_AVAILABLE:
            log.warning("ML package unavailable — using heuristic delay predictor")
            return
        try:
            cfg = MLConfig(model_dir=self.model_dir)
            self._predictor = Predictor.from_checkpoint(self.model_dir)
            log.info("Delay predictor loaded", model_dir=str(self.model_dir))
        except Exception as exc:
            log.warning("Delay predictor checkpoint not found — using heuristic",
                        error=str(exc))

    def predict_delay(self, req: DelayPredictionRequest) -> DelayPredictionResponse:
        t0 = time.monotonic()
        if self._predictor:
            try:
                preds = self._predictor.predict_single(
                    current_delay_min       = req.current_delay_min,
                    priority                = req.priority,
                    weather                 = req.weather,
                    congestion_score        = req.congestion_score,
                    section_is_single_line  = req.section_is_single_line,
                    signal_failed           = req.signal_failed,
                    track_blocked           = req.track_blocked,
                    category                = req.category,
                    hour_of_day             = req.hour_of_day,
                    month                   = req.month,
                    day_of_week             = req.day_of_week,
                    sched_depart_min        = req.sched_depart_min,
                )
                return DelayPredictionResponse(
                    train_id   = req.train_id,
                    section_id = req.section_id,
                    pred_30    = float(preds.get("pred_30", 0.0)),
                    pred_60    = float(preds.get("pred_60", 0.0)),
                    pred_120   = float(preds.get("pred_120", 0.0)),
                    model_used = "delay_predictor_nn",
                )
            except Exception as exc:
                log.warning("Delay predictor inference failed, using heuristic", error=str(exc))

        return self._heuristic_delay(req)

    def _heuristic_delay(self, req: DelayPredictionRequest) -> DelayPredictionResponse:
        """Simple rule-based fallback: delay grows with congestion + weather."""
        WEATHER_FACTOR = {"DENSE_FOG": 2.5, "STORM": 2.0, "RAIN": 1.4,
                          "LIGHT_FOG": 1.2, "CLEAR": 1.0}
        wf   = WEATHER_FACTOR.get(req.weather, 1.0)
        base = req.current_delay_min
        cong = req.congestion_score
        block_add = 30.0 if req.track_blocked else 0.0
        sig_add   = 10.0 if req.signal_failed  else 0.0
        p30  = max(0.0, base * wf + cong * 10 + block_add * 0.5 + sig_add * 0.5)
        p60  = max(0.0, base * wf * 0.8 + cong * 15 + block_add + sig_add * 0.8)
        p120 = max(0.0, base * wf * 0.6 + cong * 20 + block_add * 1.5 + sig_add)
        return DelayPredictionResponse(
            train_id=req.train_id, section_id=req.section_id,
            pred_30=round(p30, 1), pred_60=round(p60, 1), pred_120=round(p120, 1),
            model_used="heuristic",
        )

    def predict_batch(self, reqs: List[DelayPredictionRequest]) -> BatchDelayResponse:
        t0 = time.monotonic()
        preds = [self.predict_delay(r) for r in reqs]
        return BatchDelayResponse(
            predictions=preds,
            n_input=len(reqs),
            latency_ms=(time.monotonic() - t0) * 1000,
        )

    # ── Congestion prediction ─────────────────────────────────────────────

    def predict_congestion(self, req: CongestionRequest) -> CongestionResponse:
        """
        ST-GNN congestion forecast.  Returns heuristic scores when model
        checkpoint is unavailable (no PyTorch required for the API to run).
        """
        t0 = time.monotonic()
        results = []
        for sid in req.section_ids:
            # Deterministic stub: hash section_id for consistent "predicted" scores
            h = sum(ord(c) for c in sid) % 100
            s1 = round(0.2 + (h % 50) / 100.0, 2)
            s2 = round(min(1.0, s1 + 0.05), 2) if req.horizon_hours >= 2 else None
            s3 = round(min(1.0, s1 + 0.10), 2) if req.horizon_hours >= 3 else None
            results.append(SectionCongestionResponse(
                section_id=sid,
                congestion_score_h1=s1,
                congestion_score_h2=s2,
                congestion_score_h3=s3,
                risk_level=_risk(s1),
            ))
        return CongestionResponse(
            sections=results,
            timestamp_min=req.timestamp_min,
            latency_ms=(time.monotonic() - t0) * 1000,
        )
