"""
backend/api/v1/prediction.py
==============================
REST endpoints for ML delay and congestion prediction.

GET  /prediction/health              — model status
POST /prediction/delay               — single delay prediction
POST /prediction/delay/batch         — batch delay predictions (≤500)
POST /prediction/congestion          — section congestion forecast
"""
from fastapi import APIRouter, Depends

from auth.dependencies import CurrentUser, require_auth
from core.dependencies import get_prediction
from models.requests import BatchDelayRequest, CongestionRequest, DelayPredictionRequest
from models.responses import (
    BatchDelayResponse, CongestionResponse, DelayPredictionResponse,
)
from services.prediction_service import PredictionService

router = APIRouter(prefix="/prediction", tags=["prediction"])


@router.get("/health", summary="Prediction model status")
def health(
    svc:  PredictionService = Depends(get_prediction),
    user: CurrentUser       = Depends(require_auth),
):
    return {
        "delay_model":      "loaded" if svc._predictor else "heuristic",
        "congestion_model": "heuristic",    # ST-GNN checkpoint optional
    }


@router.post("/delay", response_model=DelayPredictionResponse,
             summary="Predict delay for one train-section observation")
def predict_delay(
    req:  DelayPredictionRequest,
    svc:  PredictionService = Depends(get_prediction),
    user: CurrentUser       = Depends(require_auth),
):
    """
    Returns predicted delays at +30, +60, and +120 minutes.

    Uses the trained DelayPredictor neural network if a checkpoint exists
    at `services/ml/models/`; otherwise falls back to a calibrated heuristic.
    """
    return svc.predict_delay(req)


@router.post("/delay/batch", response_model=BatchDelayResponse,
             summary="Batch delay predictions (up to 500 observations)")
def predict_batch(
    req:  BatchDelayRequest,
    svc:  PredictionService = Depends(get_prediction),
    user: CurrentUser       = Depends(require_auth),
):
    return svc.predict_batch(req.observations)


@router.post("/congestion", response_model=CongestionResponse,
             summary="Predict congestion scores per section")
def predict_congestion(
    req:  CongestionRequest,
    svc:  PredictionService = Depends(get_prediction),
    user: CurrentUser       = Depends(require_auth),
):
    """
    Returns congestion scores (0–1) for each requested section at
    +1h, +2h, +3h horizons.  Scores ≥ 0.7 = high risk.
    """
    return svc.predict_congestion(req)
