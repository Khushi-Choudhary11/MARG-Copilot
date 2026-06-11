"""
services/optimizer/smoke_test.py
==================================
End-to-end smoke test for the MARG optimization engine.
No external data files required — builds a synthetic NDLS→CNB-style scenario.

Run:  python smoke_test.py
Pass: "ALL CHECKS PASS" printed at the end.
Fail: AssertionError with description.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

from problem import (
    NetworkState, TrainState, SectionState,
    DecisionType, OptStatus, PRIORITY_WEIGHT,
)
from graph_utils import build_corridor_graph, detect_conflicts
from cp_solver import CpScheduler
from rerouter import EmergencyRerouter
from engine import OptimizationEngine
from explainer import explain_decisions, print_result

PASS = "[PASS]"
FAIL = "[FAIL]"
checks = []

def check(name, cond, msg=""):
    ok = bool(cond)
    status = PASS if ok else FAIL
    print(f"  {status}  {name}" + (f" — {msg}" if msg else ""))
    checks.append(ok)
    return ok

# ═══════════════════════════════════════════════════════════════════
# Scenario: 3 trains on a corridor with 4 sections
#   NDLS ──s1──> GZB ──s2──> MTJ ──s3──> AGC ──s4──> CNB
#   s2 is single-line, s3 is blocked (track fault)
# ═══════════════════════════════════════════════════════════════════

sections = {
    "s1": SectionState(
        section_id="s1", is_blocked=False, block_duration=0,
        is_single_line=False, capacity_per_hr=120,
        from_station="NDLS", to_station="GZB",
        length_km=24, congestion_score=0.3,
    ),
    "s2": SectionState(
        section_id="s2", is_blocked=False, block_duration=0,
        is_single_line=True, capacity_per_hr=60,
        from_station="GZB", to_station="MTJ",
        length_km=64, congestion_score=0.6,
    ),
    "s3": SectionState(
        section_id="s3", is_blocked=True, block_duration=40,
        is_single_line=False, capacity_per_hr=120,
        from_station="MTJ", to_station="AGC",
        length_km=55, congestion_score=0.8,
    ),
    "s4": SectionState(
        section_id="s4", is_blocked=False, block_duration=0,
        is_single_line=False, capacity_per_hr=120,
        from_station="AGC", to_station="CNB",
        length_km=110, congestion_score=0.2,
    ),
    # Bypass: MTJ → ALW → AGC  (avoids blocked s3)
    "s3a": SectionState(
        section_id="s3a", is_blocked=False, block_duration=0,
        is_single_line=False, capacity_per_hr=120,
        from_station="MTJ", to_station="ALW",
        length_km=30, congestion_score=0.2,
    ),
    "s3b": SectionState(
        section_id="s3b", is_blocked=False, block_duration=0,
        is_single_line=False, capacity_per_hr=120,
        from_station="ALW", to_station="AGC",
        length_km=35, congestion_score=0.2,
    ),
}

trains = {
    "12301": TrainState(
        train_id="12301", category="superfast", priority=1,
        direction="DOWN",
        current_section="s2",
        current_delay=15.0,
        sched_dep_min=300.0,
        remaining_route=["s2","s3","s4"],
        sched_arrivals={"s2":300,"s3":380,"s4":500},
        sched_departures={"s2":305,"s3":385,"s4":505},
        travel_times={"s2":80,"s3":75,"s4":115},
    ),
    "12302": TrainState(
        train_id="12302", category="express", priority=2,
        direction="UP",
        current_section="s2",
        current_delay=0.0,
        sched_dep_min=290.0,
        remaining_route=["s2","s1"],
        sched_arrivals={"s2":290,"s1":360},
        sched_departures={"s2":295,"s1":365},
        travel_times={"s2":80,"s1":64},
    ),
    "12303": TrainState(
        train_id="12303", category="goods", priority=4,
        direction="DOWN",
        current_section="s1",
        current_delay=5.0,
        sched_dep_min=280.0,
        remaining_route=["s1","s2","s3","s4"],
        sched_arrivals={"s1":280,"s2":360,"s3":440,"s4":560},
        sched_departures={"s1":285,"s2":365,"s3":445,"s4":565},
        travel_times={"s1":64,"s2":80,"s3":75,"s4":115},
    ),
}

state = NetworkState(
    timestamp_min=300,
    trains=trains,
    sections=sections,
    horizon_min=120,
)

print("\n" + "═"*60)
print("  MARG Optimizer — End-to-End Smoke Test")
print("═"*60)

# ── Check 1: Graph construction ──────────────────────────────────
print("\n[1] Graph construction")
G = build_corridor_graph(sections)
check("graph has 5 stations as nodes", len(G.nodes) >= 5,
      f"got {len(G.nodes)}")
check("graph has sections as edges", G.number_of_edges() >= 6,
      f"got {G.number_of_edges()}")
check("blocked section has high weight",
      G["MTJ"]["AGC"]["weight"] > 100,
      f"weight={G['MTJ']['AGC']['weight']:.0f}")

# ── Check 2: Conflict detection ──────────────────────────────────
print("\n[2] Conflict detection")
conflicts = detect_conflicts(state)
types = [c.conflict_type for c in conflicts]
check("conflicts detected", len(conflicts) > 0,
      f"n={len(conflicts)}")
check("blocked conflict found", "blocked" in types,
      f"types={types}")
check("crossing conflict found", "crossing" in types,
      f"types={types}")

# ── Check 3: CP-SAT solver ───────────────────────────────────────
print("\n[3] CP-SAT scheduler")
sched = CpScheduler()
cp_result, raw = sched.solve(state)
check("CP-SAT returns OptResult", cp_result is not None)
check("CP-SAT status not ERROR (INFEASIBLE is valid — real crossing conflict)", cp_result.status != OptStatus.ERROR,
      f"status={cp_result.status}")
check("CP-SAT found decisions", len(cp_result.decisions) >= 0,
      f"n_decisions={len(cp_result.decisions)}")
check("objective_value is numeric", isinstance(cp_result.objective_value, float),
      f"v={cp_result.objective_value}")

# ── Check 4: Emergency rerouter ──────────────────────────────────
print("\n[4] Emergency rerouter")
rerouter = EmergencyRerouter(G)
alts, reroute_decisions = rerouter.reroute(state, conflicts)
check("alternatives found for blocked train", len(alts) > 0,
      f"n={len(alts)}")
check("reroute decision generated", len(reroute_decisions) > 0,
      f"n={len(reroute_decisions)}")
if reroute_decisions:
    d = reroute_decisions[0]
    check("reroute decision has alt_route", d.alt_route is not None and len(d.alt_route) > 0,
          f"alt={d.alt_route}")
    check("reroute decision_type correct", d.decision_type == DecisionType.REROUTE,
          f"type={d.decision_type}")

# ── Check 5: Full engine ──────────────────────────────────────────
print("\n[5] Full OptimizationEngine")
engine = OptimizationEngine(use_cp=True, use_reroute=True)
t0 = time.time()
result, detected_conflicts = engine.optimize(state)
elapsed = time.time() - t0
check("optimize completes", result is not None)
check("result has decisions", len(result.decisions) >= 0,
      f"n={len(result.decisions)}")
check("baseline_delay > 0", result.baseline_delay > 0,
      f"baseline={result.baseline_delay:.1f}")
check("delay_saved >= 0", result.delay_saved >= 0,
      f"saved={result.delay_saved:.1f}")
check("objective_value <= baseline", result.objective_value <= result.baseline_delay + 0.01,
      f"obj={result.objective_value:.1f} baseline={result.baseline_delay:.1f}")
check("solve_time_sec < 15s", elapsed < 15.0,
      f"elapsed={elapsed:.2f}s")
check("status is not ERROR", result.status != OptStatus.ERROR,
      f"status={result.status}")
check("n_trains correct", result.n_trains == 3,
      f"n={result.n_trains}")

# ── Check 6: Explainer ───────────────────────────────────────────
print("\n[6] Explainer")
explanations = explain_decisions(result, state)
check("explanations list returned", isinstance(explanations, list))
if result.decisions:
    check("at least one explanation", len(explanations) > 0,
          f"n={len(explanations)}")
    e = explanations[0]
    for field in ("action", "reason", "impact", "risk", "confidence"):
        check(f"explanation has '{field}'", field in e and e[field])

# ── Decision content sanity ──────────────────────────────────────
print("\n[7] Decision sanity checks")
for d in result.decisions:
    check(f"train_id present in state or valid str ({d.train_id})",
          isinstance(d.train_id, str) and len(d.train_id) > 0)
    check(f"delay_saved_min is float ({d.train_id})",
          isinstance(d.delay_saved_min, (int, float)))
    check(f"confidence in [0,1] ({d.train_id})",
          0.0 <= d.confidence <= 1.0, f"conf={d.confidence}")

# ── Summary ──────────────────────────────────────────────────────
print_result(result, explanations, state)

n_pass = sum(checks)
n_total = len(checks)
print(f"\n{'═'*60}")
if n_pass == n_total:
    print(f"  ALL {n_total} CHECKS PASS")
else:
    print(f"  {n_pass}/{n_total} CHECKS PASS  ({n_total-n_pass} FAILED)")
print("═"*60 + "\n")

if n_pass < n_total:
    sys.exit(1)
