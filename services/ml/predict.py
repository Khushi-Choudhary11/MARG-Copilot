"""
services/ml/predict.py
======================
Inference utilities: load a trained model and predict on arbitrary inputs.

Typical usage
-------------
    from predict import Predictor

    p = Predictor.from_checkpoint("models/")
    df = pd.read_csv("railway_ops.csv").head(100)
    result = p.predict_df(df)   # DataFrame with columns pred_30, pred_60, pred_120
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd
import torch

from config import Config
from dataset import build_features
from model import DelayPredictor


class Predictor:
    """
    Wraps a trained DelayPredictor + scaler for end-to-end inference.

    Parameters
    ----------
    model   : trained DelayPredictor (in eval mode)
    scaler  : fitted StandardScaler from dataset.py
    cfg     : Config used during training
    device  : torch device string
    """

    def __init__(
        self,
        model:  DelayPredictor,
        scaler,
        cfg:    Config,
        device: str = "cpu",
    ):
        self.model  = model.to(device).eval()
        self.scaler = scaler
        self.cfg    = cfg
        self.device = device

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_checkpoint(
        cls,
        model_dir:  Union[str, Path] = "models",
        model_name: str = "delay_predictor",
        device:     str = "cpu",
        cfg:        Config = None,
    ) -> "Predictor":
        """Load model + scaler from the models/ directory."""
        if cfg is None:
            cfg = Config(model_dir=Path(model_dir), model_name=model_name)

        model = DelayPredictor(cfg)
        state = torch.load(cfg.model_path(), map_location=device, weights_only=True)
        model.load_state_dict(state)
        model.eval()

        with open(cfg.scaler_path(), "rb") as f:
            scaler = pickle.load(f)

        return cls(model, scaler, cfg, device)

    # ------------------------------------------------------------------
    # Core predict
    # ------------------------------------------------------------------

    @torch.no_grad()
    def predict_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Predict delays for each row in df.

        Returns
        -------
        pd.DataFrame with columns: pred_30, pred_60, pred_120
          Values are in minutes.  Indices match the input df.
        """
        num, w_idx, c_idx = build_features(df)
        num = self.scaler.transform(num).astype(np.float32)

        num_t   = torch.from_numpy(num).to(self.device)
        w_t     = torch.from_numpy(w_idx).to(self.device)
        c_t     = torch.from_numpy(c_idx).to(self.device)

        # Batch inference
        BATCH = 4096
        preds_list = []
        for start in range(0, len(num_t), BATCH):
            end = start + BATCH
            p   = self.model(num_t[start:end], w_t[start:end], c_t[start:end])
            preds_list.append(p.cpu().numpy())

        preds = np.concatenate(preds_list, axis=0)   # (N, H)

        cols = {f"pred_{h}": preds[:, i] for i, h in enumerate(self.cfg.horizons)}
        return pd.DataFrame(cols, index=df.index)

    @torch.no_grad()
    def predict_single(
        self,
        current_delay_min: float,
        priority:          float,
        weather:           str,
        congestion_score:  float,
        section_is_single_line: bool,
        signal_failed:     bool = False,
        track_blocked:     bool = False,
        **kwargs,
    ) -> dict:
        """
        Predict for a single observation given named feature values.
        Missing features default to 0.

        Returns dict: {"pred_30": x, "pred_60": y, "pred_120": z}
        """
        from config import WEATHER_CLASSES, CATEGORY_CLASSES, NUMERICAL_FEATURES

        # Build a minimal DataFrame row that build_features can process
        row = {col: 0.0 for col in NUMERICAL_FEATURES}
        row["arrive_delay_min"]      = current_delay_min
        row["depart_delay_min"]      = current_delay_min
        row["cumulative_delay_min"]  = current_delay_min
        row["congestion_score"]      = congestion_score
        row["section_is_single_line"] = float(section_is_single_line)
        row["signal_failed"]         = float(signal_failed)
        row["track_blocked"]         = float(track_blocked)
        row["priority"]              = float(priority)
        row.update(kwargs)

        # Defaults for required categorical/time columns (matching CSV schema)
        row["weather_condition"] = weather
        row["category"]          = kwargs.get("category", "express")
        row["hour_of_day"]       = kwargs.get("hour_of_day", 10.0)
        row["month"]             = kwargs.get("month", 6.0)
        row["day_of_week"]       = kwargs.get("day_of_week", 3.0)
        row["sched_depart_min"]  = kwargs.get("sched_depart_min", 600.0)
        row["direction"]         = kwargs.get("direction", "UP")

        df = pd.DataFrame([row])
        result_df = self.predict_df(df)
        return {f"pred_{h}": float(result_df[f"pred_{h}"].iloc[0])
                for h in self.cfg.horizons}
