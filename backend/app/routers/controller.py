from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user, require_role
from app.controller_state import controller_state

router = APIRouter(prefix="/api/controller", tags=["controller"])


class AutoModeRequest(BaseModel):
    enabled: bool


@router.get("/status")
def get_status(user: dict = Depends(get_current_user)):
    return {"auto_mode": controller_state.auto_mode}


@router.post("/auto-mode")
def set_auto_mode(req: AutoModeRequest, user: dict = Depends(require_role("admin", "controller"))):
    controller_state.set_auto_mode(req.enabled)
    return {"auto_mode": controller_state.auto_mode, "changed_by": user["name"]}
