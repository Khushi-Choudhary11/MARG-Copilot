"""
backend/api/v1/auth.py
=======================
POST /api/v1/auth/token   — issue JWT
GET  /api/v1/auth/me      — current user info
"""
from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from auth.dependencies import CurrentUser, require_auth
from auth.jwt import authenticate_demo_user
from config import get_settings
from core.errors import AuthError
from models.responses import TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse, summary="Obtain JWT access token")
def login(form: OAuth2PasswordRequestForm = Depends()):
    """
    Standard OAuth2 password flow.  Returns a Bearer JWT.

    Demo credentials: username=`controller`, password=`marg2026`
    (set via `DEMO_USERNAME` / `DEMO_PASSWORD` env vars).
    """
    token = authenticate_demo_user(form.username, form.password)
    if not token:
        raise AuthError("Invalid username or password.")
    cfg = get_settings()
    return TokenResponse(
        access_token=token,
        expires_in=cfg.jwt_expire_min * 60,
    )


@router.get("/me", response_model=UserResponse, summary="Current user info")
def me(user: CurrentUser = Depends(require_auth)):
    return UserResponse(username=user.username, role=user.role)
