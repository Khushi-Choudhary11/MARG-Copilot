"""
services/optimizer/problem.py
==============================
Mathematical formulation and data model for the MARG optimization engine.

═══════════════════════════════════════════════════════════════════════════════
MATHEMATICAL FORMULATION
═══════════════════════════════════════════════════════════════════════════════

SETS
────
  T   = {t₁, t₂, …}        trains active in the planning horizon
  S   = {s₁, s₂, …}        directed track sections in the corridor
  L   ⊆ S                   single-line sections (crossing hazards)
  K   = {1,2,3}             priority tiers  (1=superfast, 2=mail/express, 3=goods)
  H   = [0, T_max]          discrete time horizon (minutes, integer)

PARAMETERS
──────────
  tt[t][s]      scheduled travel time of train t through section s  (min)
  w[t]          delay cost weight of train t  (higher = more important)
                  superfast=4, mail=3, express=2, goods=1
  cap[s]        section capacity (max trains simultaneously present)
  sl[s]         1 if single-line, 0 if double-track
  hd            minimum headway between consecutive trains (min), default=3
  T_sched[t][s] scheduled departure minute of train t from start of section s
  delay₀[t]     current accumulated delay of train t (min) at planning time
  blocked[s]    1 if section s is currently blocked (emergency)
  T_max         planning horizon (default 120 min)

DECISION VARIABLES
──────────────────
  D[t][s] ∈ ℤ₊           actual departure of train t from section s start (min)
  A[t][s] ∈ ℤ₊           actual arrival  of train t at section s end   (min)
  y[t₁,t₂,s] ∈ {0,1}    1 if train t₁ enters section s before t₂
                           (defined only when both trains traverse s)
  r[t][p] ∈ {0,1}        1 if train t uses route/path p  (rerouting only)
                           (defined only when section on t's route is blocked)

OBJECTIVE  — Minimise weighted total delay
──────────────────────────────────────────
  min  Σ_{t∈T}  w[t] · max(0,  A[t][s_final(t)] − T_sched[t][s_final(t)])

  Equivalently in CP-SAT (linearised):
  min  Σ_{t∈T}  w[t] · slack[t]
  where  slack[t] ≥ 0,  slack[t] ≥ A[t][final] − T_sched[t][final]

CONSTRAINTS
───────────
C1. Travel time linkage:
      A[t][s]  =  D[t][s]  +  tt[t][s]        ∀ t∈T, s∈route(t)

C2. Station continuity (no teleportation):
      D[t][s₂]  ≥  A[t][s₁]                   if s₁→s₂ consecutive for t

C3. Minimum headway on any section:
      y[t₁,t₂,s]=1  ⟹  D[t₂][s]  ≥  A[t₁][s] + hd   ∀ s∈S
      y[t₁,t₂,s]=0  ⟹  D[t₁][s]  ≥  A[t₂][s] + hd

C4. Ordering antisymmetry:
      y[t₁,t₂,s]  +  y[t₂,t₁,s]  =  1          ∀ t₁≠t₂, s shared

C5. Single-line crossing (only one train at a time):
      occupancy[t][s][τ]  ∈ {0,1}
      occupancy[t][s][τ]=1 iff D[t][s] ≤ τ < A[t][s]
      Σ_t  occupancy[t][s][τ]  ≤  1              ∀ s∈L, τ∈H
      (Implemented via non-overlapping interval constraints in CP-SAT)

C6. Section capacity:
      |{t : D[t][s] ≤ τ < A[t][s]}|  ≤  cap[s]   ∀ s∈S, τ∈H
      (Implemented via cumulative constraint in CP-SAT)

C7. Priority soft preference:
      y[t₁,t₂,s]=1  preferred when  w[t₁] > w[t₂]
      (encoded as soft constraint: add bonus w[t₁]−w[t₂] to objective when satisfied)

C8. Crossing loop (bidirectional single-line):
      Trains in opposite directions on same single-line section must not overlap
      (subset of C5; crossing permitted only at designated loop stations)

C9. Blocked section avoidance:
      blocked[s]=1  ⟹  r[t][p]=0  for all p containing s   ∀ t∈T

C10. Route uniqueness (rerouting):
       Σ_p  r[t][p]  =  1                        ∀ t needing rerouting

C11. Schedule adherence slack bound:
       slack[t]  ≤  T_max                        ∀ t∈T  (bounded domain)
═══════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple


# ── Priority weights (matches CSV `priority` column 0-2) ─────────────────────

PRIORITY_WEIGHT = {
    "superfast": 4,
    "mail":      3,
    "express":   2,
    "goods":     1,
}
INT_PRIORITY_WEIGHT = {0: 4, 1: 2, 2: 1}   # priority column: 0=high, 1=med, 2=low


# ── Enums ────────────────────────────────────────────────────────────────────

class DecisionType(Enum):
    PRECEDENCE  = auto()   # train A passes before train B on a section
    CROSSING    = auto()   # loop crossing order on single-line section
    OVERTAKING  = auto()   # faster train overtakes slower at a station
    REROUTE     = auto()   # train diverted to alternative route
    HOLD        = auto()   # train held at station for N minutes
    CLEAR       = auto()   # no action needed


class OptStatus(Enum):
    OPTIMAL     = auto()
    FEASIBLE    = auto()
    INFEASIBLE  = auto()
    TIMEOUT     = auto()
    ERROR       = auto()


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class TrainState:
    """Live state of one train at the time of optimization."""
    train_id:       str
    category:       str          # superfast / mail / express / goods
    priority:       int          # 0=high, 1=med, 2=low
    direction:      str          # UP / DOWN
    current_section:str          # section_id currently on (or next to enter)
    current_delay:  float        # accumulated delay in minutes
    sched_dep_min:  float        # scheduled departure from current section start
    remaining_route:List[str]    # ordered list of section_ids still to traverse
    sched_arrivals: Dict[str, float]   # section_id → scheduled arrival minute
    sched_departures:Dict[str, float]  # section_id → scheduled departure minute
    travel_times:   Dict[str, float]   # section_id → scheduled travel time (min)

    @property
    def weight(self) -> int:
        return PRIORITY_WEIGHT.get(self.category, 1)

    @property
    def final_section(self) -> Optional[str]:
        return self.remaining_route[-1] if self.remaining_route else None


@dataclass
class SectionState:
    """Current state of one track section."""
    section_id:      str
    from_station:    str
    to_station:      str
    length_km:       float
    capacity_per_hr: int
    is_single_line:  bool
    is_blocked:      bool = False
    block_duration:  float = 0.0      # minutes remaining if blocked
    trains_present:  List[str] = field(default_factory=list)
    congestion_score:float = 0.0


@dataclass
class NetworkState:
    """Full network state fed to the optimizer."""
    timestamp_min:  float                      # current time (minutes from midnight)
    trains:         Dict[str, TrainState]      # train_id → TrainState
    sections:       Dict[str, SectionState]    # section_id → SectionState
    horizon_min:    int = 120                  # planning horizon (minutes)
    min_headway:    int = 3                    # minimum headway (minutes)
    time_limit_sec: int = 10                   # solver time limit

    @property
    def blocked_sections(self) -> List[str]:
        return [s for s, st in self.sections.items() if st.is_blocked]

    @property
    def single_line_sections(self) -> List[str]:
        return [s for s, st in self.sections.items() if st.is_single_line]

    @property
    def active_trains(self) -> List[TrainState]:
        return list(self.trains.values())


@dataclass
class Decision:
    """One atomic optimization decision."""
    decision_type:  DecisionType
    train_id:       str
    section_id:     str
    detail:         str                        # human-readable description
    recommended_dep:Optional[float] = None     # recommended departure minute
    hold_minutes:   float = 0.0
    alt_route:      Optional[List[str]] = None # for REROUTE decisions
    affected_trains:List[str] = field(default_factory=list)
    delay_saved_min:float = 0.0                # estimated cascade delay saved
    confidence:     float = 1.0               # 0–1


@dataclass
class OptResult:
    """Complete output of one optimization run."""
    status:         OptStatus
    decisions:      List[Decision]
    objective_value:float                      # total weighted delay (minimised)
    baseline_delay: float                      # delay without optimization
    delay_saved:    float                      # objective_value improvement
    solve_time_sec: float
    horizon_min:    int
    n_trains:       int
    n_conflicts:    int
    message:        str = ""

    @property
    def summary(self) -> str:
        return (
            f"Status={self.status.name}  "
            f"Trains={self.n_trains}  "
            f"Conflicts={self.n_conflicts}  "
            f"Saved={self.delay_saved:.1f}min  "
            f"SolveTime={self.solve_time_sec:.2f}s"
        )
