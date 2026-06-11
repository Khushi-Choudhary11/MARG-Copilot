"""
services/congestion/train.py
=============================
Training loop for CongestionForecaster.
  - AdamW + CosineAnnealingLR
  - CongestionLoss (MSE + high-congestion penalty)
  - Early stopping on val MAE mean
  - Best checkpoint saving
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Dict

import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader

from config import Config
from evaluate import evaluate, print_metrics
from model import CongestionLoss


def _train_epoch(model, loader, opt, criterion, device, grad_clip) -> float:
    model.train()
    total = 0.0
    n     = 0

    for x, static, y, adj in loader:
        x      = x.to(device)
        static = static[0].to(device)   # same for all batch items; (N, S)
        adj    = adj[0].to(device)       # same adjacency; (N, N)
        y      = y.to(device)

        opt.zero_grad()
        pred = model(x, static, adj)     # (B, H, N)
        loss = criterion(pred, y)
        loss.backward()

        if grad_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)

        opt.step()
        total += loss.item()
        n     += 1

    return total / max(n, 1)


def train(model, train_ds, val_ds, cfg: Config, section_ids=None) -> Dict:
    device = cfg.resolve_device()
    model  = model.to(device)

    train_loader = DataLoader(
        train_ds, batch_size=cfg.batch_size, shuffle=True,
        num_workers=cfg.num_workers, pin_memory=(device != "cpu"), drop_last=True,
    )
    val_loader = DataLoader(
        val_ds, batch_size=cfg.batch_size * 2, shuffle=False,
        num_workers=cfg.num_workers,
    )

    criterion = CongestionLoss(alpha=0.5, threshold=0.6).to(device)
    opt       = AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    sched     = CosineAnnealingLR(opt, T_max=cfg.epochs, eta_min=cfg.lr * 1e-2)

    best_mae   = float("inf")
    patience   = 0
    best_state = None
    history    = {"train_loss": [], "val_mae": [], "lr": []}

    Path(cfg.model_dir).mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*64}")
    print(
        f"Training on {device.upper()}  |  "
        f"params={model.count_params():,}  |  "
        f"epochs={cfg.epochs}  |  bs={cfg.batch_size}"
    )
    print(f"{'='*64}\n")

    t0 = time.time()

    for epoch in range(1, cfg.epochs + 1):
        tr_loss = _train_epoch(model, train_loader, opt, criterion, device, cfg.grad_clip)
        sched.step()
        val_m   = evaluate(model, val_loader, device, cfg, section_ids)
        val_mae = val_m.get("mae_mean", float("inf"))
        lr      = sched.get_last_lr()[0]

        history["train_loss"].append(tr_loss)
        history["val_mae"].append(val_mae)
        history["lr"].append(lr)

        if val_mae < best_mae:
            best_mae   = val_mae
            patience   = 0
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            torch.save(best_state, cfg.model_path())
        else:
            patience += 1

        if epoch % cfg.log_every == 0 or epoch == 1:
            elapsed = time.time() - t0
            print(
                f"Epoch {epoch:3d}/{cfg.epochs}  "
                f"train={tr_loss:.5f}  val_mae={val_mae:.4f}  "
                f"lr={lr:.2e}  patience={patience}/{cfg.patience}  ({elapsed:.0f}s)"
            )
            print_metrics(val_m, prefix="  val")

        if patience >= cfg.patience:
            print(f"\nEarly stopping at epoch {epoch}")
            break

    if best_state:
        model.load_state_dict(best_state)
        model.to(device)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s  |  best val MAE={best_mae:.4f}")
    print(f"Checkpoint → {cfg.model_path()}")
    return history
