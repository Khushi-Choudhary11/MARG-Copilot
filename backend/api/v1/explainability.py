"""
backend/api/v1/explainability.py
==================================
REST endpoints for Claude-powered recommendation explanations.

POST /explainability/explain        — explain one decision
POST /explainability/explain/batch  — explain multiple decisions concurrently
GET  /explainability/health         — Claude API + cache status
GET  /explainability/cache/stats    — explanation cache hit rates
"""
from fastapi import APIRouter, Depends

from auth.dependencies import CurrentUser, require_auth
from core.dependencies import get_explanation
from models.requests import BatchExplainRequest, ExplainRequest
from models.responses import BatchExplanationResponse, ExplanationResponse
from services.explanation_service import ExplanationService

router = APIRouter(prefix="/explainability", tags=["explainability"])


@router.get("/health", summary="Explainer availability and Claude API status")
def health(
    svc:  ExplanationService = Depends(get_explanation),
    user: CurrentUser        = Depends(require_auth),
):
    claude_live = bool(
        svc._explainer
        and getattr(svc._explainer, "_client", None) is not None
    )
    return {
        "claude_api":   "live"      if claude_live   else "unavailable",
        "fallback":     "template",
        "cache":        "active",
    }


@router.get("/cache/stats", summary="LRU and Redis cache statistics")
def cache_stats(
    svc:  ExplanationService = Depends(get_explanation),
    user: CurrentUser        = Depends(require_auth),
):
    if svc._explainer and hasattr(svc._explainer, "cache"):
        return svc._explainer.cache.stats()
    return {"lru": {}, "redis_live": False}


@router.post(
    "/explain",
    response_model=ExplanationResponse,
    summary="Generate a human-readable explanation for one optimizer decision",
)
def explain_one(
    req:  ExplainRequest,
    svc:  ExplanationService = Depends(get_explanation),
    user: CurrentUser        = Depends(require_auth),
):
    """
    Passes the decision through the three-tier explanation pipeline:

    1. **Cache** — returns instantly if an identical decision was recently explained
    2. **Claude API** — generates a contextual NL justification (3–5 sentences)
    3. **Template fallback** — rule-based text if Claude is unavailable

    The `source` field in the response indicates which tier served the request.

    Example output:
    > *"Hold 12309 at Aligarh loop for 6 minutes, clearing the section for Rajdhani
    > 12951. 12951 holds higher priority and connects to 5 downstream services;
    > letting it pass first saves 41 cumulative delay-minutes. Confirm loop is clear
    > before issuing line-clear. Risk: Low."*
    """
    return svc.explain_one(req)


@router.post(
    "/explain/batch",
    response_model=BatchExplanationResponse,
    summary="Explain multiple decisions concurrently (up to 20)",
)
def explain_batch(
    req:  BatchExplainRequest,
    svc:  ExplanationService = Depends(get_explanation),
    user: CurrentUser        = Depends(require_auth),
):
    """
    Explains up to 20 decisions in parallel (bounded by `max_concurrent`).
    Typically called immediately after `/optimization/run` to enrich all
    decisions before displaying them in the Control Tower UI.
    """
    return svc.explain_batch(req.decisions, req.max_concurrent)
