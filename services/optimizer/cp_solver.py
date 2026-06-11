"""
services/optimizer/cp_solver.py
================================
OR-Tools CP-SAT solver for train scheduling.

Solves the joint precedence + crossing + overtaking problem for all
trains active in the planning horizon on a given corridor.

CP-SAT model summary
────────────────────
  For each (train t, section s) in the active set:
    dep[t][s]  = IntVar(lb, ub)   actual departure  (minutes, integer)
    arr[t][s]  = IntVar(lb, ub)   actual arrival    (minutes, integer)
    intvl[t][s]= IntervalVar      occupancy interval [dep, dep+tt, arr]

  For each pair (t1, t2) sharing section s:
    before[t1][t2][s] = BoolVar   t1 departs before t2

  Objective: minimise  Σ_t  w[t] · slack[t]
    slack[t] = max(0, arr[t][final] − sched_arr[t][final])

  Constraints enforced:
    C1  arr = dep + tt             (travel time, exact)
    C2  dep[t][s2] ≥ arr[t][s1]   (continuity, with optional dwell)
    C3  headway via AddNoOverlap / manual implication
    C5  single-line: AddNoOverlap on intervals per section
    C6  capacity:    AddCumulative on intervals per section
    C4  antisymmetry: before[t1,t2] + before[t2,t1] = 1
    C7  priority bonus: objective term per pair

Returns: solved departure/arrival times for every (train, section) pair,
plus the binary ordering decisions.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from problem import (
    Decision, DecisionType, NetworkState, OptResult, OptStatus,
    TrainState,
)


# ── Constants ──────────────────────────────────────────────────────────────────

_MINUTES_SCALE  = 1            # already in integer minutes
_BIG_M          = 9_999        # upper bound on departure time


# ── Solver ─────────────────────────────────────────────────────────────────────

class CpScheduler:
    """
    Wraps the OR-Tools CP-SAT model for train scheduling.

    Usage
    -----
        scheduler = CpScheduler()
        result    = scheduler.solve(state)
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    # ------------------------------------------------------------------
    def solve(self, state: NetworkState) -> Tuple[OptResult, Dict]:
        """
        Build and solve the CP-SAT model for the given NetworkState.

        Returns
        -------
        (OptResult, raw_schedule)
        raw_schedule : dict  (train_id, section_id) → {"dep": int, "arr": int}
        """
        t_start = time.time()
        model   = cp_model.CpModel()
        now     = int(state.timestamp_min)
        horizon = now + state.horizon_min
        trains  = state.active_trains

        if not trains:
            return self._empty_result(t_start), {}

        # ── Variables ──────────────────────────────────────────────────
        dep: Dict[Tuple, cp_model.IntVar]      = {}
        arr: Dict[Tuple, cp_model.IntVar]      = {}
        intvl: Dict[Tuple, cp_model.IntervalVar] = {}
        before: Dict[Tuple, cp_model.IntVar]   = {}

        for t in trains:
            for s_id in t.remaining_route:
                sec   = state.sections.get(s_id)
                if sec is None:
                    continue
                tt    = int(max(1, round(t.travel_times.get(s_id, sec.length_km / 70 * 60))))
                sched = int(t.sched_departures.get(s_id, now))
                lb    = max(now, sched)          # can't depart in the past
                ub    = min(horizon, now + state.horizon_min)
                if lb > ub:                          # section beyond planning horizon — skip
                    continue

                key       = (t.train_id, s_id)
                dep[key]  = model.new_int_var(lb, ub,      f"dep_{t.train_id}_{s_id}")
                arr[key]  = model.new_int_var(lb + tt, ub + tt, f"arr_{t.train_id}_{s_id}")
                intvl[key]= model.new_interval_var(
                    dep[key], tt, arr[key], f"intvl_{t.train_id}_{s_id}"
                )

        # ── C1: Travel time ────────────────────────────────────────────
        for t in trains:
            for s_id in t.remaining_route:
                sec = state.sections.get(s_id)
                if sec is None:
                    continue
                tt  = int(max(1, round(t.travel_times.get(s_id, sec.length_km / 70 * 60))))
                key = (t.train_id, s_id)
                if key in dep and key in arr:
                    model.add(arr[key] == dep[key] + tt)

        # ── C2: Station continuity ─────────────────────────────────────
        for t in trains:
            route = t.remaining_route
            for i in range(len(route) - 1):
                s1, s2 = route[i], route[i + 1]
                k1, k2 = (t.train_id, s1), (t.train_id, s2)
                if k1 in arr and k2 in dep:
                    model.add(dep[k2] >= arr[k1])   # C2: no teleportation

        # ── C3 + C4 + C5: Headway and ordering ────────────────────────
        # Group trains by section
        section_trains: Dict[str, List[TrainState]] = {}
        for t in trains:
            for s_id in t.remaining_route:
                if (t.train_id, s_id) in dep:
                    section_trains.setdefault(s_id, []).append(t)

        for s_id, s_trains in section_trains.items():
            sec = state.sections.get(s_id)
            if sec is None or len(s_trains) < 2:
                continue

            hd = state.min_headway

            # C5: Single-line — no overlap at all (AddNoOverlap)
            if sec.is_single_line:
                s_intervals = [intvl[(t.train_id, s_id)]
                               for t in s_trains if (t.train_id, s_id) in intvl]
                if s_intervals:
                    model.add_no_overlap(s_intervals)

            # C3 + C4: Headway + ordering for all pairs
            for i, t1 in enumerate(s_trains):
                for t2 in s_trains[i + 1:]:
                    k1 = (t1.train_id, s_id)
                    k2 = (t2.train_id, s_id)
                    if k1 not in dep or k2 not in dep:
                        continue

                    b = model.new_bool_var(f"before_{t1.train_id}_{t2.train_id}_{s_id}")
                    before[(t1.train_id, t2.train_id, s_id)] = b

                    # If b=1: t1 before t2  → dep[t2] ≥ arr[t1] + headway
                    model.add(dep[k2] >= arr[k1] + hd).only_enforce_if(b)
                    # If b=0: t2 before t1  → dep[t1] ≥ arr[k2] + headway
                    model.add(dep[k1] >= arr[k2] + hd).only_enforce_if(b.negated())

        # ── C6: Section capacity (cumulative) ─────────────────────────
        for s_id, s_trains in section_trains.items():
            sec = state.sections.get(s_id)
            if sec is None:
                continue
            s_intervals = [intvl[(t.train_id, s_id)]
                           for t in s_trains if (t.train_id, s_id) in intvl]
            demands     = [1] * len(s_intervals)
            cap_per_min = max(1, int(sec.capacity_per_hr / 60) + 1)
            if s_intervals:
                model.add_cumulative(s_intervals, demands, cap_per_min)

        # ── Objective: minimise weighted delay ─────────────────────────
        slack_vars: List[Tuple[int, cp_model.IntVar]] = []
        priority_bonuses = []

        for t in trains:
            if not t.final_section or (t.train_id, t.final_section) not in arr:
                continue
            sched_final = int(t.sched_arrivals.get(t.final_section, horizon))
            slack       = model.new_int_var(0, state.horizon_min,
                                            f"slack_{t.train_id}")
            model.add_max_equality(slack, [arr[(t.train_id, t.final_section)] - sched_final, 0])
            slack_vars.append((t.weight, slack))

        # C7: Priority bonus for ordering decisions
        # If higher-priority train gets precedence, reduce effective cost
        for (t1_id, t2_id, s_id), b_var in before.items():
            t1 = state.trains.get(t1_id)
            t2 = state.trains.get(t2_id)
            if t1 and t2 and t1.weight > t2.weight:
                # Reward giving precedence to higher-priority train
                bonus = model.new_int_var(0, 5, f"bonus_{t1_id}_{t2_id}_{s_id}")
                model.add(bonus == (t1.weight - t2.weight)).only_enforce_if(b_var)
                model.add(bonus == 0).only_enforce_if(b_var.negated())
                priority_bonuses.append(bonus)

        obj_terms = [w * sl for w, sl in slack_vars]
        if priority_bonuses:
            obj_terms += [-b for b in priority_bonuses]

        if obj_terms:
            model.minimize(sum(obj_terms))

        # ── Solve ──────────────────────────────────────────────────────
        solver   = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds  = state.time_limit_sec
        solver.parameters.num_search_workers   = 4
        solver.parameters.log_search_progress  = self.verbose

        status_code = solver.solve(model)

        solve_time = time.time() - t_start

        # Map OR-Tools status
        status_map = {
            cp_model.OPTIMAL:   OptStatus.OPTIMAL,
            cp_model.FEASIBLE:  OptStatus.FEASIBLE,
            cp_model.INFEASIBLE:OptStatus.INFEASIBLE,
            cp_model.UNKNOWN:   OptStatus.TIMEOUT,
        }
        opt_status = status_map.get(status_code, OptStatus.ERROR)

        if opt_status in (OptStatus.INFEASIBLE, OptStatus.ERROR):
            return OptResult(
                status=opt_status, decisions=[], objective_value=float("inf"),
                baseline_delay=0, delay_saved=0, solve_time_sec=solve_time,
                horizon_min=state.horizon_min, n_trains=len(trains),
                n_conflicts=0, message=f"CP-SAT: {solver.status_name(status_code)}",
            ), {}

        # ── Extract solution ──────────────────────────────────────────
        raw_schedule: Dict[Tuple[str,str], Dict] = {}
        for (t_id, s_id), var in dep.items():
            a_var = arr.get((t_id, s_id))
            raw_schedule[(t_id, s_id)] = {
                "dep": solver.value(var),
                "arr": solver.value(a_var) if a_var else None,
            }

        # Build Decision objects from ordering variables
        decisions: List[Decision] = []
        baseline_delay = 0.0
        opt_delay      = 0.0

        for t in trains:
            if t.final_section and (t.train_id, t.final_section) in arr:
                a_var      = arr[(t.train_id, t.final_section)]
                sched_fin  = t.sched_arrivals.get(t.final_section, now + 120)
                actual_arr = solver.value(a_var)
                baseline_delay += t.weight * max(0, t.current_delay)
                opt_delay      += t.weight * max(0, actual_arr - sched_fin)

        for (t1_id, t2_id, s_id), b_var in before.items():
            val = solver.boolean_value(b_var)
            winner = t1_id if val else t2_id
            loser  = t2_id if val else t1_id
            t_w    = state.trains.get(winner)
            t_l    = state.trains.get(loser)

            sec    = state.sections.get(s_id)
            d_type = (DecisionType.CROSSING if sec and sec.is_single_line
                      else DecisionType.PRECEDENCE)

            # Estimate delay saved
            w_delay = state.trains[winner].current_delay if winner in state.trains else 0
            l_delay = state.trains[loser].current_delay  if loser  in state.trains else 0
            saved   = max(0, l_delay - state.min_headway) if t_w and t_l and t_w.weight > t_l.weight else 0

            decisions.append(Decision(
                decision_type   = d_type,
                train_id        = winner,
                section_id      = s_id,
                detail          = (
                    f"{'CROSS' if d_type==DecisionType.CROSSING else 'PRECEDENCE'}: "
                    f"{winner} passes section {s_id} before {loser}"
                ),
                affected_trains = [loser],
                delay_saved_min = saved,
                confidence      = 0.95 if opt_status == OptStatus.OPTIMAL else 0.80,
            ))

        # Detect hold decisions (trains whose dep is pushed back significantly)
        for t in trains:
            for s_id in t.remaining_route[:3]:
                key = (t.train_id, s_id)
                if key in raw_schedule:
                    sched_dep = t.sched_departures.get(s_id, now)
                    actual_dep= raw_schedule[key]["dep"]
                    hold      = actual_dep - sched_dep
                    if hold >= 2:
                        decisions.append(Decision(
                            decision_type   = DecisionType.HOLD,
                            train_id        = t.train_id,
                            section_id      = s_id,
                            detail          = (
                                f"HOLD: {t.train_id} at {s_id} start — "
                                f"depart {actual_dep} instead of sched {int(sched_dep)} "
                                f"(+{hold:.0f} min)"
                            ),
                            hold_minutes    = hold,
                            recommended_dep = actual_dep,
                            delay_saved_min = max(0, t.current_delay - hold),
                        ))

        delay_saved = max(0, baseline_delay - opt_delay)

        result = OptResult(
            status          = opt_status,
            decisions       = decisions,
            objective_value = opt_delay,
            baseline_delay  = baseline_delay,
            delay_saved     = delay_saved,
            solve_time_sec  = solve_time,
            horizon_min     = state.horizon_min,
            n_trains        = len(trains),
            n_conflicts     = len([d for d in decisions
                                   if d.decision_type != DecisionType.HOLD]),
            message         = solver.status_name(status_code),
        )
        return result, raw_schedule

    @staticmethod
    def _empty_result(t_start: float) -> OptResult:
        return OptResult(
            status=OptStatus.OPTIMAL, decisions=[], objective_value=0,
            baseline_delay=0, delay_saved=0,
            solve_time_sec=time.time()-t_start,
            horizon_min=0, n_trains=0, n_conflicts=0,
            message="No active trains",
        )
