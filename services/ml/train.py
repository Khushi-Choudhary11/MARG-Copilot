"""
services/ml/train.py
====================
Training loop for DelayPredictor with:
  - AdamW optimiser + CosineAnnealingLR
  - Huber loss (masked, weighted per horizon)
  - Early stopping on val MAE mean
  - Best model checkpoint
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Dict, Tuple

import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader

from config import Config
from evaluate import evaluate, print_metrics
from model import MaskedHuberLoss


# ---------------------------------------------------------------------------
# Single epoch helpers
# ---------------------------------------------------------------------------

def _train_epoch(
    model:     torch.nn.Module,
    loader:    DataLoader,
    optimiser: torch.optim.Optimizer,
    criterion: torch.nn.Module,
    device:    str,
    grad_clip: float,
) -> float:
    """Returns mean training loss for the epoch."""
    model.train()
    total_loss = 0.0
    n_batches  = 0

    for num, w_idx, c_idx, targets in loader:
        num     = num.to(device)
        w_idx   = w_idx.to(device)
        c_idx   = c_idx.to(device)
        targets = targets.to(device)

        optimiser.zero_grad()
        preds = model(num, w_idx, c_idx)          # (B, H)
        loss  = criterion(preds, targets)
        loss.backward()

        if grad_clip > 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)

        optimiser.step()

        total_loss += loss.item()
        n_batches  += 1

    return total_loss / max(n_batches, 1)


# ---------------------------------------------------------------------------
# Full training procedure
# ---------------------------------------------------------------------------

def train(
    model:     torch.nn.Module,
    train_ds,
    val_ds,
    cfg:       Config,
) -> Dict[str, list]:
    """
    Trains the model in-place.
    Returns history dict:  {"train_loss": [...], "val_mae": [...], "lr": [...]}
    """
    device = cfg.resolve_device()
    model  = model.to(device)

    train_loader = DataLoader(
        train_ds,
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=cfg.num_workers,
        pin_memory=(device != "cpu"),
        drop_last=True,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=cfg.batch_size * 2,
        shuffle=False,
        num_workers=cfg.num_workers,
    )

    criterion = MaskedHuberLoss(
        weights=cfg.horizon_weights,
        delta=cfg.huber_delta,
    ).to(device)

    optimiser = AdamW(
        model.parameters(),
        lr=cfg.lr,
        weight_decay=cfg.weight_decay,
    )
    scheduler = CosineAnnealingLR(
        optimiser,
        T_max=cfg.epochs,
        eta_min=cfg.lr * 1e-2,
    )

    best_val_mae = float("inf")
    patience_ctr = 0
    best_state   = None

    history: Dict[str, list] = {
        "train_loss": [],
        "val_mae":    [],
        "lr":         [],
    }

    model_path = cfg.model_path()
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}", flush=True)
    print(
        f"Training on {device.upper()}  |  "
        f"params={model.count_params():,}  |  "
        f"epochs={cfg.epochs}  |  bs={cfg.batch_size}",
        flush=True,
    )
    print(f"{'='*60}\n", flush=True)

    t0 = time.time()

    for epoch in range(1, cfg.epochs + 1):
        train_loss = _train_epoch(
            model, train_loader, optimiser, criterion, device, cfg.grad_clip
        )
        scheduler.step()

        val_metrics = evaluate(model, val_loader, device, cfg)
        val_mae     = val_metrics.get("mae_mean", float("inf"))
        current_lr  = scheduler.get_last_lr()[0]

        history["train_loss"].append(train_loss)
        history["val_mae"].append(val_mae)
        history["lr"].append(current_lr)

        # ── Early stopping ──────────────────────────────────────────────
        if val_mae < best_val_mae:
            best_val_mae = val_mae
            patience_ctr = 0
            best_state   = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            torch.save(best_state, model_path)
        else:
            patience_ctr += 1

        # ── Logging ─────────────────────────────────────────────────────
        if epoch % cfg.log_every == 0 or epoch == 1:
            elapsed = time.time() - t0
            print(
                f"Epoch {epoch:3d}/{cfg.epochs}  "
                f"train_loss={train_loss:.4f}  "
                f"val_mae={val_mae:.2f}  "
                f"lr={current_lr:.2e}  "
                f"patience={patience_ctr}/{cfg.patience}  "
                f"({elapsed:.0f}s)",
                flush=True,
            )
            print_metrics(val_metrics, prefix="  val")

        if patience_ctr >= cfg.patience:
            print(f"\nEarly stopping at epoch {epoch}  (patience={cfg.patience})", flush=True)
            break

    # Restore best weights
    if best_state is not None:
        model.load_state_dict(best_state)
        model.to(device)

    total_time = time.time() - t0
    print(f"\nTraining complete in {total_time:.0f}s  |  best val MAE={best_val_mae:.2f} min", flush=True)
    print(f"Best model saved → {model_path}", flush=True)

    return history
