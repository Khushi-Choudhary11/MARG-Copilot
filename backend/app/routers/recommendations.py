from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user, require_role
from app.controller_state import controller_state
from app.schemas import Recommendation
from app.simulation import build_snapshot

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def _severity(delay: float) -> str | None:
    if delay >= 30:
        return "critical"
    if delay >= 10:
        return "warning"
    return None


def _suggested_action(train_type: str | None, severity: str, station: str | None) -> str:
    if severity == "critical":
        if train_type in ("Rajdhani", "Shatabdi", "Vande Bharat", "Duronto"):
            return f"Grant priority pass through {station}; hold lower-priority traffic on adjacent loop lines."
        return f"Consider short-term hold at {station} to regularize, or reassign loop line to avoid platform conflict."
    return f"Monitor closely approaching {station}; no immediate action needed."


@router.get("", response_model=list[Recommendation])
def get_recommendations():
    snapshot = build_snapshot()
    recs: list[Recommendation] = []
    for train in snapshot.trains:
        if train.status != "running" or train.predicted_delay_next is None:
            continue
        severity = _severity(train.predicted_delay_next)
        if severity is None:
            continue
        recs.append(
            Recommendation(
                id=f"{train.train_number}-{train.next_station}",
                train_number=train.train_number,
                train_name=train.train_name,
                station_code=train.next_station or "",
                severity=severity,
                predicted_delay=train.predicted_delay_next,
                prediction_source=train.prediction_source or "fallback",
                message=(
                    f"{train.train_name or train.train_number} ({train.train_number}) is "
                    f"predicted to arrive at {train.next_station} ~{train.predicted_delay_next:.0f} min late."
                ),
                suggested_action=_suggested_action(train.train_type, severity, train.next_station),
            )
        )

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    recs.sort(key=lambda r: (severity_rank.get(r.severity, 9), -r.predicted_delay))
    return recs


@router.post("/{rec_id}/apply")
def apply_recommendation(rec_id: str, user: dict = Depends(require_role("admin", "controller"))):
    """Controller/admin manually applies (acknowledges) a recommendation."""
    recs = {r.id: r for r in get_recommendations()}
    rec = recs.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation no longer active")
    if controller_state.has_actioned(rec_id):
        raise HTTPException(status_code=409, detail="Recommendation already actioned")
    entry = controller_state.log_action(recommendation=rec.model_dump(), actor=user["name"], auto=False)
    return entry


@router.get("/log")
def get_action_log(user: dict = Depends(get_current_user)):
    return controller_state.action_log
