"""
services/congestion/config.py
==============================
Configuration for the MARG Spatio-Temporal GNN congestion forecaster.

Graph:  48 directed sections as nodes, edges = consecutive sections
Time:   hourly snapshots, 6-hour input window, predict +1h / +2h / +3h
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


# ── Node feature names (dynamic — change every hour) ────────────────────────
DYNAMIC_FEATURES = [
    "congestion_score",     # primary signal [0,1]
    "train_count",          # trains on section this hour (normalised)
    "capacity_util",        # train_count / section_capacity_per_hr
    "weather_speed_factor", # mean [0,1]
    "signal_failed",        # max (any failure = 1)
    "track_blocked",        # max
    "arrive_delay_mean",    # mean arrival delay (minutes, normalised)
    "time_sin",             # cyclic hour encoding
    "time_cos",
]
N_DYNAMIC = len(DYNAMIC_FEATURES)   # 9

# ── Node feature names (static — fixed per section) ─────────────────────────
STATIC_FEATURES = [
    "section_length_km",       # normalised
    "section_capacity_per_hr", # normalised
    "section_is_single_line",  # binary
]
N_STATIC = len(STATIC_FEATURES)    # 3


@dataclass
class Config:
    # ── Paths ────────────────────────────────────────────────────────────────
    data_path:  Path = Path("railway_ops.csv")
    model_dir:  Path = Path("models")
    model_name: str  = "congestion_forecaster"

    # ── Graph ────────────────────────────────────────────────────────────────
    n_sections: int = 48
    self_loops: bool = True   # add self-loops to adjacency

    # ── Temporal ─────────────────────────────────────────────────────────────
    seq_len:    int = 6       # hours of history as input
    horizons:   list[int] = field(default_factory=lambda: [1, 2, 3])
    # horizon k means predicting congestion k hours ahead

    # ── Model ────────────────────────────────────────────────────────────────
    gcn_hidden:  int   = 32   # GCN output dim per layer
    gcn_layers:  int   = 2    # number of GCN layers
    gru_hidden:  int   = 64   # GRU hidden size
    head_hidden: int   = 32
    dropout:     float = 0.2

    # ── Training ─────────────────────────────────────────────────────────────
    epochs:      int   = 80
    batch_size:  int   = 64
    lr:          float = 1e-3
    weight_decay:float = 1e-4
    patience:    int   = 12
    grad_clip:   float = 5.0
    log_every:   int   = 5

    # ── Data split (by date — no leakage) ────────────────────────────────────
    val_months:  list[int] = field(default_factory=lambda: [11])
    test_months: list[int] = field(default_factory=lambda: [12])

    # ── Misc ─────────────────────────────────────────────────────────────────
    seed:        int = 42
    device:      str = "auto"
    num_workers: int = 0

    def resolve_device(self) -> str:
        if self.device != "auto":
            return self.device
        try:
            import torch
            if torch.cuda.is_available():         return "cuda"
            if torch.backends.mps.is_available(): return "mps"
        except Exception:
            pass
        return "cpu"

    def model_path(self) -> Path:
        return Path(self.model_dir) / f"{self.model_name}.pt"

    def meta_path(self) -> Path:
        return Path(self.model_dir) / f"{self.model_name}_meta.pkl"
