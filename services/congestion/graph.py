"""
services/congestion/graph.py
============================
Build the railway section graph from railway_ops.csv.

Nodes  = sections  (48 for NDLS–CNB)
Edges  = section A → section B when A.to_station == B.from_station
         (consecutive sections share a station)

Returns:
  adj_norm   : normalised adjacency (N, N) numpy float32
               D^{-1/2} (A + I) D^{-1/2}  — with self-loops
  section_ids: list[str] — ordered node index mapping
  static_feat: numpy float32 (N, N_STATIC) — length, capacity, single-line
  section_meta: dict[section_id → {from, to, length, capacity, single_line}]
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd

from config import Config, STATIC_FEATURES, N_STATIC


# ---------------------------------------------------------------------------

def build_graph(
    df: pd.DataFrame,
    cfg: Config,
) -> Tuple[np.ndarray, list, np.ndarray, dict]:
    """
    Parameters
    ----------
    df  : full railway_ops.csv DataFrame

    Returns
    -------
    adj_norm    : (N, N) float32 — normalised adjacency with self-loops
    section_ids : list of N section_id strings (node index ↔ string)
    static_feat : (N, 3) float32 — scaled static section features
    meta        : dict  section_id → {from_station, to_station, ...}
    """
    # ── 1. Unique sections ────────────────────────────────────────────────
    sec_df = (
        df[["section_id", "from_station", "to_station",
            "section_length_km", "section_capacity_per_hr",
            "section_is_single_line"]]
        .drop_duplicates("section_id")
        .sort_values("section_id")
        .reset_index(drop=True)
    )

    section_ids: list[str] = sec_df["section_id"].tolist()
    N = len(section_ids)
    id2idx = {sid: i for i, sid in enumerate(section_ids)}

    meta = {
        row["section_id"]: {
            "from_station":          row["from_station"],
            "to_station":            row["to_station"],
            "section_length_km":     row["section_length_km"],
            "section_capacity_per_hr": row["section_capacity_per_hr"],
            "section_is_single_line":  int(row["section_is_single_line"]),
        }
        for _, row in sec_df.iterrows()
    }

    # ── 2. Adjacency: A[i,j] = 1 if section i leads to section j ─────────
    # station → list of sections that START at this station (successors)
    from collections import defaultdict
    from_map: dict[str, list[int]] = defaultdict(list)
    for i, sid in enumerate(section_ids):
        from_map[meta[sid]["from_station"]].append(i)

    A = np.zeros((N, N), dtype=np.float32)
    for i, sid in enumerate(section_ids):
        to_st = meta[sid]["to_station"]
        for j in from_map[to_st]:   # all sections starting where i ends
            A[i, j] = 1.0
            A[j, i] = 1.0           # undirected (trains run both ways)

    # ── 3. Self-loops ──────────────────────────────────────────────────────
    if cfg.self_loops:
        np.fill_diagonal(A, 1.0)

    # ── 4. Symmetric normalisation D^{-1/2} A D^{-1/2} ───────────────────
    deg  = A.sum(axis=1)
    d_inv_sqrt = np.where(deg > 0, 1.0 / np.sqrt(deg), 0.0)
    D    = np.diag(d_inv_sqrt)
    adj_norm = (D @ A @ D).astype(np.float32)

    # ── 5. Static features (N, 3) — min-max scaled ────────────────────────
    static_raw = sec_df[["section_length_km",
                          "section_capacity_per_hr",
                          "section_is_single_line"]].values.astype(np.float32)

    # Scale each column to [0, 1]
    col_min = static_raw.min(axis=0)
    col_max = static_raw.max(axis=0)
    denom   = np.where(col_max > col_min, col_max - col_min, 1.0)
    static_feat = (static_raw - col_min) / denom

    print(
        f"Graph built: {N} nodes, "
        f"{int(A.sum() - np.trace(A) if cfg.self_loops else A.sum())//2} undirected edges",
        flush=True,
    )

    return adj_norm, section_ids, static_feat, meta


def save_graph(path: Path, adj_norm, section_ids, static_feat, meta) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({
            "adj_norm": adj_norm,
            "section_ids": section_ids,
            "static_feat": static_feat,
            "meta": meta,
        }, f)
    print(f"Graph saved → {path}", flush=True)


def load_graph(path: Path) -> tuple:
    with open(path, "rb") as f:
        d = pickle.load(f)
    return d["adj_norm"], d["section_ids"], d["static_feat"], d["meta"]
