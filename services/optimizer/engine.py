"""
services/optimizer/engine.py
=============================
OptimizationEngine — the single entry-point that orchestrates:
  1. conflict detection   (graph_utils.detect_conflicts)
  2. precedence / crossing scheduling  (cp_solver.CpScheduler)
  3. emergency rerouting  (rerouter.EmergencyRerouter)
  4. decision merging + deduplication
  5. objective accounting

Usage
-----
    from problem import NetworkState, TrainState, SectionState
    from engine import OptimizationEngine

    engine = OptimizationEngine()
    result, explanations_ctx = engine.optimize(state)
"""
from __future__ import annotations

import time
import sys
import os
from typing import List, Tuple, Optional

sys.path.insert(0, os.path.dirname(__file__))

from problem import (
    Decision, DecisionType, NetworkState, OptResult, OptStatus,
    TrainState, SectionState, PRIORITY_WEIGHT,
)
from graph_utils import (
    build_corridor_graph, detect_conflicts, ConflictRecord,
    find_route, k_shortest_routes,
)
from cp_solver import CpScheduler
from rerouter import EmergencyRerouter


class OptimizationEngine:
    """
    Main orchestrator for the MARG optimization pipeline.

    Parameters
    ----------
    use_cp      : run CP-SAT solver for precedence/crossing (default True).
                  Set False to skip when no conflicts or for speed.
    use_reroute : run emergency rerouter for blocked sections (default True).
    cp_timeout  : seconds budget for the CP-SAT solver (default 10s).
    """

    def __init__(
        self,
        use_cp:      bool  = True,
        use_reroute: bool  = True,
        cp_timeout:  float = 10.0,
    ):
        self.use_cp      = use_cp
        self.use_reroute = use_reroute
        self.cp_timeout  = cp_timeout

    # ── Public API ────────────────────────────────────────────────────────────

    def optimize(
        self,
        state: NetworkState,
    ) -> Tuple[OptResult, List[ConflictRecord]]:
        """
        Run the full optimization pipeline on the given network state.

        Returns
        -------
        result     : OptResult  — decisions, objective, status, timing
        conflicts  : List[ConflictRecord] — detected conflicts (for UI display)
        """
        t0 = time.time()

        # ── 1. Build corridor graph ──────────────────────────────────────────
        G = build_corridor_graph(
            sections=state.sections,
        )

        # ── 2. Detect conflicts ──────────────────────────────────────────────
        conflicts = detect_conflicts(state)
        n_blocked  = sum(1 for c in conflicts if c.conflict_type == "blocked")
        n_crossing = sum(1 for c in conflicts if c.conflict_type == "crossing")
        n_headway  = sum(1 for c in conflicts if c.conflict_type == "headway")

        all_decisions: List[Decision] = []
        cp_status  = OptStatus.OPTIMAL
        cp_obj     = 0.0
        baseline   = _baseline_delay(state)

        # ── 3. CP-SAT: precedence + crossing ────────────────────────────────
        if self.use_cp and (n_crossing > 0 or n_headway > 0):
            scheduler = CpScheduler(verbose=False)
            cp_result, _ = scheduler.solve(state)
            cp_status = cp_result.status
            cp_obj    = cp_result.objective_value
            all_decisions.extend(cp_result.decisions)

        # ── 4. Emergency rerouter ────────────────────────────────────────────
        reroute_decisions: List[Decision] = []
        if self.use_reroute and n_blocked > 0:
            rerouter = EmergencyRerouter(G)
            _, reroute_decisions = rerouter.reroute(state, conflicts)
            all_decisions.extend(reroute_decisions)

        # ── 5. Merge & deduplicate ───────────────────────────────────────────
        merged = _deduplicate(all_decisions)

        # ── 6. Add HOLD decisions for unresolved headway conflicts ───────────
        hold_decisions = _synthesise_holds(conflicts, merged, state)
        merged.extend(hold_decisions)

        # ── 7. Rank by impact ────────────────────────────────────────────────
        merged.sort(key=lambda d: (-d.delay_saved_min, _type_rank(d.decision_type)))

        # ── 8. Aggregate accounting ──────────────────────────────────────────
        total_saved = sum(max(0, d.delay_saved_min) for d in merged)
        final_obj   = max(0.0, baseline - total_saved)

        # Propagate CP status; downgrade if rerouting found alternatives
        if len(reroute_decisions) > 0 and cp_status == OptStatus.OPTIMAL:
            final_status = OptStatus.OPTIMAL
        elif cp_status in (OptStatus.INFEASIBLE, OptStatus.ERROR):
            final_status = OptStatus.FEASIBLE   # rerouting may still help
        else:
            final_status = cp_status if merged else OptStatus.OPTIMAL

        result = OptResult(
            status          = final_status,
            decisions       = merged,
            objective_value = final_obj,
            baseline_delay  = baseline,
            delay_saved     = total_saved,
            solve_time_sec  = time.time() - t0,
            horizon_min     = state.horizon_min,
            n_trains        = len(state.trains),
            n_conflicts     = len(conflicts),
        )

        return result, conflicts


# ── Internal helpers ──────────────────────────────────────────────────────────

def _baseline_delay(state: NetworkState) -> float:
    """Weighted sum of current delays — the do-nothing baseline."""
    total = 0.0
    for train in state.trains.values():
        w = PRIORITY_WEIGHT.get(train.category, 1)
        total += w * max(0, train.current_delay)
    return total


def _deduplicate(decisions: List[Decision]) -> List[Decision]:
    """
    Remove duplicate decisions targeting the same (train, section, type).
    When duplicates exist, keep the one with higher delay_saved_min.
    """
    seen: dict = {}
    for d in decisions:
        key = (d.train_id, d.section_id, d.decision_type)
        if key not in seen or d.delay_saved_min > seen[key].delay_saved_min:
            seen[key] = d
    return list(seen.values())


def _synthesise_holds(
    conflicts: List[ConflictRecord],
    existing:  List[Decision],
    state:     NetworkState,
) -> List[Decision]:
    """
    For headway conflicts not yet covered by CP-SAT output, generate
    a conservative HOLD decision for the lower-priority train.
    """
    existing_keys = {(d.train_id, d.section_id) for d in existing}
    holds: List[Decision] = []

    for c in conflicts:
        if c.conflict_type != "headway":
            continue
        if len(c.trains) < 2:
            continue

        # Sort trains: lower priority → hold
        trains_sorted = sorted(
            c.trains,
            key=lambda tid: PRIORITY_WEIGHT.get(
                state.trains[tid].category if tid in state.trains else "goods", 1
            ),
        )
        hold_tid = trains_sorted[0]   # lowest priority holds
        sec_id   = c.section_id

        if (hold_tid, sec_id) in existing_keys:
            continue

        hold_min = getattr(c, "time_window", 5)   # default 5 min hold
        hold_min = hold_min if isinstance(hold_min, (int, float)) else 5

        train = state.trains.get(hold_tid)
        holds.append(
            Decision(
                decision_type   = DecisionType.HOLD,
                train_id        = hold_tid,
                section_id      = sec_id,
                detail          = f"Hold {hold_min:.0f} min — headway conflict",
                delay_saved_min = max(0.0, hold_min * 0.5),
                hold_minutes    = hold_min,
                confidence      = 0.80,
                affected_trains = [t for t in c.trains if t != hold_tid],
            )
        )

    return holds


_TYPE_ORDER = {
    DecisionType.REROUTE:    0,
    DecisionType.CROSSING:   1,
    DecisionType.PRECEDENCE: 2,
    DecisionType.OVERTAKING: 3,
    DecisionType.HOLD:       4,
    DecisionType.CLEAR:      5,
}

def _type_rank(dt: DecisionType) -> int:
    return _TYPE_ORDER.get(dt, 9)
