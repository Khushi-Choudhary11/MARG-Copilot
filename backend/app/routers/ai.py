from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.ai_assistant import ask, is_configured
from app.auth import get_current_user
from app.routers.recommendations import get_recommendations
from app.simulation import build_snapshot

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AskRequest(BaseModel):
    question: str


@router.get("/status")
def status():
    return {"claude_configured": is_configured()}


@router.post("/ask")
async def ask_assistant(req: AskRequest, user: dict = Depends(get_current_user)):
    snapshot = build_snapshot()
    recs = get_recommendations()
    context = {
        "sim_time": snapshot.sim_time,
        "running_trains": len([t for t in snapshot.trains if t.status == "running"]),
        "recommendations": [r.model_dump() for r in recs[:5]],
    }
    result = await ask(req.question, context)
    return result
