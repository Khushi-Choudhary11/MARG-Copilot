"""
services/congestion/run_training.py
=====================================
Main training entry point for the MARG congestion forecaster.

    cd services/congestion
    python run_training.py --data ../../railway_ops.csv
    python run_training.py --data ../../railway_ops.csv --quick   # 5-epoch test
    python run_training.py --device cpu --epochs 40 --bs 32
"""
from __future__ import annotations

import argparse
import json
import pickle
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
import torch
from torch.utils.data import DataLoader

from config import Config
from dataset import make_datasets
from evaluate import evaluate, print_metrics
from graph import build_graph, save_graph
from model import CongestionForecaster
from predict import CongestionPredictor
from train import train


# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Train MARG congestion forecaster")
    p.add_argument("--data",   default=None,  help="Path to railway_ops.csv")
    p.add_argument("--epochs", type=int,   default=None)
    p.add_argument("--bs",     type=int,   default=None, dest="batch_size")
    p.add_argument("--lr",     type=float, default=None)
    p.add_argument("--device", default=None, choices=["cpu","cuda","mps","auto"])
    p.add_argument("--quick",  action="store_true", default=False,
                   help="5-epoch smoke test")
    return p.parse_args()


def seed_all(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def main():
    args = parse_args()
    cfg  = Config()

    # Apply overrides
    if args.data:      cfg.data_path  = Path(args.data)
    if args.epochs:    cfg.epochs     = args.epochs
    if args.batch_size:cfg.batch_size = args.batch_size
    if args.lr:        cfg.lr         = args.lr
    if args.device:    cfg.device     = args.device
    if args.quick:     cfg.epochs = 5; cfg.patience = 5

    # Resolve data path
    if not cfg.data_path.exists():
        for cand in [
            Path(__file__).parent / cfg.data_path,
            Path(__file__).parent.parent.parent / cfg.data_path,
            Path.cwd() / cfg.data_path,
        ]:
            if cand.exists():
                cfg.data_path = cand
                break
        else:
            sys.exit(f"ERROR: cannot find {cfg.data_path}")

    if not cfg.model_dir.is_absolute():
        cfg.model_dir = Path(__file__).parent / cfg.model_dir

    seed_all(cfg.seed)
    device = cfg.resolve_device()
    print(f"Device: {device}")

    # ── Load CSV and build graph ──────────────────────────────────────────
    import pandas as pd
    print(f"Loading {cfg.data_path} …")
    df = pd.read_csv(cfg.data_path, low_memory=False)

    adj_norm, section_ids, static_feat, meta = build_graph(df, cfg)
    graph_path = Path(cfg.model_dir) / f"{cfg.model_name}_graph.pkl"
    Path(cfg.model_dir).mkdir(parents=True, exist_ok=True)
    save_graph(graph_path, adj_norm, section_ids, static_feat, meta)

    # ── Build datasets ────────────────────────────────────────────────────
    train_ds, val_ds, test_ds, all_dates, all_hours = make_datasets(
        cfg, adj_norm, section_ids, static_feat
    )

    # ── Model ─────────────────────────────────────────────────────────────
    model = CongestionForecaster(cfg)
    print(f"Parameters: {model.count_params():,}")

    # ── Train ─────────────────────────────────────────────────────────────
    history = train(model, train_ds, val_ds, cfg, section_ids)

    # Save history
    hist_path = Path(cfg.model_dir) / "congestion_history.json"
    with open(hist_path, "w") as f:
        json.dump({k: [float(v) for v in vs] for k, vs in history.items()}, f, indent=2)
    print(f"History → {hist_path}")

    # ── Test evaluation ────────────────────────────────────────────────────
    test_loader = DataLoader(
        test_ds, batch_size=cfg.batch_size * 2, shuffle=False,
        num_workers=cfg.num_workers,
    )
    print("\n── Test Set Metrics ──────────────────────────────────────────")
    test_m = evaluate(model, test_loader, device, cfg, section_ids)
    print_metrics(test_m, prefix="TEST")

    metrics_path = Path(cfg.model_dir) / "congestion_test_metrics.json"
    with open(metrics_path, "w") as f:
        m_ser = {k: (v if not isinstance(v, list) else
                     [(a, float(b)) for a, b in v])
                 for k, v in test_m.items()}
        json.dump(m_ser, f, indent=2)
    print(f"Test metrics → {metrics_path}")

    # ── Inference demo ─────────────────────────────────────────────────────
    print("\n── Inference Demo ────────────────────────────────────────────")
    predictor = CongestionPredictor(
        model, adj_norm, section_ids, static_feat, meta, cfg, device
    )

    # Grab last seq_len hours of test data as a "live" feed
    test_flat  = test_ds.flat           # (D*H, N, F)
    x_recent   = test_flat[-cfg.seq_len:].numpy()   # (T, N, F)
    scores     = predictor.predict_from_array(x_recent)
    top5       = predictor.top_congested(scores, horizon="1h", top_n=5)

    print("  Top-5 predicted congested sections (+1h):")
    for sid, score in top5:
        print(f"    {sid:<22s}  congestion={score:.3f}")


if __name__ == "__main__":
    main()
