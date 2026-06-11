"""
services/congestion/dataset.py
===============================
Data pipeline:
  1. Aggregate railway_ops.csv → hourly section snapshots
     (date, hour_of_day, section_id) → 9 dynamic node features
  2. Fill missing cells with zero (no trains = zero congestion)
  3. Build sliding windows: seq_len consecutive hours → targets at +1/+2/+3h
  4. CongestionDataset (PyTorch Dataset)

Tensors (per sample):
  x      : (T, N, F_dyn)   dynamic features — float32
  static : (N, F_stat)     static features  — float32
  y      : (H, N)           target congestion scores — float32
  adj    : (N, N)           normalised adjacency (same for all samples)
"""
from __future__ import annotations

import math
import pickle
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

try:
    import torch
    from torch.utils.data import Dataset
    _TORCH = True
except ImportError:
    _TORCH = False
    class Dataset:  # type: ignore
        pass

from config import Config, DYNAMIC_FEATURES, N_DYNAMIC


# ── Cyclic helper ────────────────────────────────────────────────────────────

def _cyc(v, period):
    a = 2 * math.pi * v / period
    return np.sin(a), np.cos(a)


# ── Step 1: aggregate to hourly section snapshots ────────────────────────────

def build_snapshots(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate rows to (date, hour_of_day, section_id) level.
    Returns a DataFrame with one row per (date, hour, section) cell,
    containing the 9 dynamic features.
    """
    agg = df.groupby(["date", "hour_of_day", "section_id"]).agg(
        congestion_score    = ("congestion_score",    "mean"),
        train_count         = ("train_id",            "count"),
        weather_speed_factor= ("weather_speed_factor","mean"),
        signal_failed       = ("signal_failed",       "max"),
        track_blocked       = ("track_blocked",       "max"),
        arrive_delay_mean   = ("arrive_delay_min",    "mean"),
        capacity_per_hr     = ("section_capacity_per_hr", "first"),
    ).reset_index()

    # Derived features
    agg["capacity_util"] = (
        agg["train_count"] / agg["capacity_per_hr"].clip(lower=1)
    ).clip(upper=1.0)
    agg["time_sin"], agg["time_cos"] = _cyc(agg["hour_of_day"], 24.0)

    # Normalise train_count and delay
    max_tc   = agg["train_count"].max() or 1
    max_del  = agg["arrive_delay_mean"].abs().max() or 1
    agg["train_count"]       = agg["train_count"]       / max_tc
    agg["arrive_delay_mean"] = agg["arrive_delay_mean"] / max_del

    agg["signal_failed"] = agg["signal_failed"].astype(float)
    agg["track_blocked"] = agg["track_blocked"].astype(float)

    return agg


# ── Step 2: pivot to dense (dates × hours × sections) tensor ─────────────────

def build_dense_array(
    snapshots:   pd.DataFrame,
    section_ids: list[str],
    all_dates:   list[str],
    all_hours:   list[int],
) -> np.ndarray:
    """
    Returns float32 array shape (D, H_per_day, N, F_dyn).
    Missing cells are zero.
    """
    D = len(all_dates);  H = len(all_hours);  N = len(section_ids)
    date2i = {d: i for i, d in enumerate(all_dates)}
    hour2i = {h: i for i, h in enumerate(all_hours)}
    sec2i  = {s: i for i, s in enumerate(section_ids)}

    arr = np.zeros((D, H, N, N_DYNAMIC), dtype=np.float32)

    cols = [
        "congestion_score", "train_count", "capacity_util",
        "weather_speed_factor", "signal_failed", "track_blocked",
        "arrive_delay_mean", "time_sin", "time_cos",
    ]

    for row in snapshots.itertuples(index=False):
        d = date2i.get(row.date)
        h = hour2i.get(row.hour_of_day)
        s = sec2i.get(row.section_id)
        if d is None or h is None or s is None:
            continue
        for f_i, col in enumerate(cols):
            arr[d, h, s, f_i] = getattr(row, col)

    return arr   # (D, H, N, F)


# ── Step 3: sliding window index builder ─────────────────────────────────────

def build_windows(
    date_indices: list[int],
    n_hours:      int,
    seq_len:      int,
    max_horizon:  int,
) -> list[tuple]:
    """
    Each window = (date_idx, hour_idx of LAST input step).
    Valid windows need seq_len preceding hours and max_horizon following hours
    within the same contiguous date block.

    Returns list of (flat_start, flat_end, flat_target_starts).
    Flat index = date_idx * n_hours + hour_idx.
    """
    windows = []
    n_dates = len(date_indices)

    for di_pos, di in enumerate(date_indices):
        for hi in range(n_hours):
            flat_start = di * n_hours + hi
            flat_end   = flat_start + seq_len

            # Check we have seq_len + max_horizon consecutive flat indices
            # (we don't cross date boundaries mid-sequence for simplicity)
            needed_hrs  = seq_len + max_horizon
            start_hr    = hi
            if start_hr + needed_hrs > n_hours:
                # Would spill into next day — skip
                continue

            flat_targets = [flat_end + k - 1 for k in range(1, max_horizon + 1)]
            windows.append((flat_start, seq_len, flat_targets))

    return windows


# ── Dataset class ─────────────────────────────────────────────────────────────

class CongestionDataset(Dataset):
    """
    Parameters
    ----------
    dense    : (D, H, N, F) float32 — full dense array for one split
    windows  : list of (flat_start, seq_len, flat_targets)
    adj_norm : (N, N) float32
    static   : (N, S) float32
    cfg      : Config
    n_hours  : int   hours per day in the dense array
    """

    def __init__(
        self,
        dense:    np.ndarray,
        windows:  list,
        adj_norm: np.ndarray,
        static:   np.ndarray,
        cfg:      Config,
        n_hours:  int,
    ):
        if not _TORCH:
            raise ImportError("PyTorch required. Run: pip install torch")

        D, H, N, F = dense.shape
        # Reshape to (D*H, N, F) for flat indexing
        self.flat = dense.reshape(D * H, N, F)
        self.windows  = windows
        self.adj_norm = torch.from_numpy(adj_norm)              # (N, N)
        self.static   = torch.from_numpy(static)               # (N, S)
        self.seq_len  = cfg.seq_len
        self.cfg      = cfg

    def __len__(self) -> int:
        return len(self.windows)

    def __getitem__(self, idx: int):
        flat_start, seq_len, flat_targets = self.windows[idx]

        # Input sequence
        x_np = self.flat[flat_start: flat_start + seq_len]   # (T, N, F)
        x    = torch.from_numpy(x_np)                        # (T, N, F)

        # Targets: congestion_score is feature index 0
        y_np = np.stack(
            [self.flat[t, :, 0] for t in flat_targets], axis=0
        )  # (H, N)
        y = torch.from_numpy(y_np)

        return x, self.static, y, self.adj_norm


# ── Full pipeline ─────────────────────────────────────────────────────────────

def make_datasets(
    cfg:         Config,
    adj_norm:    np.ndarray,
    section_ids: list[str],
    static_feat: np.ndarray,
):
    """
    Load CSV, build snapshots, split, build datasets.
    Returns (train_ds, val_ds, test_ds, all_dates, all_hours).
    """
    print(f"Loading {cfg.data_path} …", flush=True)
    df = pd.read_csv(cfg.data_path, low_memory=False)
    df["date"] = df["date"].astype(str)

    snaps = build_snapshots(df)
    print(f"  Snapshots: {len(snaps):,} (date, hour, section) cells", flush=True)

    all_dates = sorted(df["date"].unique())
    all_hours = sorted(df["hour_of_day"].unique())
    H = len(all_hours)
    max_h = max(cfg.horizons)

    dense = build_dense_array(snaps, section_ids, all_dates, all_hours)
    print(f"  Dense array: {dense.shape}  (dates={len(all_dates)}, hours={H}, sections={len(section_ids)}, features={N_DYNAMIC})", flush=True)

    # Date-based split
    date_df = pd.DataFrame({"date": all_dates})
    date_df["month"] = pd.to_datetime(date_df["date"]).dt.month

    val_dates  = date_df[date_df["month"].isin(cfg.val_months)]["date"].tolist()
    test_dates = date_df[date_df["month"].isin(cfg.test_months)]["date"].tolist()
    train_dates= date_df[~date_df["month"].isin(cfg.val_months + cfg.test_months)]["date"].tolist()

    def _indices(dates):
        return [all_dates.index(d) for d in dates]

    def _windows(date_idxs):
        return build_windows(date_idxs, H, cfg.seq_len, max_h)

    tr_idx = _indices(train_dates)
    va_idx = _indices(val_dates)
    te_idx = _indices(test_dates)

    tr_w = _windows(tr_idx)
    va_w = _windows(va_idx)
    te_w = _windows(te_idx)

    print(
        f"  Windows: train={len(tr_w):,}  val={len(va_w):,}  test={len(te_w):,}",
        flush=True,
    )

    train_ds = CongestionDataset(dense, tr_w, adj_norm, static_feat, cfg, H)
    val_ds   = CongestionDataset(dense, va_w, adj_norm, static_feat, cfg, H)
    test_ds  = CongestionDataset(dense, te_w, adj_norm, static_feat, cfg, H)

    return train_ds, val_ds, test_ds, all_dates, all_hours
