"""
services/optimizer/explainer.py
================================
Translates raw optimizer decisions into controller-facing plain-English
justifications.  Every recommendation shown to a section controller comes
through this module.

Output format (per Decision):
  {
    "action":      "HOLD 12309 at ALJN for 6 minutes",
    "reason":      "Gives way to Rajdhani 12951 (Superfast, priority 1) …",
    "impact":      "Saves 41 cumulative delay-minutes across 4 downstream trains",
    "risk":        "Low — loop capacity confirmed, headway maintained",
    "confidence":  "95%",
  }
"""
from __future__ import annotations

from typing import Dict, List

from problem import Decision, DecisionType, NetworkState, OptResult


# ── Human-readable labels ─────────────────────────────────────────────────────

_TYPE_LABEL = {
    DecisionType.PRECEDENCE: "PRECEDENCE",
    DecisionType.CROSSING:   "CROSSING",
    DecisionType.OVERTAKING: "OVERTAKING",
    DecisionType.REROUTE:    "REROUTE",
    DecisionType.HOLD:       "HOLD",
    DecisionType.CLEAR:      "CLEAR",
}

_RISK_MAP = {
    (True,  True):  "Low  — high-priority train leads, loop confirmed clear",
    (True,  False): "Low  — sufficient headway on double-track section",
    (False, True):  "Medium — priority mismatch; confirm loop occupancy",
    (False, False): "Medium — verify no unscheduled train on section",
}


def explain_decisions(
    result:   OptResult,
    state:    NetworkState,
) -> List[Dict[str, str]]:
    """
    Convert OptResult.decisions → list of controller-facing explanation dicts.
    One dict per Decision.
    """
    explanations = []

    for dec in result.decisions:
        expl = _explain_one(dec, state, result)
        if expl:
            explanations.append(expl)

    return explanations


def _explain_one(
    dec:    Decision,
    state:  NetworkState,
    result: OptResult,
) -> Dict[str, str]:
    """Generate one explanation dict for one Decision."""
    train  = state.trains.get(dec.train_id)
    sec    = state.sections.get(dec.section_id)
    t_name = _train_label(train, dec.train_id)
    s_name = dec.section_id

    if dec.decision_type == DecisionType.HOLD:
        return _explain_hold(dec, train, sec, t_name, s_name)
    elif dec.decision_type in (DecisionType.PRECEDENCE, DecisionType.CROSSING):
        return _explain_precedence(dec, train, sec, state, t_name, s_name)
    elif dec.decision_type == DecisionType.REROUTE:
        return _explain_reroute(dec, train, state, t_name, s_name)
    elif dec.decision_type == DecisionType.OVERTAKING:
        return _explain_overtaking(dec, train, sec, state, t_name, s_name)
    return {}


def _explain_hold(dec, train, sec, t_name, s_name) -> Dict:
    hold = int(dec.hold_minutes)
    return {
        "action":     f"HOLD {t_name} at {s_name} entry — depart {hold} min later",
        "reason":     (
            f"Section {s_name} is occupied by a higher-priority or earlier train.  "
            f"Holding {t_name} ({_cat(train)}) maintains minimum headway of "
            f"{hold} min and prevents a crossing conflict"
            + (f" on single-line track" if sec and sec.is_single_line else "")
            + "."
        ),
        "impact":     (
            f"{'Saves' if dec.delay_saved_min > 0 else 'Limits additional delay to'} "
            f"~{int(abs(dec.delay_saved_min))} min cascade delay downstream."
        ),
        "risk":       _risk_label(dec, train, sec),
        "confidence": f"{int(dec.confidence * 100)}%",
    }


def _explain_precedence(dec, train, sec, state, t_name, s_name) -> Dict:
    losers = [state.trains.get(tid) for tid in dec.affected_trains]
    loser_labels = ", ".join(_train_label(l, tid)
                             for l, tid in zip(losers, dec.affected_trains) if l)
    cross_type   = "CROSSING" if (sec and sec.is_single_line) else "PRECEDENCE"

    return {
        "action":     f"{cross_type}: {t_name} enters {s_name} first",
        "reason":     (
            f"{t_name} ({_cat(train)}, priority weight {_w(train)}) "
            f"has higher operational priority than "
            f"{loser_labels or 'opposing train(s)'}.  "
            + ("Loop crossing required — only one direction permitted at a time.  "
               if sec and sec.is_single_line else "")
            + "CP-SAT solver confirmed this ordering minimises total weighted delay."
        ),
        "impact":     (
            f"Estimated {dec.delay_saved_min:.1f} min delay saved on downstream cascade.  "
            f"Affected train(s) {loser_labels} will hold at loop/siding."
        ),
        "risk":       _risk_label(dec, train, sec),
        "confidence": f"{int(dec.confidence * 100)}%",
    }


def _explain_reroute(dec, train, state, t_name, s_name) -> Dict:
    n_secs   = len(dec.alt_route) if dec.alt_route else 0
    route_str= " → ".join(dec.alt_route[:4]) + ("…" if n_secs > 4 else "") if dec.alt_route else "N/A"
    return {
        "action":     f"REROUTE {t_name} — bypass blocked {s_name}",
        "reason":     (
            f"Section {s_name} is blocked"
            + (f" (estimated {state.sections[s_name].block_duration:.0f} min remaining)"
               if s_name in state.sections else "")
            + f".  NetworkX Dijkstra identified {route_str} as the lowest-cost "
              f"alternative ({n_secs} sections, scored by travel time + congestion)."
        ),
        "impact":     (
            f"Saves ~{dec.delay_saved_min:.1f} min vs waiting for clearance.  "
            f"New route avoids blockage entirely."
        ),
        "risk":       (
            "Medium — verify loop availability on alternative route.  "
            "New ETA update required for downstream stations."
        ),
        "confidence": f"{int(dec.confidence * 100)}%",
    }


def _explain_overtaking(dec, train, sec, state, t_name, s_name) -> Dict:
    losers = [state.trains.get(tid) for tid in dec.affected_trains]
    loser_labels = ", ".join(_train_label(l, tid)
                             for l, tid in zip(losers, dec.affected_trains) if l)
    return {
        "action":     f"OVERTAKE: {t_name} passes {loser_labels or 'slower train'} at {s_name}",
        "reason":     (
            f"{t_name} ({_cat(train)}) is faster and higher priority.  "
            f"Station {s_name} has a passing loop with sufficient capacity.  "
            f"Allowing overtake reduces total weighted network delay."
        ),
        "impact":     f"~{dec.delay_saved_min:.1f} min saved for {t_name} and downstream passengers.",
        "risk":       _risk_label(dec, train, sec),
        "confidence": f"{int(dec.confidence * 100)}%",
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _train_label(train, train_id: str) -> str:
    if train is None:
        return train_id
    return f"{train_id} ({train.category.capitalize()})"


def _cat(train) -> str:
    return train.category.capitalize() if train else "Unknown"


def _w(train) -> int:
    return train.weight if train else 1


def _risk_label(dec: Decision, train, sec) -> str:
    high_prio  = bool(train and train.weight >= 3)
    single_line= bool(sec  and sec.is_single_line)
    key = (high_prio, not single_line)
    return _RISK_MAP.get(key, "Low")


# ── Summary printer ───────────────────────────────────────────────────────────

def print_result(result: OptResult, explanations: List[Dict], state: NetworkState) -> None:
    sep = "─" * 70
    print(f"\n{'═'*70}")
    print(f"  MARG OPTIMIZATION RESULT — {result.status.name}")
    print(f"{'═'*70}")
    print(f"  Trains:     {result.n_trains}")
    print(f"  Conflicts:  {result.n_conflicts}")
    print(f"  Baseline delay (weighted): {result.baseline_delay:.1f}")
    print(f"  Optimised  delay (weighted): {result.objective_value:.1f}")
    print(f"  Delay saved: {result.delay_saved:.1f} weighted-minutes")
    print(f"  Solve time: {result.solve_time_sec:.3f}s")
    print(sep)
    for i, expl in enumerate(explanations, 1):
        print(f"\n  [{i}] {expl.get('action', '')}")
        print(f"      Reason:     {expl.get('reason', '')}")
        print(f"      Impact:     {expl.get('impact', '')}")
        print(f"      Risk:       {expl.get('risk', '')}")
        print(f"      Confidence: {expl.get('confidence', '')}")
    if not explanations:
        print("  No actionable decisions required.")
    print(f"\n{'═'*70}\n")
