"""
services/ml/dataset.py — MARG multi-horizon delay prediction dataset.

Column name mapping (CSV schema):
  date, train_id          → grouping keys for target construction
  sched_arrive_min        → horizon anchor (minutes from midnight)
  sched_depart_min        → cyclic position-in-day encoding
  hour_of_day, month,
  day_of_week, is_weekend → time features (already in CSV)
  category                → train category (superfast/mail/express/goods)
  direction               → UP/DOWN string → binarised
  weather_condition       → string → embedding index
"""
from __future__ import annotations

import math
import pickle
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import pandas as pd

try:
    from sklearn.preprocessing import StandardScaler
except ImportError:
    raise SystemExit("scikit-learn not installed.  Run: pip install scikit-learn")

try:
    import torch
    from torch.utils.data import Dataset
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False
    class Dataset:  # type: ignore
        pass

from config import (
    WEATHER_CLASSES, CATEGORY_CLASSES,
    NUMERICAL_FEATURES, N_NUMERICAL,
    Config,
)

# ── Cyclic encoding ──────────────────────────────────────────────────────────

def _cyc(value, period: float):
    angle = 2 * math.pi * value / period
    return np.sin(angle), np.cos(angle)


# ── Feature engineering ──────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns
    -------
    num   : float32 (N, 23)
    w_idx : int64   (N,)   weather embedding index
    c_idx : int64   (N,)   category embedding index

    All inputs come from columns already present in railway_ops.csv.
    """
    df = df.copy()

    # Cyclic time encodings (columns already in CSV)
    hour  = df["hour_of_day"].astype(float)
    month = df["month"].astype(float)
    dow   = df["day_of_week"].astype(float)
    sod   = (df["sched_depart_min"] % 1440).astype(float)

    h_sin, h_cos = _cyc(hour,      24.0)
    m_sin, m_cos = _cyc(month - 1, 12.0)
    d_sin, d_cos = _cyc(dow,        7.0)
    s_sin, s_cos = _cyc(sod,     1440.0)

    df["hour_sin"]      = h_sin;  df["hour_cos"]      = h_cos
    df["month_sin"]     = m_sin;  df["month_cos"]     = m_cos
    df["dow_sin"]       = d_sin;  df["dow_cos"]       = d_cos
    df["sched_dep_sin"] = s_sin;  df["sched_dep_cos"] = s_cos

    # Binarise
    df["section_is_single_line"] = df["section_is_single_line"].astype(float)
    df["signal_failed"]          = df["signal_failed"].astype(float)
    df["track_blocked"]          = df["track_blocked"].astype(float)
    df["direction"]              = (df["direction"] == "UP").astype(float)
    df["is_weekend"]             = df["is_weekend"].astype(float)

    # Categorical → index
    w_map = {w: i for i, w in enumerate(WEATHER_CLASSES)}
    c_map = {c: i for i, c in enumerate(CATEGORY_CLASSES)}
    w_idx = df["weather_condition"].map(w_map).fillna(0).astype(np.int64).values
    c_idx = df["category"].map(c_map).fillna(0).astype(np.int64).values

    num = df[NUMERICAL_FEATURES].astype(np.float32).values
    return num, w_idx, c_idx


# ── Multi-horizon target construction ─────────────────────────────────────────

_WINDOW = {30: (20, 45), 60: (45, 80), 120: (90, 150)}


def build_targets(df: pd.DataFrame, horizons: list) -> np.ndarray:
    """
    Returns float32 (N, H).  NaN where no matching future section found.
    Groups by (date, train_id), sorted by sched_arrive_min.
    For each row i, finds the first subsequent row j where
    sched_arrive_min[j] - sched_arrive_min[i] falls in the horizon window.
    """
    df = df.copy().reset_index(drop=True)
    df["_sarr"] = pd.to_numeric(df["sched_arrive_min"], errors="coerce")
    df["_del"]  = pd.to_numeric(df["arrive_delay_min"],  errors="coerce")
    df["_oi"]   = df.index

    N = len(df)
    targets = np.full((N, len(horizons)), np.nan, dtype=np.float32)

    for _, grp in df.groupby(["date", "train_id"], sort=False):
        grp  = grp.sort_values("_sarr")
        arr  = grp["_sarr"].values
        dels = grp["_del"].values
        orig = grp["_oi"].values

        for pos, (src_i, T) in enumerate(zip(orig, arr)):
            if np.isnan(T):
                continue
            fut_arr = arr[pos + 1:]
            fut_del = dels[pos + 1:]
            delta   = fut_arr - T
            for h_i, h in enumerate(horizons):
                lo, hi = _WINDOW[h]
                mask   = (delta >= lo) & (delta <= hi)
                if mask.any():
                    targets[src_i, h_i] = fut_del[mask][0]

    return targets


# ── Dataset class ─────────────────────────────────────────────────────────────

class RailwayDelayDataset(Dataset):
    """
    PyTorch Dataset wrapping feature engineering + scaler.

    Parameters
    ----------
    df     : raw DataFrame for one split (train / val / test)
    cfg    : Config instance
    scaler : fitted StandardScaler, or None if fit=True
    fit    : if True, fit a new scaler on this split (train only)
    """

    def __init__(self, df: pd.DataFrame, cfg: Config,
                 scaler=None, fit: bool = False):
        if not _TORCH_AVAILABLE:
            raise ImportError("PyTorch required. Run: pip install torch")
        self.cfg = cfg

        num, w_idx, c_idx = build_features(df)
        targets            = build_targets(df, cfg.horizons)

        if fit:
            self.scaler = StandardScaler()
            self.scaler.fit(num)
        else:
            if scaler is None:
                raise ValueError("Pass fitted scaler for val/test splits.")
            self.scaler = scaler

        num = self.scaler.transform(num).astype(np.float32)

        self.num     = torch.from_numpy(num)
        self.w_idx   = torch.from_numpy(w_idx)
        self.c_idx   = torch.from_numpy(c_idx)
        self.targets = torch.from_numpy(targets)

    def __len__(self):
        return len(self.num)

    def __getitem__(self, idx):
        return self.num[idx], self.w_idx[idx], self.c_idx[idx], self.targets[idx]

    def save_scaler(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self.scaler, f)

    @staticmethod
    def load_scaler(path: Path):
        with open(path, "rb") as f:
            return pickle.load(f)


# ── Load + split helpers ──────────────────────────────────────────────────────

def load_and_split(cfg: Config):
    """
    Load railway_ops.csv and split by month (prevents temporal leakage).
    Train: all months not in val_months or test_months.
    Val:   cfg.val_months  (default: [11] = November)
    Test:  cfg.test_months (default: [12] = December)
    """
    print(f"Loading {cfg.data_path} …", flush=True)
    df = pd.read_csv(cfg.data_path, low_memory=False)
    # "month" column already in CSV (int 1–12)

    test_mask  = df["month"].isin(cfg.test_months)
    val_mask   = df["month"].isin(cfg.val_months)
    train_mask = ~test_mask & ~val_mask

    train_df = df[train_mask].reset_index(drop=True)
    val_df   = df[val_mask].reset_index(drop=True)
    test_df  = df[test_mask].reset_index(drop=True)

    print(
        f"  Train: {len(train_df):,}  |  Val: {len(val_df):,}  |  Test: {len(test_df):,}",
        flush=True,
    )
    return train_df, val_df, test_df


def make_datasets(cfg: Config):
    """
    Build train / val / test datasets.
    Fits scaler on train, applies to val + test.
    Saves scaler to cfg.scaler_path().
    """
    train_df, val_df, test_df = load_and_split(cfg)
    train_ds = RailwayDelayDataset(train_df, cfg, fit=True)
    val_ds   = RailwayDelayDataset(val_df,   cfg, scaler=train_ds.scaler)
    test_ds  = RailwayDelayDataset(test_df,  cfg, scaler=train_ds.scaler)
    Path(cfg.model_dir).mkdir(parents=True, exist_ok=True)
    train_ds.save_scaler(cfg.scaler_path())
    print(f"  Scaler saved → {cfg.scaler_path()}", flush=True)
    return train_ds, val_ds, test_ds
