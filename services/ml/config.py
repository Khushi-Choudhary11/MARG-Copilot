"""
services/ml/config.py
=====================
Central hyperparameter and path configuration for the MARG delay
prediction model.  Modify this file — don't scatter constants around.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Feature lists — kept here so dataset.py and model.py stay in sync
# ---------------------------------------------------------------------------

WEATHER_CLASSES = [
    "CLEAR", "LIGHT_FOG", "MODERATE_FOG", "DENSE_FOG",
    "LIGHT_RAIN", "HEAVY_RAIN", "STORM",
]
CATEGORY_CLASSES = ["superfast", "mail", "express", "goods"]
N_WEATHER  = len(WEATHER_CLASSES)   # 7
N_CATEGORY = len(CATEGORY_CLASSES)  # 4

# Numerical features fed to the model (after cyclic encoding and scaling)
NUMERICAL_FEATURES = [
    # Current train state
    "arrive_delay_min",
    "depart_delay_min",
    "cumulative_delay_min",
    "upstream_delay_min",
    # Section characteristics
    "cascade_factor",
    "congestion_score",
    "weather_speed_factor",
    "section_length_km",
    "section_capacity_per_hr",
    "section_is_single_line",
    # Disruptions
    "signal_failed",
    "track_blocked",
    # Cyclic time encodings  (4 pairs = 8 floats)
    "hour_sin", "hour_cos",
    "month_sin", "month_cos",
    "dow_sin", "dow_cos",
    "sched_dep_sin", "sched_dep_cos",   # position in day
    # Misc
    "is_weekend",
    "priority",
    "direction",          # 1=UP, 0=DOWN
]
N_NUMERICAL = len(NUMERICAL_FEATURES)  # 23


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class Config:
    # ── Paths ────────────────────────────────────────────────────────────────
    data_path:  Path = Path("railway_ops.csv")
    model_dir:  Path = Path("models")
    model_name: str  = "delay_predictor"

    # ── Prediction horizons (minutes ahead) ─────────────────────────────────
    horizons:        list[int]   = field(default_factory=lambda: [30, 60, 120])
    horizon_weights: list[float] = field(default_factory=lambda: [1.0, 0.8, 0.6])
    horizon_tol:     int = 30    # max minutes gap to consider a horizon valid

    # ── Model architecture ────────────────────────────────────────────────────
    embed_dim_weather:  int = 8
    embed_dim_category: int = 6
    hidden_dims:  list[int] = field(default_factory=lambda: [256, 128, 64])
    head_hidden:  int = 32
    dropout:      float = 0.25
    use_residual: bool  = True   # residual connections in trunk

    # ── Training ──────────────────────────────────────────────────────────────
    epochs:       int   = 60
    batch_size:   int   = 2048
    lr:           float = 3e-4
    weight_decay: float = 1e-4
    huber_delta:  float = 10.0   # Huber loss delta (minutes)
    patience:     int   = 10     # early-stopping patience (val loss)
    grad_clip:    float = 5.0

    # ── Data split (by date, not random — prevents leakage) ─────────────────
    val_months:  list[int] = field(default_factory=lambda: [11])     # Nov
    test_months: list[int] = field(default_factory=lambda: [12])     # Dec
    # Jan–Oct used for training

    # ── Reproducibility ───────────────────────────────────────────────────────
    seed:   int = 42
    device: str = "auto"   # auto | cpu | cuda | mps

    # ── Misc ─────────────────────────────────────────────────────────────────
    num_workers: int = 0   # DataLoader workers (0 = main process)
    log_every:   int = 5   # print train metrics every N epochs

    def resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch
            if torch.cuda.is_available():    return "cuda"
            if torch.backends.mps.is_available(): return "mps"
        except Exception:
            pass
        return "cpu"

    def model_path(self) -> Path:
        return Path(self.model_dir) / f"{self.model_name}.pt"

    def scaler_path(self) -> Path:
        return Path(self.model_dir) / f"{self.model_name}_scaler.pkl"
