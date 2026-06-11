"""
services/congestion/predict.py
===============================
Inference utility for the CongestionForecaster.

Usage
-----
    from predict import CongestionPredictor

    # Load from checkpoint
    predictor = CongestionPredictor.from_checkpoint("models/")

    # Predict from a live snapshot DataFrame
    # (DataFrame must have the same structure as railway_ops.csv)
    scores = predictor.predict_from_df(live_df, current_hour=14)
    # scores: dict  { section_id: {"1h": 0.42, "2h": 0.38, "3h": 0.31} }

    # Or predict from raw dense array (latest seq_len hours)
    scores = predictor.predict_from_array(x_recent)
    # x_recent: (seq_len, N, F_dyn) numpy float32
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Dict, List, Union

import numpy as np
import pandas as pd
import torch

from config import Config
from dataset import build_snapshots, build_dense_array
from graph import load_graph
from model import CongestionForecaster


class CongestionPredictor:
    """Wraps a trained model for end-to-end inference."""

    def __init__(
        self,
        model:       CongestionForecaster,
        adj_norm:    np.ndarray,
        section_ids: List[str],
        static_feat: np.ndarray,
        meta:        dict,
        cfg:         Config,
        device:      str = "cpu",
    ):
        self.model       = model.to(device).eval()
        self.adj_norm    = torch.from_numpy(adj_norm).to(device)
        self.section_ids = section_ids
        self.static      = torch.from_numpy(static_feat).to(device)
        self.meta        = meta
        self.cfg         = cfg
        self.device      = device

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_checkpoint(
        cls,
        model_dir:  Union[str, Path] = "models",
        model_name: str = "congestion_forecaster",
        device:     str = "cpu",
        cfg:        Config = None,
    ) -> "CongestionPredictor":
        if cfg is None:
            cfg = Config(model_dir=Path(model_dir), model_name=model_name)

        # Load graph
        graph_path = Path(model_dir) / f"{model_name}_graph.pkl"
        adj_norm, section_ids, static_feat, meta = load_graph(graph_path)

        # Load model
        model = CongestionForecaster(cfg)
        state = torch.load(cfg.model_path(), map_location=device, weights_only=True)
        model.load_state_dict(state)
        model.eval()

        return cls(model, adj_norm, section_ids, static_feat, meta, cfg, device)

    # ── Core predict ─────────────────────────────────────────────────────────

    @torch.no_grad()
    def predict_from_array(self, x_recent: np.ndarray) -> Dict[str, Dict[str, float]]:
        """
        Parameters
        ----------
        x_recent : (seq_len, N, F_dyn) float32

        Returns
        -------
        dict: section_id → {"1h": score, "2h": score, "3h": score}
        """
        assert x_recent.shape == (self.cfg.seq_len, len(self.section_ids),
                                   len([None] * 9)), \
            f"Expected ({self.cfg.seq_len}, {len(self.section_ids)}, 9), got {x_recent.shape}"

        x   = torch.from_numpy(x_recent).unsqueeze(0).to(self.device)   # (1, T, N, F)
        out = self.model(x, self.static, self.adj_norm)                  # (1, H, N)
        out = out.squeeze(0).cpu().numpy()                               # (H, N)

        result: Dict[str, Dict[str, float]] = {}
        for s_i, sid in enumerate(self.section_ids):
            result[sid] = {
                f"{h}h": float(out[h_i, s_i])
                for h_i, h in enumerate(self.cfg.horizons)
            }
        return result

    @torch.no_grad()
    def predict_from_df(
        self,
        live_df:      pd.DataFrame,
        current_hour: int,
        all_hours:    List[int] = None,
    ) -> Dict[str, Dict[str, float]]:
        """
        Build a live snapshot from a raw DataFrame slice (last seq_len hours
        ending at current_hour) and run inference.

        Parameters
        ----------
        live_df      : DataFrame filtered to the relevant time window
        current_hour : the most recent hour (inclusive) to use as the last timestep
        all_hours    : sorted list of valid hours (defaults to [6..23])
        """
        if all_hours is None:
            all_hours = list(range(6, 24))

        snaps = build_snapshots(live_df)
        dates = sorted(live_df["date"].astype(str).unique())

        dense = build_dense_array(snaps, self.section_ids, dates, all_hours)
        # dense: (D, H, N, F) — flatten to (D*H, N, F)
        flat  = dense.reshape(len(dates) * len(all_hours), len(self.section_ids), -1)

        # Find index of current_hour in all_hours
        h_idx = all_hours.index(current_hour) if current_hour in all_hours else len(all_hours) - 1
        d_idx = len(dates) - 1
        end   = d_idx * len(all_hours) + h_idx + 1
        start = end - self.cfg.seq_len
        if start < 0:
            # Pad with zeros at the beginning
            pad_len = -start
            pad     = np.zeros((pad_len, len(self.section_ids), flat.shape[-1]),
                               dtype=np.float32)
            seq = np.concatenate([pad, flat[0:end]], axis=0)
        else:
            seq = flat[start:end]   # (seq_len, N, F)

        return self.predict_from_array(seq.astype(np.float32))

    def top_congested(
        self,
        scores:    Dict[str, Dict[str, float]],
        horizon:   str = "1h",
        top_n:     int = 5,
    ) -> List[tuple]:
        """Return top-N most congested sections for a given horizon."""
        ranked = sorted(
            [(sid, v[horizon]) for sid, v in scores.items()],
            key=lambda t: t[1],
            reverse=True,
        )
        return ranked[:top_n]
