"""
services/ml/run_training.py
============================
Main entry point.  Run from the services/ml/ directory:

    cd services/ml
    python run_training.py                        # default config
    python run_training.py --epochs 30 --bs 1024  # override hyperparams

After training the script:
  1. Evaluates on the test split
  2. Prints a compact metrics table
  3. Saves models/delay_predictor.pt  (best checkpoint)
  4. Saves models/delay_predictor_scaler.pkl
  5. (Optional) saves training history as models/history.json
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# Allow imports from the same directory
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import torch

from config import Config
from dataset import make_datasets
from evaluate import evaluate, print_metrics
from model import DelayPredictor
from train import train


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train MARG delay predictor")
    p.add_argument("--data",    default=None,  help="Path to railway_ops.csv")
    p.add_argument("--epochs",  type=int,   default=None)
    p.add_argument("--bs",      type=int,   default=None, dest="batch_size")
    p.add_argument("--lr",      type=float, default=None)
    p.add_argument("--device",  default=None, choices=["cpu","cuda","mps","auto"])
    p.add_argument("--no-residual", action="store_true", default=False)
    p.add_argument("--quick",   action="store_true", default=False,
                   help="5-epoch smoke test")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    cfg = Config()

    # Apply CLI overrides
    if args.data:
        cfg.data_path = Path(args.data)
    if args.epochs:
        cfg.epochs = args.epochs
    if args.batch_size:
        cfg.batch_size = args.batch_size
    if args.lr:
        cfg.lr = args.lr
    if args.device:
        cfg.device = args.device
    if args.no_residual:
        cfg.use_residual = False
    if args.quick:
        cfg.epochs  = 5
        cfg.patience = 5

    # Locate data file: try relative to script, then cwd, then project root
    if not cfg.data_path.exists():
        candidates = [
            Path(__file__).parent / cfg.data_path,
            Path(__file__).parent.parent.parent / cfg.data_path,
            Path.cwd() / cfg.data_path,
        ]
        for c in candidates:
            if c.exists():
                cfg.data_path = c
                break
        else:
            sys.exit(f"ERROR: cannot find {cfg.data_path}.  Use --data <path>")

    # Locate model dir relative to script
    if not cfg.model_dir.is_absolute():
        cfg.model_dir = Path(__file__).parent / cfg.model_dir

    seed_everything(cfg.seed)
    device = cfg.resolve_device()
    print(f"Device: {device}", flush=True)

    # ── Build datasets ──────────────────────────────────────────────────────
    train_ds, val_ds, test_ds = make_datasets(cfg)

    # ── Model ───────────────────────────────────────────────────────────────
    model = DelayPredictor(cfg)
    print(f"Model parameters: {model.count_params():,}", flush=True)

    # ── Train ───────────────────────────────────────────────────────────────
    history = train(model, train_ds, val_ds, cfg)

    # Save history
    history_path = Path(cfg.model_dir) / "history.json"
    with open(history_path, "w") as f:
        json.dump({k: [float(v) for v in vs] for k, vs in history.items()}, f, indent=2)
    print(f"History saved → {history_path}", flush=True)

    # ── Test evaluation ─────────────────────────────────────────────────────
    from torch.utils.data import DataLoader

    test_loader = DataLoader(
        test_ds,
        batch_size=cfg.batch_size * 2,
        shuffle=False,
        num_workers=cfg.num_workers,
    )

    print("\n── Test Set Metrics ──────────────────────────────────────────", flush=True)
    test_metrics = evaluate(model, test_loader, device, cfg)
    print_metrics(test_metrics, prefix="TEST")

    # Save metrics alongside model
    metrics_path = Path(cfg.model_dir) / "test_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump({k: float(v) for k, v in test_metrics.items()}, f, indent=2)
    print(f"\nTest metrics saved → {metrics_path}", flush=True)

    # ── Quick inference demo ─────────────────────────────────────────────────
    print("\n── Inference Demo ────────────────────────────────────────────", flush=True)
    from predict import Predictor
    predictor = Predictor(model, train_ds.scaler, cfg, device)
    example   = predictor.predict_single(
        current_delay_min=22.5,
        priority=1,
        weather="DENSE_FOG",
        congestion_score=0.75,
        section_is_single_line=True,
        signal_failed=False,
        track_blocked=False,
        category="superfast",
        hour_of_day=6.5,
        month=12.0,
        day_of_week=4.0,
        sched_depart_min=390.0,
    )
    print("  Input:  delay=22.5 min, DENSE_FOG, congestion=0.75, single-line, superfast")
    for h, v in example.items():
        print(f"  {h.replace('pred_','Pred ')}min: {v:.1f} min")


if __name__ == "__main__":
    main()
