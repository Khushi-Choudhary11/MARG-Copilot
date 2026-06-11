"""
services/optimizer/rerouter.py
================================
Emergency rerouting via NetworkX.

When a section is blocked, this module:
  1. Identifies all trains whose route passes through the blocked section
  2. For each affected train, finds k alternative paths using Yen's algorithm
  3. Scores each alternative: travel_time + congestion_penalty + cascade_delay
  4. Returns ranked RouteAlternative objects

Scoring function
────────────────
  score(path) = α · travel_extra_min
              + β · congestion_penalty
              + γ · single_line_crossings
              + δ · cascade_delay_estimate

  Lower score = better route.  α=1.0, β=20.0, γ=5.0, δ=0.5 (tunable)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import networkx as nx

from graph_utils import (
    k_shortest_routes, route_travel_time, ConflictRecord,
)
from problem import Decision, DecisionType, NetworkState, TrainState


# ── Scoring weights ───────────────────────────────────────────────────────────

_W_TRAVEL    = 1.0    # weight on extra travel time (minutes)
_W_CONG      = 20.0   # weight on mean congestion score
_W_SINGLELINE= 5.0    # penalty per single-line section in route
_W_CASCADE   = 0.5    # weight on estimated cascade delay (minutes)
_K_PATHS     = 4      # number of alternative paths to consider


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class RouteAlternative:
    """One alternative route for a blocked-route train."""
    train_id:       str
    original_route: List[str]        # original section_id list
    alt_route:      List[str]        # alternative section_id list
    bypasses:       List[str]        # blocked sections avoided
    extra_time_min: float            # extra travel time vs original
    congestion_avg: float            # mean congestion on new route
    n_single_line:  int              # single-line sections in new route
    cascade_est:    float            # estimated cascade delay (minutes)
    total_score:    float            # lower = better
    feasible:       bool = True
    reason:         str = ""

    @property
    def recommended(self) -> bool:
        return self.feasible and self.total_score < 60.0

    def summary(self) -> str:
        return (
            f"Train {self.train_id}: alt route [{len(self.alt_route)} sections], "
            f"+{self.extra_time_min:.1f}min, "
            f"cong={self.congestion_avg:.2f}, "
            f"score={self.total_score:.1f}  "
            f"{'✓ RECOMMENDED' if self.recommended else '✗ marginal'}"
        )


# ── Rerouter ─────────────────────────────────────────────────────────────────

class EmergencyRerouter:
    """
    Finds and scores alternative routes for trains affected by section blockages.

    Parameters
    ----------
    G : nx.DiGraph  corridor graph (with section_id on edges)
    """

    def __init__(self, G: nx.DiGraph):
        self.G = G

    # ------------------------------------------------------------------
    def reroute(
        self,
        state:     NetworkState,
        conflicts: Optional[List[ConflictRecord]] = None,
    ) -> Tuple[List[RouteAlternative], List[Decision]]:
        """
        Main entry point.  Returns (alternatives, decisions).
        """
        blocked = set(state.blocked_sections)
        if not blocked:
            return [], []

        all_alts:  List[RouteAlternative] = []
        decisions: List[Decision]         = []

        for train in state.active_trains:
            route_set = set(train.remaining_route)
            hit_secs  = route_set & blocked
            if not hit_secs:
                continue

            alts = self._find_alternatives(train, state, hit_secs, list(blocked))
            all_alts.extend(alts)

            if alts and alts[0].feasible:
                best = alts[0]
                # Estimate cascade delay saved: blocked section adds many minutes;
                # rerouting saves that minus the extra travel time
                blocked_delay = sum(
                    state.sections[s].block_duration
                    for s in hit_secs
                    if s in state.sections
                )
                delay_saved = max(0, blocked_delay - best.extra_time_min)

                decisions.append(Decision(
                    decision_type   = DecisionType.REROUTE,
                    train_id        = train.train_id,
                    section_id      = list(hit_secs)[0],
                    detail          = (
                        f"REROUTE: {train.train_id} diverted via "
                        f"{best.alt_route[:3]}…  "
                        f"avoids blocked {', '.join(hit_secs)}  "
                        f"extra={best.extra_time_min:.1f}min"
                    ),
                    alt_route       = best.alt_route,
                    delay_saved_min = delay_saved,
                    confidence      = 0.85 if best.total_score < 30 else 0.65,
                ))

        return all_alts, decisions

    # ------------------------------------------------------------------
    def _find_alternatives(
        self,
        train:    TrainState,
        state:    NetworkState,
        hit_secs: set,
        blocked:  List[str],
    ) -> List[RouteAlternative]:
        """Find and rank k alternative routes for one affected train."""
        if not train.remaining_route:
            return []

        # Entry point: current section's from_station
        start_sec = state.sections.get(train.current_section)
        if start_sec is None:
            return []
        from_st = start_sec.from_station

        # Destination: final section's to_station
        final_sec = state.sections.get(train.final_section)
        if final_sec is None:
            return []
        to_st = final_sec.to_station

        # Original route travel time (excluding blocked sections)
        orig_tt = sum(
            t for sid, t in
            ((s, train.travel_times.get(s, 0)) for s in train.remaining_route)
            if sid not in hit_secs
        )

        # Find k alternatives
        candidates = k_shortest_routes(self.G, from_st, to_st, k=_K_PATHS,
                                       blocked=list(blocked))

        alts = []
        for alt_sec_path, cost in candidates:
            if not alt_sec_path:
                continue
            if any(s in blocked for s in alt_sec_path):
                continue   # skip if alternative still uses blocked section

            alt_tt = route_travel_time(self.G, alt_sec_path)
            extra  = max(0.0, alt_tt - orig_tt)

            # Congestion
            cong_scores = [
                state.sections[s].congestion_score
                for s in alt_sec_path if s in state.sections
            ]
            cong_avg = sum(cong_scores) / len(cong_scores) if cong_scores else 0.0

            # Single-line count
            n_sl = sum(
                1 for s in alt_sec_path
                if state.sections.get(s) and state.sections[s].is_single_line
            )

            # Cascade estimate: how many other trains does this reroute affect?
            cascade = self._estimate_cascade(alt_sec_path, train, state)

            score = (
                _W_TRAVEL     * extra +
                _W_CONG       * cong_avg +
                _W_SINGLELINE * n_sl +
                _W_CASCADE    * cascade
            )

            alts.append(RouteAlternative(
                train_id        = train.train_id,
                original_route  = train.remaining_route,
                alt_route       = alt_sec_path,
                bypasses        = list(hit_secs),
                extra_time_min  = extra,
                congestion_avg  = cong_avg,
                n_single_line   = n_sl,
                cascade_est     = cascade,
                total_score     = score,
            ))

        # If no alternative found, return infeasible placeholder
        if not alts:
            return [RouteAlternative(
                train_id=train.train_id, original_route=train.remaining_route,
                alt_route=[], bypasses=list(hit_secs), extra_time_min=9999,
                congestion_avg=1.0, n_single_line=0, cascade_est=0,
                total_score=9999, feasible=False,
                reason="No alternative route found — section is a bottleneck",
            )]

        return sorted(alts, key=lambda a: a.total_score)

    # ------------------------------------------------------------------
    def _estimate_cascade(
        self,
        alt_path:    List[str],
        rerouted:    TrainState,
        state:       NetworkState,
    ) -> float:
        """
        Estimate cascade delay introduced by sending this train on the alt path.
        = sum of (min_headway) for each other train already on that path section.
        """
        total = 0.0
        for s_id in alt_path:
            sec = state.sections.get(s_id)
            if sec is None:
                continue
            # Count other trains currently on or approaching this section
            other = [
                t for t in state.active_trains
                if t.train_id != rerouted.train_id and s_id in t.remaining_route[:4]
            ]
            total += len(other) * state.min_headway
        return total
