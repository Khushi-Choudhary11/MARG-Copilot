"""
backend/api/v1/optimization.py
================================
REST endpoints for the MARG optimization engine.

POST /optimization/run           — full pipeline (CP-SAT + rerouter)
POST /optimization/conflicts     — detect conflicts only (no decisions)
GET  /optimization/health        — optimizer status
"""
from typing import List

from fastapi import APIRouter, Depends

from auth.dependencies import CurrentUser, require_auth
from core.dependencies import get_optimization
from models.requests import OptimizationRequest
from models.responses import ConflictResponse, OptimizationResponse
from services.optimization_service import OptimizationService

router = APIRouter(prefix="/optimization", tags=["optimization"])


@router.get("/health", summary="Optimizer availability")
def health(
    svc:  OptimizationService = Depends(get_optimization),
    user: CurrentUser         = Depends(require_auth),
):
    return {
        "cp_sat":   "available" if svc._engine else "unavailable",
        "rerouter": "available" if svc._engine else "unavailable",
    }


@router.post(
    "/run",
    response_model=OptimizationResponse,
    summary="Run full optimization (CP-SAT + emergency rerouting)",
)
def run_optimization(
    req:  OptimizationRequest,
    svc:  OptimizationService = Depends(get_optimization),
    user: CurrentUser         = Depends(require_auth),
):
    """
    Accepts the current network state (trains + sections) and returns:
    - Ranked list of actionable decisions (HOLD, REROUTE, PRECEDENCE, CROSSING)
    - Baseline vs. optimized delay
    - Conflict list

    The CP-SAT solver enforces:
    - Minimum headway between trains on shared sections
    - No-overlap on single-line (loop) sections
    - Priority weighting (Superfast > Mail > Express > Goods)

    Emergency rerouting activates for any blocked section.
    """
    result, _ = svc.optimize(req)
    return result


@router.post(
    "/conflicts",
    response_model=List[ConflictResponse],
    summary="Detect conflicts without generating decisions",
)
def detect_conflicts(
    req:  OptimizationRequest,
    svc:  OptimizationService = Depends(get_optimization),
    user: CurrentUser         = Depends(require_auth),
):
    """
    Lighter endpoint — runs only conflict detection (no CP-SAT solver).
    Useful for the frontend to highlight conflicting sections before
    requesting full optimization.
    """
    _, conflicts = svc.optimize(req)
    return conflicts
