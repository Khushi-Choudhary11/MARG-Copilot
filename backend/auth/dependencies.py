"""
backend/auth/dependencies.py
==============================
FastAPI dependency for JWT authentication.

Usage in a route:
    @router.get("/protected")
    def protected(user: CurrentUser = Depends(require_auth)):
        return {"hello": user.username}

Roles:
    "controller"  — standard section controller (most endpoints)
    "admin"       — can trigger simulation resets, config changes
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, WebSocket
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from auth.jwt import decode_token
from core.errors import AuthError, ForbiddenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@dataclass
class CurrentUser:
    username: str
    role:     str


# ── Dependencies ──────────────────────────────────────────────────────────

def _decode(token: str) -> CurrentUser:
    try:
        payload = decode_token(token)
    except JWTError as exc:
        raise AuthError("Invalid or expired token.") from exc
    username = payload.get("sub")
    role     = payload.get("role", "controller")
    if not username:
        raise AuthError("Token missing 'sub' claim.")
    return CurrentUser(username=username, role=role)


def require_auth(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    """Require a valid JWT; return CurrentUser.  Used for REST endpoints."""
    return _decode(token)


def require_admin(user: CurrentUser = Depends(require_auth)) -> CurrentUser:
    """Require role='admin'."""
    if user.role != "admin":
        raise ForbiddenError("Admin role required.")
    return user


# ── WebSocket auth (token passed as query param) ──────────────────────────

async def ws_auth(websocket: WebSocket) -> Optional[CurrentUser]:
    """
    Extract and verify JWT from WebSocket query param `?token=<jwt>`.
    Returns CurrentUser or closes the socket with 4001 if invalid.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return None
    try:
        return _decode(token)
    except AuthError:
        await websocket.close(code=4001)
        return None
