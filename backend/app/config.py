"""
Central configuration for the NDLS<->CNB Digital Twin MVP backend.

No Redis / Celery for the MVP: live state is recomputed on demand from a
"demo day" of real data (drawn from new_final_master_data.csv) and broadcast
over a plain in-process WebSocket connection manager via an asyncio task.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / "backend" / ".env")
DATA_DIR = BASE_DIR / "data" / "processed"

# Small (~1.3k row) extract of new_final_master_data.csv containing only the
# demo-day's corridor rows - committed to git so deployments work without
# needing the full ~130MB dataset. Override with MASTER_DATA_URL to load a
# larger/different dataset (e.g. a hosted copy of new_final_master_data.csv).
MASTER_DATA_PATH = DATA_DIR / "demo_day_master_data.csv"
MASTER_DATA_URL = os.environ.get("MASTER_DATA_URL", "")
STATIONS_PATH = DATA_DIR / "stations.csv"
TRAIN_MASTER_PATH = DATA_DIR / "train_master.csv"
TRAIN_ROUTES_PATH = DATA_DIR / "train_routes.csv"
STATION_INFRA_PATH = DATA_DIR / "station_infrastructure.csv"
SECTION_INFRA_PATH = DATA_DIR / "section_infrastructure.csv"

MODEL_PATH = BASE_DIR / "best_delay_model.pkl"
MODEL_METADATA_PATH = BASE_DIR / "best_delay_model_metadata.pkl"

# Corridor stations, in DOWN (NDLS -> CNB) order.
CORRIDOR_STATIONS = ["NDLS", "GZB", "ALJN", "TDL", "ETW", "CNB"]

# The "demo day": a real date from new_final_master_data.csv whose features
# (weather, congestion, lag/rolling delays, etc.) drive the live simulation
# and the model predictions. Overridable via env var.
DEMO_DATE = os.environ.get("DEMO_DATE", "2026-06-10")

# How fast simulated time moves relative to wall-clock time. At 180x, a
# 24-hour service day completes in 8 real minutes.
SIM_SPEED = float(os.environ.get("SIM_SPEED", "180"))

# How often (seconds) the WebSocket broadcasts a fresh twin snapshot.
TWIN_BROADCAST_INTERVAL = float(os.environ.get("TWIN_BROADCAST_INTERVAL", "3"))

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:5183").split(",")

# Optional - if unset, /api/ai endpoints fall back to template-based
# explanations and the frontend falls back to puter.js client-side AI.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
