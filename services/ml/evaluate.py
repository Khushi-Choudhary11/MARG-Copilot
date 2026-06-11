"""
services/ml/evaluate.py
=======================
Evaluation metrics for delay prediction.

Exports
-------
evaluate(model, loader, device, cfg) -> dict
    Runs inference on a DataLoader and returns a metrics dict.

within_n_accuracy(pred, true, n)
    Fraction of predictions within n minutes of ground truth.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import torch
from torch.utils.data import DataLoader

from config import Config


def _mae(pred: np.ndarray, true: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - true)))


def _rmse(pred: np.ndarray, true: np.ndarray) -> float:
    return float(np.sqrt(np.mean((pred - true) ** 2)))


def _r2(pred: np.ndarray, true: np.ndarray) -> float:
    ss_res = np.sum((true - pred) ** 2)
    ss_tot = np.sum((true - np.mean(true)) ** 2)
    return float(1.0 - ss_res / (ss_tot + 1e-8))


def within_n_accuracy(pred: np.ndarray, true: np.ndarray, n: float) -> float:
    return float(np.mean(np.abs(pred - true) <= n))


@torch.no_grad()
def evaluate(
    model:  torch.nn.Module,
    loader: DataLoader,
    device: str,
    cfg:    Config,
) -> Dict[str, float]:
    """
    Returns a dict like:
      {
        "mae_30": 3.4, "rmse_30": 5.1, "r2_30": 0.72,
        "w5_30":  0.52, "w15_30": 0.87,
        ... (same for _60, _120)
        "mae_mean": ..., "rmse_mean": ...
      }
    """
    model.eval()

    # Collect all predictions and targets (per horizon, only valid rows)
    all_preds   = [[] for _ in cfg.horizons]
    all_targets = [[] for _ in cfg.horizons]

    for num, w_idx, c_idx, targets in loader:
        num    = num.to(device)
        w_idx  = w_idx.to(device)
        c_idx  = c_idx.to(device)
        targets = targets  # keep on CPU

        preds = model(num, w_idx, c_idx).cpu()   # (B, H)

        for h_i in range(len(cfg.horizons)):
            valid = ~torch.isnan(targets[:, h_i])
            if valid.any():
                all_preds[h_i].append(preds[valid, h_i].numpy())
                all_targets[h_i].append(targets[valid, h_i].numpy())

    metrics: Dict[str, float] = {}
    horizon_maes = []

    for h_i, h in enumerate(cfg.horizons):
        if not all_preds[h_i]:
            continue
        p = np.concatenate(all_preds[h_i])
        t = np.concatenate(all_targets[h_i])

        key = str(h)
        metrics[f"mae_{key}"]  = _mae(p, t)
        metrics[f"rmse_{key}"] = _rmse(p, t)
        metrics[f"r2_{key}"]   = _r2(p, t)
        metrics[f"w5_{key}"]   = within_n_accuracy(p, t, 5.0)
        metrics[f"w15_{key}"]  = within_n_accuracy(p, t, 15.0)
        metrics[f"n_{key}"]    = len(p)
        horizon_maes.append(metrics[f"mae_{key}"])

    if horizon_maes:
        metrics["mae_mean"]  = float(np.mean(horizon_maes))

    return metrics


def print_metrics(metrics: Dict[str, float], prefix: str = "") -> None:
    """Pretty-print the metrics dict."""
    tag = f"[{prefix}] " if prefix else ""
    for h in [30, 60, 120]:
        k = str(h)
        if f"mae_{k}" not in metrics:
            continue
        print(
            f"{tag}+{h:3d}min  "
            f"MAE={metrics[f'mae_{k}']:.2f}  "
            f"RMSE={metrics[f'rmse_{k}']:.2f}  "
            f"R²={metrics[f'r2_{k}']:.3f}  "
            f"W5={metrics[f'w5_{k}']:.3f}  "
            f"W15={metrics[f'w15_{k}']:.3f}  "
            f"n={int(metrics[f'n_{k}']):,}"
        )
    if "mae_mean" in metrics:
        print(f"{tag}Mean MAE: {metrics['mae_mean']:.2f} min")
