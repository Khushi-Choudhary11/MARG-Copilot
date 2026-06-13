"""
Minimal in-process auth for the MVP (no DB, no Redis).

Three demo accounts covering the roles described in the platform architecture:
  - admin      / admin123      -> full access incl. user management view
  - controller / controller123 -> can apply AI recommendations, toggle auto-mode
  - viewer     / viewer123      -> read-only dashboards

Tokens are opaque UUIDs kept in a process-local dict. Restarting the backend
invalidates all sessions - acceptable for an MVP/demo.
"""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Header

ROLES = ("admin", "controller", "viewer")

USERS = {
    "admin": {"password": "admin123", "role": "admin", "name": "Admin User"},
    "controller": {"password": "controller123", "role": "controller", "name": "Section Controller"},
    "viewer": {"password": "viewer123", "role": "viewer", "name": "Viewer"},
}

# token -> {"username": ..., "role": ..., "name": ...}
SESSIONS: dict[str, dict] = {}


def login(username: str, password: str) -> dict:
    user = USERS.get(username)
    if not user or user["password"] != password:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = uuid.uuid4().hex
    session = {"username": username, "role": user["role"], "name": user["name"]}
    SESSIONS[token] = session
    return {"token": token, **session}


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    session = SESSIONS.get(token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return session


def require_role(*allowed_roles: str):
    def _checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions for this action")
        return user

    return _checker
