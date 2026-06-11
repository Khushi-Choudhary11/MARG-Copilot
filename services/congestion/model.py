"""
services/congestion/model.py
=============================
Spatio-Temporal GNN for railway congestion forecasting.

Architecture
------------
For each input timestep t ∈ [0, T):
  GCNStack:  (B, N, F_dyn) ──[L graph conv layers]──► (B, N, H_gcn)

Temporal encoding:
  Stack T steps → (B, N, T, H_gcn)
  Permute+reshape → (B*N, T, H_gcn)
  GRU → h_T: (B*N, H_gru)
  Reshape → (B, N, H_gru)

Static fusion:
  Concat static features → (B, N, H_gru + F_stat)
  Linear projection → (B, N, H_proj)

Forecast heads (one per horizon):
  Linear(H_proj → H_head) → GELU → Linear(H_head → 1) → sigmoid
  Output per horizon: (B, N)  ∈ [0, 1]

Full output: (B, H_horizons, N)

All graph convolutions use the same normalised adjacency matrix A_norm,
passed as a buffer (not trained). Pure PyTorch, no external GNN library.
"""
from __future__ import annotations

from typing import List

import torch
import torch.nn as nn

from config import Config, N_DYNAMIC, N_STATIC


# ---------------------------------------------------------------------------
# Graph Convolution Layer
# ---------------------------------------------------------------------------

class GraphConv(nn.Module):
    """
    One GCN layer: H = σ(A_norm @ X @ W + b)

    Parameters
    ----------
    in_dim  : input feature dimension
    out_dim : output feature dimension
    """

    def __init__(self, in_dim: int, out_dim: int):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(in_dim, out_dim))
        self.bias   = nn.Parameter(torch.zeros(out_dim))
        nn.init.xavier_uniform_(self.weight)

    def forward(
        self,
        x:        torch.Tensor,   # (B, N, in_dim)
        adj_norm: torch.Tensor,   # (N, N)
    ) -> torch.Tensor:             # (B, N, out_dim)
        # Spectral graph convolution: A_norm @ X @ W
        support = x @ self.weight            # (B, N, out_dim)
        out     = torch.einsum("nm,bmo->bno", adj_norm, support) + self.bias
        return out


class GCNStack(nn.Module):
    """Stack of L GCN layers with residual connection on matching dims."""

    def __init__(self, in_dim: int, hidden: int, n_layers: int, dropout: float):
        super().__init__()
        dims   = [in_dim] + [hidden] * n_layers
        self.layers = nn.ModuleList(
            [GraphConv(dims[i], dims[i + 1]) for i in range(n_layers)]
        )
        self.bns    = nn.ModuleList(
            [nn.BatchNorm1d(dims[i + 1]) for i in range(n_layers)]
        )
        self.act    = nn.GELU()
        self.drop   = nn.Dropout(dropout)
        # Projection for residual on first layer only if dims differ
        self.proj   = (
            nn.Linear(in_dim, hidden, bias=False)
            if in_dim != hidden else None
        )

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        B, N, _ = x.shape
        out = x
        for i, (layer, bn) in enumerate(zip(self.layers, self.bns)):
            h = layer(out, adj)                  # (B, N, H)
            # BatchNorm expects (B, F) — apply over (B*N) batch
            h = bn(h.reshape(B * N, -1)).reshape(B, N, -1)
            h = self.act(h)
            h = self.drop(h)
            if i == 0:
                skip = self.proj(out) if self.proj is not None else out
                h = h + skip
            out = h
        return out   # (B, N, hidden)


# ---------------------------------------------------------------------------
# Full ST-GNN
# ---------------------------------------------------------------------------

class CongestionForecaster(nn.Module):
    """
    Spatio-Temporal GNN congestion forecaster.

    Parameters
    ----------
    cfg : Config

    Forward inputs
    --------------
    x      : (B, T, N, F_dyn)  dynamic node features
    static : (N, F_stat)        static section features (broadcast over B)
    adj    : (N, N)             normalised adjacency (same for all batches)

    Returns
    -------
    (B, H, N) predicted congestion scores in [0, 1]
    """

    def __init__(self, cfg: Config):
        super().__init__()

        self.cfg      = cfg
        self.seq_len  = cfg.seq_len
        self.n_horiz  = len(cfg.horizons)

        # ── Spatial encoder (shared across timesteps) ─────────────────────
        self.gcn = GCNStack(
            in_dim  = N_DYNAMIC,
            hidden  = cfg.gcn_hidden,
            n_layers= cfg.gcn_layers,
            dropout = cfg.dropout,
        )

        # ── Temporal encoder ──────────────────────────────────────────────
        self.gru = nn.GRU(
            input_size  = cfg.gcn_hidden,
            hidden_size = cfg.gru_hidden,
            num_layers  = 2,
            batch_first = True,
            dropout     = cfg.dropout,
        )

        # ── Static fusion projection ──────────────────────────────────────
        fusion_in  = cfg.gru_hidden + N_STATIC
        fusion_out = cfg.gru_hidden
        self.fusion = nn.Sequential(
            nn.Linear(fusion_in, fusion_out),
            nn.GELU(),
            nn.Dropout(cfg.dropout),
        )

        # ── Forecast heads (one per horizon) ─────────────────────────────
        self.heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(fusion_out, cfg.head_hidden),
                nn.GELU(),
                nn.Linear(cfg.head_hidden, 1),
                nn.Sigmoid(),   # congestion ∈ [0, 1]
            )
            for _ in cfg.horizons
        ])

        self._init_weights()

    # ------------------------------------------------------------------

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    # ------------------------------------------------------------------

    def forward(
        self,
        x:      torch.Tensor,    # (B, T, N, F_dyn)
        static: torch.Tensor,    # (N, F_stat)  or (B, N, F_stat)
        adj:    torch.Tensor,    # (N, N)
    ) -> torch.Tensor:

        B, T, N, F = x.shape

        # ── Spatial encoding for each timestep ───────────────────────────
        gcn_out = []
        for t in range(T):
            xt  = x[:, t, :, :]           # (B, N, F)
            ht  = self.gcn(xt, adj)        # (B, N, H_gcn)
            gcn_out.append(ht)

        # Stack → (B, N, T, H_gcn) → (B*N, T, H_gcn)
        gcn_seq = torch.stack(gcn_out, dim=2)        # (B, N, T, H_gcn)
        gcn_seq = gcn_seq.reshape(B * N, T, -1)      # (B*N, T, H_gcn)

        # ── Temporal encoding ────────────────────────────────────────────
        _, h_n  = self.gru(gcn_seq)        # h_n: (2, B*N, H_gru)
        h_last  = h_n[-1]                  # (B*N, H_gru) — top layer last state

        h_last  = h_last.reshape(B, N, -1) # (B, N, H_gru)

        # ── Static fusion ────────────────────────────────────────────────
        if static.dim() == 2:              # (N, S) → (B, N, S)
            static_exp = static.unsqueeze(0).expand(B, -1, -1)
        else:
            static_exp = static            # already (B, N, S)

        fused = torch.cat([h_last, static_exp], dim=-1)   # (B, N, H+S)
        fused = self.fusion(fused)                          # (B, N, H_proj)

        # ── Forecast heads ────────────────────────────────────────────────
        preds = torch.stack(
            [head(fused).squeeze(-1) for head in self.heads],
            dim=1,
        )  # (B, H_horizons, N)

        return preds

    # ------------------------------------------------------------------

    def count_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ---------------------------------------------------------------------------
# Loss
# ---------------------------------------------------------------------------

class CongestionLoss(nn.Module):
    """
    MSE + penalty for false negatives on high-congestion sections
    (we care more about missing a congestion event than over-predicting).

    loss = MSE(pred, target) + alpha * MSE(pred[target>threshold], target[target>threshold])
    """

    def __init__(self, alpha: float = 0.5, threshold: float = 0.6):
        super().__init__()
        self.alpha     = alpha
        self.threshold = threshold
        self.mse       = nn.MSELoss()

    def forward(
        self,
        pred:   torch.Tensor,   # (B, H, N)
        target: torch.Tensor,   # (B, H, N)
    ) -> torch.Tensor:
        base_loss = self.mse(pred, target)

        # Extra penalty for high-congestion misses
        high_mask = target > self.threshold
        if high_mask.any():
            high_loss = self.mse(pred[high_mask], target[high_mask])
        else:
            high_loss = torch.tensor(0.0, device=pred.device)

        return base_loss + self.alpha * high_loss
