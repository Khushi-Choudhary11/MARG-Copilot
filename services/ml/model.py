"""
services/ml/model.py
====================
DelayPredictor — multi-horizon delay prediction model.

Architecture
------------
1. Embedding layers for categorical inputs (weather, train category)
2. Shared trunk: Linear → BN → GELU → Dropout  (×3 layers, optional residual)
3. Three independent heads (one per prediction horizon)
   Each head: Linear(64→32) → GELU → Linear(32→1)

Inputs per forward pass
-----------------------
  num   : (B, N_NUMERICAL)  z-scored floats
  w_idx : (B,)              weather class index  [0..6]
  c_idx : (B,)              train category index [0..3]

Output
------
  preds : (B, H)  predicted delay in minutes for each horizon
"""

from __future__ import annotations

import math
from typing import List

import torch
import torch.nn as nn

from config import (
    N_WEATHER, N_CATEGORY, N_NUMERICAL, Config,
)


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class _Block(nn.Module):
    """Linear → BN → GELU → Dropout, with optional residual."""

    def __init__(self, in_dim: int, out_dim: int, dropout: float, residual: bool):
        super().__init__()
        self.fc  = nn.Linear(in_dim, out_dim)
        self.bn  = nn.BatchNorm1d(out_dim)
        self.act = nn.GELU()
        self.drop = nn.Dropout(dropout)
        # 1×1 projection for residual if dims differ
        self.residual = residual
        self.proj = (
            nn.Linear(in_dim, out_dim, bias=False)
            if (residual and in_dim != out_dim)
            else None
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.drop(self.act(self.bn(self.fc(x))))
        if self.residual:
            skip = self.proj(x) if self.proj is not None else x
            out = out + skip
        return out


class _Head(nn.Module):
    """Single horizon prediction head."""

    def __init__(self, in_dim: int, hidden: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)   # (B,)


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------

class DelayPredictor(nn.Module):
    """
    Parameters
    ----------
    cfg : Config  (architecture hyper-parameters read from config.py)
    """

    def __init__(self, cfg: Config):
        super().__init__()

        self.weather_emb  = nn.Embedding(N_WEATHER,  cfg.embed_dim_weather)
        self.category_emb = nn.Embedding(N_CATEGORY, cfg.embed_dim_category)

        n_in = N_NUMERICAL + cfg.embed_dim_weather + cfg.embed_dim_category

        dims = cfg.hidden_dims  # e.g. [256, 128, 64]
        layers: list[nn.Module] = []
        d_prev = n_in
        for d_out in dims:
            layers.append(
                _Block(d_prev, d_out, cfg.dropout, cfg.use_residual)
            )
            d_prev = d_out

        self.trunk = nn.Sequential(*layers)
        self.trunk_out_dim = d_prev  # 64 by default

        self.heads = nn.ModuleList(
            [_Head(self.trunk_out_dim, cfg.head_hidden) for _ in cfg.horizons]
        )

        self._init_weights()

    # ------------------------------------------------------------------

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, nonlinearity="relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Embedding):
                nn.init.normal_(m.weight, std=0.05)
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)

    # ------------------------------------------------------------------

    def forward(
        self,
        num:   torch.Tensor,   # (B, N_NUMERICAL)
        w_idx: torch.Tensor,   # (B,)
        c_idx: torch.Tensor,   # (B,)
    ) -> torch.Tensor:
        """Returns (B, H) predicted delay in minutes."""
        w_emb = self.weather_emb(w_idx)    # (B, E_w)
        c_emb = self.category_emb(c_idx)   # (B, E_c)
        x = torch.cat([num, w_emb, c_emb], dim=-1)  # (B, n_in)
        x = self.trunk(x)                            # (B, 64)
        preds = torch.stack([h(x) for h in self.heads], dim=1)  # (B, H)
        return preds

    # ------------------------------------------------------------------
    # Convenience: count params
    # ------------------------------------------------------------------

    def count_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Loss
# ---------------------------------------------------------------------------

class MaskedHuberLoss(nn.Module):
    """
    Huber loss averaged only over non-NaN targets.
    Weighted per horizon.

    Parameters
    ----------
    weights : list[float]  one per horizon, e.g. [1.0, 0.8, 0.6]
    delta   : float        Huber delta (minutes)
    """

    def __init__(self, weights: List[float], delta: float = 10.0):
        super().__init__()
        self.register_buffer(
            "weights", torch.tensor(weights, dtype=torch.float32)
        )
        self.delta = delta

    def forward(
        self,
        preds:   torch.Tensor,   # (B, H)
        targets: torch.Tensor,   # (B, H)  — may contain NaN
    ) -> torch.Tensor:
        valid  = ~torch.isnan(targets)           # (B, H) bool mask
        preds  = preds[valid]
        tgts   = targets[valid]

        if preds.numel() == 0:
            return preds.sum() * 0.0             # zero loss, correct device

        diff   = preds - tgts
        huber  = torch.where(
            diff.abs() <= self.delta,
            0.5 * diff ** 2,
            self.delta * (diff.abs() - 0.5 * self.delta),
        )

        # per-horizon weighting (broadcast)
        h_idx  = valid.nonzero(as_tuple=False)[:, 1]       # which horizon?
        w      = self.weights[h_idx]
        loss   = (huber * w).sum() / (w.sum() + 1e-8)
        return loss
