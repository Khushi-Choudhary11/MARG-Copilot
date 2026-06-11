"""
backend/config.py
==================
Centralised settings loaded from environment variables / .env file.
All modules import `get_settings()` — never import Settings directly,
so the singleton can be overridden in tests.

Usage
-----
    from config import get_settings
    cfg = get_settings()
    print(cfg.jwt_secret)
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────────────────
    app_name:     str  = "MARG Railway AI Backend"
    app_version:  str  = "0.1.0"
    debug:        bool = False
    log_level:    str  = "INFO"

    # ── Server ───────────────────────────────────────────────────────────────
    host:         str  = "0.0.0.0"
    port:         int  = 8000
    workers:      int  = 1

    # ── CORS ─────────────────────────────────────────────────────────────────
    # "*" allows dev tunnels, Vercel previews, and local dev without extra config.
    # Narrow this in production.
    cors_origins: List[str] = ["*"]

    # ── Auth (JWT) ───────────────────────────────────────────────────────────
    jwt_secret:       str   = "change-me-in-production-at-least-32-chars!!"
    jwt_algorithm:    str   = "HS256"
    jwt_expire_min:   int   = 1440      # 24 hours — safe for demo sessions
    # Demo credentials (replace with real user store in prod)
    demo_username:    str   = "controller"
    demo_password:    str   = "marg2026"

    # ── Anthropic / Claude ───────────────────────────────────────────────────
    anthropic_api_key:   Optional[str] = None
    claude_model:        str = "claude-haiku-4-5-20251001"
    claude_timeout_sec:  float = 8.0

    # ── Paths (relative to project root) ────────────────────────────────────
    project_root:    Path = Path(__file__).parent.parent
    ml_model_dir:    Path = Path("services/ml/models")
    csv_data_path:   Path = Path("railway_ops.csv")

    # ── Redis ────────────────────────────────────────────────────────────────
    redis_url:       str  = "redis://localhost:6379/0"
    use_redis_cache: bool = False      # False = LRU only (no Redis required)

    # ── Simulation ───────────────────────────────────────────────────────────
    sim_tick_seconds:    float = 1.0   # wall-clock seconds per simulated minute
    sim_max_clients:     int   = 10    # max concurrent WebSocket clients

    # ── Rate limiting ────────────────────────────────────────────────────────
    rate_limit_per_min:  int   = 120

    @field_validator("ml_model_dir", "csv_data_path", mode="before")
    @classmethod
    def _resolve(cls, v):
        return Path(v)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
