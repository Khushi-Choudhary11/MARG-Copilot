"""
backend/auth/jwt.py
====================
JWT creation and verification using python-jose.

Tokens carry: sub (username), role, exp.
The demo auth flow (POST /auth/token) checks against config credentials;
swap in a real user DB for production.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from config import get_settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Password helpers ───────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


# ── Token helpers ──────────────────────────────────────────────────────────

def create_access_token(
    username: str,
    role:     str = "controller",
    expires:  Optional[timedelta] = None,
) -> str:
    cfg  = get_settings()
    exp  = datetime.now(timezone.utc) + (
        expires or timedelta(minutes=cfg.jwt_expire_min)
    )
    payload = {"sub": username, "role": role, "exp": exp}
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.  Raises JWTError on invalid/expired token.
    Returns the payload dict (sub, role, exp).
    """
    cfg = get_settings()
    return jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])


# ── Demo user authentication ───────────────────────────────────────────────

def authenticate_demo_user(username: str, password: str) -> Optional[str]:
    """
    Returns a JWT if credentials match the demo account, else None.
    Replace with a real database lookup in production.
    """
    cfg = get_settings()
    if username == cfg.demo_username and password == cfg.demo_password:
        return create_access_token(username, role="controller")
    return None
