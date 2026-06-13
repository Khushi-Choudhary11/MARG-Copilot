from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import get_current_user, login

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def do_login(req: LoginRequest):
    return login(req.username, req.password)


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user
