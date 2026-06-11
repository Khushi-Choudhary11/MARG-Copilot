"""
Section State
=============
Runtime state of a track section: occupancy, disruptions, and headway tracking.
A section is the directed track between two adjacent stations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


class SectionCondition(Enum):
    CLEAR       = auto()   # Normal operations
    CONGESTED   = auto()   # High utilisation, speed reduced
    SIGNAL_FAIL = auto()   # Signal failure — trains may proceed with caution
    BLOCKED     = auto()   # Hard block — no trains can enter


@dataclass
class SectionState:
    """
    Mutable runtime state for one directed track section.

    Parameters
    ----------
    section_id:
        Unique identifier (e.g. 'NDLS_TKJ_UP').
    from_station, to_station:
        Station IDs at each end of the section.
    length_km:
        Physical length.
    max_speed_passenger_kmh, max_speed_freight_kmh:
        Maximum permitted speeds under normal conditions.
    theoretical_capacity_per_hour:
        Maximum trains per hour under ideal conditions.
    is_single_line:
        Whether this section is single-track (crossing constraints apply).
    base_travel_min_passenger, base_travel_min_freight:
        Baseline travel times (no disruption).
    """

    section_id:                     str
    from_station:                   str
    to_station:                     str
    length_km:                      float
    max_speed_passenger_kmh:        float
    max_speed_freight_kmh:          float
    theoretical_capacity_per_hour:  float
    is_single_line:                 bool
    base_travel_min_passenger:      float
    base_travel_min_freight:        float

    # ── Runtime state (mutable) ───────────────────────────────────────────────

    condition: SectionCondition = field(
        default=SectionCondition.CLEAR, init=False
    )

    # Trains currently on this section (in transit)
    trains_on_section: set[str] = field(default_factory=set, init=False)

    # Congestion score driven by occupancy [0, 1]
    congestion_score: float = field(default=0.0, init=False)

    # Weather speed factor [0.15, 1.0]
    weather_speed_factor: float = field(default=1.0, init=False)

    # Active caution order (km/h), None if clear
    caution_order_kmh: Optional[float] = field(default=None, init=False)

    # Signal state
    signal_failed: bool = field(default=False, init=False)
    signal_restore_time: Optional[float] = field(default=None, init=False)

    # Headway tracking: sim_time when the last train entered the section
    last_entry_time: Optional[float] = field(default=None, init=False)
    min_headway_minutes: float = field(default=3.0, init=False)  # IR absolute block

    # Cumulative counters
    total_trains_passed: int = field(default=0, init=False)
    total_delay_minutes: float = field(default=0.0, init=False)

    # ── Effective travel time ─────────────────────────────────────────────────

    def effective_travel_min(self, is_passenger: bool = True) -> float:
        """
        Compute the current effective travel time considering:
        - Congestion (increases travel time)
        - Weather (reduces effective speed)
        - Caution order (reduces speed)
        - Hard block (returns infinity)
        """
        if self.condition == SectionCondition.BLOCKED:
            return float("inf")

        base = (
            self.base_travel_min_passenger
            if is_passenger
            else self.base_travel_min_freight
        )
        max_speed = (
            self.max_speed_passenger_kmh
            if is_passenger
            else self.max_speed_freight_kmh
        )

        # Apply caution order
        if self.caution_order_kmh is not None:
            effective_speed = min(max_speed, self.caution_order_kmh)
            base = (self.length_km / effective_speed) * 60

        # Apply weather factor
        base = base / max(self.weather_speed_factor, 0.01)

        # Apply congestion factor (convex: heavy congestion adds up to 3× time)
        congestion_factor = 1.0 + 2.0 * (self.congestion_score ** 2)

        # Signal failure adds caution penalty
        if self.signal_failed:
            congestion_factor *= 1.5

        return base * congestion_factor

    # ── Occupancy ─────────────────────────────────────────────────────────────

    def train_enters(self, train_id: str, sim_time: float) -> None:
        self.trains_on_section.add(train_id)
        self.last_entry_time = sim_time
        self.total_trains_passed += 1
        self._update_congestion()
        logger.debug(
            "Section %s: train %s entered (t=%.1f, occupancy=%d)",
            self.section_id, train_id, sim_time, len(self.trains_on_section),
        )

    def train_exits(self, train_id: str) -> None:
        self.trains_on_section.discard(train_id)
        self._update_congestion()

    def headway_satisfied(self, sim_time: float) -> bool:
        """True if the section can accept another train right now."""
        if self.condition == SectionCondition.BLOCKED:
            return False
        if self.last_entry_time is None:
            return True
        return (sim_time - self.last_entry_time) >= self.min_headway_minutes

    def time_until_headway_clear(self, sim_time: float) -> float:
        """Minutes until the headway timer expires (0 if already clear)."""
        if self.last_entry_time is None:
            return 0.0
        elapsed = sim_time - self.last_entry_time
        return max(0.0, self.min_headway_minutes - elapsed)

    def _update_congestion(self) -> None:
        capacity = self.theoretical_capacity_per_hour * (self.min_headway_minutes / 60)
        n = len(self.trains_on_section)
        self.congestion_score = min(1.0, n / max(capacity, 1.0))
        if self.congestion_score >= 0.85:
            self.condition = SectionCondition.CONGESTED
        elif self.condition == SectionCondition.CONGESTED:
            self.condition = SectionCondition.CLEAR

    # ── Disruption management ─────────────────────────────────────────────────

    def apply_signal_failure(self, restore_time: float) -> None:
        self.signal_failed = True
        self.signal_restore_time = restore_time
        self.condition = SectionCondition.SIGNAL_FAIL
        logger.info("Section %s: signal FAILED (restore=%.1f)", self.section_id, restore_time)

    def restore_signal(self) -> None:
        self.signal_failed = False
        self.signal_restore_time = None
        self.condition = SectionCondition.CLEAR
        logger.info("Section %s: signal RESTORED", self.section_id)

    def apply_blockage(self) -> None:
        self.condition = SectionCondition.BLOCKED
        logger.info("Section %s: BLOCKED", self.section_id)

    def clear_blockage(self) -> None:
        self.condition = SectionCondition.CLEAR
        self.congestion_score = 0.0
        logger.info("Section %s: blockage CLEARED", self.section_id)

    def apply_weather(self, speed_factor: float) -> None:
        self.weather_speed_factor = max(0.01, min(1.0, speed_factor))

    def set_caution_order(self, speed_kmh: float) -> None:
        self.caution_order_kmh = speed_kmh

    def clear_caution_order(self) -> None:
        self.caution_order_kmh = None

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "section_id":          self.section_id,
            "from_station":        self.from_station,
            "to_station":          self.to_station,
            "condition":           self.condition.name,
            "trains_on_section":   list(self.trains_on_section),
            "congestion_score":    round(self.congestion_score, 3),
            "weather_speed_factor":self.weather_speed_factor,
            "caution_order_kmh":   self.caution_order_kmh,
            "signal_failed":       self.signal_failed,
            "effective_travel_min":round(self.effective_travel_min(), 2),
            "total_trains_passed": self.total_trains_passed,
        }

    def __repr__(self) -> str:
        return (
            f"SectionState({self.section_id} "
            f"[{self.condition.name}] "
            f"trains={len(self.trains_on_section)} "
            f"cong={self.congestion_score:.2f})"
        )
