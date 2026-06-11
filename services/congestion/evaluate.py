"""
services/congestion/evaluate.py
================================
Evaluation metrics for congestion forecasting.

Metrics (per horizon, per section, and averaged):
  MAE        : mean absolute error in congestion score units [0,1]
  RMSE       : root mean squared error
  R²         : coefficient of determination
  accuracy@5%: fraction of predictions within 0.05 of ground truth
  high_recall: recall for congestion_score > 0.6  (critical threshold)
  high_prec  : precision for predicted > 0.6
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import torch
from torch.utils.data import DataLoader

from config import Config


def _mae(p, t):   return float(np.mean(np.abs(p - t)))
def _rmse(p, t):  return float(np.sqrt(np.mean((p - t) ** 2)))
def _r2(p, t):
    ss_res = np.sum((t - p) ** 2)
    ss_tot = np.sum((t - np.mean(t)) ** 2)
    return float(1 - ss_res / (ss_tot + 1e-8))
def _acc(p, t, tol=0.05):   return float(np.mean(np.abs(p - t) <= tol))
def _high_recall(p, t, thr=0.6):
    mask = t > thr
    if not mask.any():  return float("nan")
    return float(np.mean(p[mask] > thr))
def _high_prec(p, t, thr=0.6):
    mask = p > thr
    if not mask.any():  return float("nan")
    return float(np.mean(t[mask] > thr))


@torch.no_grad()
def evaluate(
    model:    torch.nn.Module,
    loader:   DataLoader,
    device:   str,
    cfg:      Config,
    section_ids: List[str] = None,
) -> Dict[str, float]:
    """
    Run inference on loader and return metrics dict.

    Keys: mae_1h, rmse_1h, r2_1h, acc_1h, recall_1h, prec_1h, ...same for 2h/3h, mae_mean
    If section_ids provided, also returns per-section MAE for worst 5 sections.
    """
    model.eval()

    all_pred  = [[] for _ in cfg.horizons]
    all_tgt   = [[] for _ in cfg.horizons]

    for x, static, y, adj in loader:
        x      = x.to(device)
        static = static.to(device)
        adj    = adj.to(device)
        y      = y  # keep on CPU

        preds = model(x, static, adj).cpu()   # (B, H, N)

        for h_i in range(len(cfg.horizons)):
            all_pred[h_i].append(preds[:, h_i, :].numpy())   # (B, N)
            all_tgt[h_i].append(y[:, h_i, :].numpy())

    metrics: Dict[str, float] = {}
    hour_maes = []

    for h_i, h in enumerate(cfg.horizons):
        p = np.concatenate(all_pred[h_i], axis=0).ravel()   # (B*N,)
        t = np.concatenate(all_tgt[h_i],  axis=0).ravel()

        key = f"{h}h"
        metrics[f"mae_{key}"]    = _mae(p, t)
        metrics[f"rmse_{key}"]   = _rmse(p, t)
        metrics[f"r2_{key}"]     = _r2(p, t)
        metrics[f"acc_{key}"]    = _acc(p, t)
        metrics[f"recall_{key}"] = _high_recall(p, t)
        metrics[f"prec_{key}"]   = _high_prec(p, t)
        metrics[f"n_{key}"]      = len(p)
        hour_maes.append(metrics[f"mae_{key}"])

    metrics["mae_mean"] = float(np.mean(hour_maes))

    # Per-section worst-5 MAE (for the +1h horizon)
    if section_ids is not None:
        p2d = np.concatenate(all_pred[0], axis=0)   # (B, N)
        t2d = np.concatenate(all_tgt[0],  axis=0)   # (B, N)
        sec_mae = np.mean(np.abs(p2d - t2d), axis=0)  # (N,)
        worst5  = np.argsort(sec_mae)[-5:][::-1]
        metrics["worst5_sections"] = [
            (section_ids[i], float(sec_mae[i])) for i in worst5
        ]

    return metrics


def print_metrics(metrics: Dict, prefix: str = "") -> None:
    tag = f"[{prefix}] " if prefix else ""
    for h in [1, 2, 3]:
        k = f"{h}h"
        if f"mae_{k}" not in metrics:
            continue
        rec = metrics.get(f"recall_{k}", float("nan"))
        pre = metrics.get(f"prec_{k}",   float("nan"))
        print(
            f"{tag}+{h}h  "
            f"MAE={metrics[f'mae_{k}']:.4f}  "
            f"RMSE={metrics[f'rmse_{k}']:.4f}  "
            f"R²={metrics[f'r2_{k}']:.3f}  "
            f"Acc@5%={metrics[f'acc_{k}']:.3f}  "
            f"HiRec={rec:.3f}  HiPrec={pre:.3f}"
        )
    if "mae_mean" in metrics:
        print(f"{tag}Mean MAE: {metrics['mae_mean']:.4f}")
    if "worst5_sections" in metrics:
        print(f"{tag}Worst 5 sections (+1h MAE):")
        for sid, m in metrics["worst5_sections"]:
            print(f"    {sid:<20s}  MAE={m:.4f}")
