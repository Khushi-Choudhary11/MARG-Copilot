"""
services/optimizer/graph_utils.py
===================================
NetworkX corridor graph for MARG.

Graph structure
───────────────
  Nodes  = stations  (25 for NDLS–CNB)
  Edges  = directed sections  (48)
  Edge attributes:
    section_id      str
    length_km       float
    travel_time     Dict[category → float]   scheduled travel time per train type
    capacity_per_hr int
    is_single_line  bool
    is_blocked      bool
    congestion_score float
    weight          float   routing cost (updated dynamically)

Graph operations
────────────────
  build_corridor_graph(sections)      → nx.DiGraph
  update_edge_weights(G, state)       → mutate G in-place
  find_route(G, from_st, to_st)       → List[section_id]   (Dijkstra)
  k_shortest_routes(G, from_st, to_st, k) → List[List[section_id]]
  detect_conflicts(state)             → List[ConflictRecord]
  section_path_to_station_path(...)   → List[station_id]
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import networkx as nx
import pandas as pd

from problem import NetworkState, SectionState, TrainState


# ── Conflict record ───────────────────────────────────────────────────────────

@dataclass
class ConflictRecord:
    """A detected conflict requiring optimizer attention."""
    section_id:   str
    conflict_type: str        # "headway" | "crossing" | "capacity" | "blocked"
    trains:       List[str]
    severity:     float       # 0–1; higher = more urgent
    time_window:  Tuple[float, float]   # (start, end) in minutes from midnight


# ── Build corridor graph ──────────────────────────────────────────────────────

# Base speed (km/h) per category — used to estimate travel time if not provided
_BASE_SPEED = {"superfast": 110, "mail": 80, "express": 70, "goods": 55}

# Default headway and loop wait penalty
_HEADWAY_MIN   = 3
_LOOP_PENALTY  = 8   # extra minutes added to routing cost for single-line sections


def build_corridor_graph(
    sections: Dict[str, SectionState],
    travel_times: Optional[Dict[Tuple[str,str], float]] = None,
) -> nx.DiGraph:
    """
    Build a directed weighted NetworkX graph from SectionState objects.

    Edge weight = base routing cost (minutes). Updated dynamically.

    Parameters
    ----------
    sections     : dict of section_id → SectionState
    travel_times : optional dict of (section_id, category) → minutes
    """
    G = nx.DiGraph()

    for sid, sec in sections.items():
        # Estimate default travel time from distance + speed
        speed    = _BASE_SPEED.get("express", 70)
        base_tt  = (sec.length_km / speed) * 60        # minutes

        # Routing cost: blocked = very high; single-line = penalty; else base
        if sec.is_blocked:
            weight = 1e6
        else:
            weight = base_tt * (1 + sec.congestion_score)
            if sec.is_single_line:
                weight += _LOOP_PENALTY

        G.add_edge(
            sec.from_station,
            sec.to_station,
            section_id      = sid,
            length_km       = sec.length_km,
            base_travel_min = base_tt,
            capacity_per_hr = sec.capacity_per_hr,
            is_single_line  = sec.is_single_line,
            is_blocked      = sec.is_blocked,
            congestion_score= sec.congestion_score,
            weight          = weight,
        )

    return G


def build_graph_from_csv(csv_path: str) -> nx.DiGraph:
    """
    Convenience: build graph directly from railway_ops.csv.
    Uses mean congestion_score per section as initial weight signal.
    """
    df = pd.read_csv(csv_path, low_memory=False)

    sec_agg = df.groupby("section_id").agg(
        from_station     = ("from_station",      "first"),
        to_station       = ("to_station",        "first"),
        length_km        = ("section_length_km", "first"),
        capacity_per_hr  = ("section_capacity_per_hr", "first"),
        is_single_line   = ("section_is_single_line",  "first"),
        congestion_score = ("congestion_score",  "mean"),
    ).reset_index()

    sections = {}
    for _, row in sec_agg.iterrows():
        sections[row["section_id"]] = SectionState(
            section_id      = row["section_id"],
            from_station    = row["from_station"],
            to_station      = row["to_station"],
            length_km       = row["length_km"],
            capacity_per_hr = int(row["capacity_per_hr"]),
            is_single_line  = bool(row["is_single_line"]),
            congestion_score= float(row["congestion_score"]),
        )

    return build_corridor_graph(sections), sections


def update_edge_weights(G: nx.DiGraph, state: NetworkState) -> None:
    """
    Refresh edge weights from current NetworkState (in-place).
    Called before each optimization run.
    """
    for sid, sec in state.sections.items():
        # Find edge in G
        for u, v, data in G.edges(data=True):
            if data.get("section_id") == sid:
                if sec.is_blocked:
                    G[u][v]["weight"] = 1e6
                else:
                    base = data["base_travel_min"]
                    G[u][v]["weight"] = (
                        base * (1 + sec.congestion_score) +
                        (_LOOP_PENALTY if sec.is_single_line else 0)
                    )
                G[u][v]["is_blocked"]       = sec.is_blocked
                G[u][v]["congestion_score"] = sec.congestion_score
                break


# ── Routing ──────────────────────────────────────────────────────────────────

def find_route(
    G:       nx.DiGraph,
    from_st: str,
    to_st:   str,
    blocked: Optional[List[str]] = None,
) -> Optional[List[str]]:
    """
    Dijkstra shortest path. Returns list of section_ids (not stations).
    Returns None if no path exists.

    Parameters
    ----------
    blocked : section_ids to treat as impassable (weight=1e6)
    """
    if from_st == to_st:
        return []

    # Temporarily block sections if requested
    if blocked:
        orig_weights = {}
        for u, v, data in G.edges(data=True):
            if data.get("section_id") in blocked:
                orig_weights[(u, v)] = data["weight"]
                G[u][v]["weight"] = 1e9

    path_nodes = None
    try:
        path_nodes = nx.dijkstra_path(G, from_st, to_st, weight="weight")
    except nx.NetworkXNoPath:
        pass

    # Restore weights
    if blocked and orig_weights:
        for (u, v), w in orig_weights.items():
            G[u][v]["weight"] = w

    if path_nodes is None:
        return None

    # Convert station path → section_id list
    return _station_path_to_sections(G, path_nodes)


def k_shortest_routes(
    G:       nx.DiGraph,
    from_st: str,
    to_st:   str,
    k:       int = 3,
    blocked: Optional[List[str]] = None,
) -> List[Tuple[List[str], float]]:
    """
    Yen's k-shortest simple paths (by weight).
    Returns list of (section_id_list, total_cost) tuples.
    """
    if from_st == to_st:
        return [([], 0.0)]

    # Block sections
    if blocked:
        for u, v, data in G.edges(data=True):
            if data.get("section_id") in blocked:
                G[u][v]["weight"] = 1e9

    results = []
    try:
        for path_nodes in nx.shortest_simple_paths(G, from_st, to_st, weight="weight"):
            cost     = sum(G[path_nodes[i]][path_nodes[i+1]]["weight"]
                           for i in range(len(path_nodes)-1))
            sec_path = _station_path_to_sections(G, path_nodes)
            results.append((sec_path, cost))
            if len(results) >= k:
                break
    except nx.NetworkXNoPath:
        pass

    return results


def _station_path_to_sections(G: nx.DiGraph, station_path: List[str]) -> List[str]:
    """Convert a list of station IDs to the section_ids along the path."""
    return [
        G[station_path[i]][station_path[i+1]]["section_id"]
        for i in range(len(station_path) - 1)
    ]


def route_cost(G: nx.DiGraph, section_ids: List[str]) -> float:
    """Total routing cost for a section_id path."""
    total = 0.0
    for u, v, data in G.edges(data=True):
        if data.get("section_id") in section_ids:
            total += data["weight"]
    return total


def route_travel_time(G: nx.DiGraph, section_ids: List[str]) -> float:
    """Expected travel time (minutes) for a section_id path."""
    total = 0.0
    for u, v, data in G.edges(data=True):
        if data.get("section_id") in section_ids:
            total += data["base_travel_min"]
    return total


# ── Conflict detection ────────────────────────────────────────────────────────

def detect_conflicts(state: NetworkState) -> List[ConflictRecord]:
    """
    Scan the current NetworkState and return all detected conflicts.

    Conflict types:
      "headway"  — two trains too close on the same section
      "crossing" — two trains approaching same single-line section from opposite ends
      "capacity" — section over capacity
      "blocked"  — train's route passes through a blocked section
    """
    conflicts: List[ConflictRecord] = []
    now = state.timestamp_min

    # ── Blocked section conflicts ─────────────────────────────────────────
    blocked = set(state.blocked_sections)
    for train in state.active_trains:
        route_secs = set(train.remaining_route)
        hit = route_secs & blocked
        for sec_id in hit:
            conflicts.append(ConflictRecord(
                section_id   = sec_id,
                conflict_type= "blocked",
                trains       = [train.train_id],
                severity     = 1.0,
                time_window  = (now, now + state.horizon_min),
            ))

    # ── Section-level conflicts ───────────────────────────────────────────
    # Group trains by upcoming sections
    section_trains: Dict[str, List[TrainState]] = {}
    for train in state.active_trains:
        for sec_id in train.remaining_route[:6]:   # look 6 sections ahead
            section_trains.setdefault(sec_id, []).append(train)

    for sec_id, trains in section_trains.items():
        if len(trains) < 2:
            continue
        sec = state.sections.get(sec_id)
        if sec is None:
            continue

        t_window_start = min(
            t.sched_departures.get(sec_id, now) for t in trains
        )
        t_window_end   = t_window_start + 60

        # Capacity conflict
        if len(trains) > sec.capacity_per_hr:
            conflicts.append(ConflictRecord(
                section_id   = sec_id,
                conflict_type= "capacity",
                trains       = [t.train_id for t in trains],
                severity     = min(1.0, len(trains) / sec.capacity_per_hr - 1),
                time_window  = (t_window_start, t_window_end),
            ))

        # Headway / crossing conflict
        conflict_type = "crossing" if sec.is_single_line else "headway"
        # Check for opposing-direction trains on single-line
        if sec.is_single_line:
            up_trains   = [t for t in trains if t.direction == "UP"]
            down_trains = [t for t in trains if t.direction == "DOWN"]
            if up_trains and down_trains:
                conflicts.append(ConflictRecord(
                    section_id   = sec_id,
                    conflict_type= "crossing",
                    trains       = [t.train_id for t in trains],
                    severity     = 0.9,
                    time_window  = (t_window_start, t_window_end),
                ))
                continue  # crossing supersedes headway for same section

        # Headway: check if any two trains are within min_headway of each other
        for i, t1 in enumerate(trains):
            for t2 in trains[i+1:]:
                dep1 = t1.sched_departures.get(sec_id, now + t1.current_delay)
                dep2 = t2.sched_departures.get(sec_id, now + t2.current_delay)
                gap  = abs(dep1 - dep2)
                if gap < state.min_headway:
                    conflicts.append(ConflictRecord(
                        section_id   = sec_id,
                        conflict_type= "headway",
                        trains       = [t1.train_id, t2.train_id],
                        severity     = 1.0 - gap / state.min_headway,
                        time_window  = (min(dep1,dep2), max(dep1,dep2)+20),
                    ))

    # Deduplicate by (section_id, conflict_type, frozenset(trains))
    seen  = set()
    dedup = []
    for c in conflicts:
        key = (c.section_id, c.conflict_type, frozenset(c.trains))
        if key not in seen:
            seen.add(key)
            dedup.append(c)

    return sorted(dedup, key=lambda c: -c.severity)
