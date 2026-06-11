"""
Station model — graph node.

A station is the fundamental node in the corridor graph. It encapsulates
both static infrastructure data and derived operational properties.
Real-time mutable state (platform/loop occupation) lives in the
simulation layer, not in this immutable model.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .enums import Direction, ElectrificationType, StationClass
from .loop_line import LoopLine


# ── Minimum halt times (seconds) by station class ─────────────────────────────
# Sourced from IR Working Timetable conventions.
_MIN_HALT_PASSENGER: dict[StationClass, int] = {
    StationClass.A1: 120,
    StationClass.A:   60,
    StationClass.B:   30,
    StationClass.C:   20,
    StationClass.D:   10,
    StationClass.E:    0,
    StationClass.F:    0,
}

_MIN_HALT_GOODS: dict[StationClass, int] = {
    StationClass.A1: 300,
    StationClass.A:  240,
    StationClass.B:  180,
    StationClass.C:  120,
    StationClass.D:   60,
    StationClass.E:   30,
    StationClass.F:    0,
}


@dataclass(frozen=True)
class Platform:
    """A single platform track at a station."""
    platform_id: str
    platform_number: int
    length_meters: float
    electrified: bool = True


@dataclass(frozen=True)
class Station:
    """
    A railway station — graph node on the NDLS–CNB corridor.

    Immutable value object. All distance measurements are in kilometres
    from New Delhi (NDLS = 0.0 km).

    Attributes
    ----------
    station_id:
        Short IR station code, e.g. ``"ALJN"``, ``"TDL"``.
    name:
        Full station name.
    chainage_km:
        Distance from NDLS in kilometres (reference datum).
    station_class:
        IR classification (A1 down to F).
    latitude, longitude:
        WGS-84 coordinates for map rendering.
    platforms:
        Ordered tuple of Platform objects.
    loop_lines:
        Tuple of LoopLine objects. Length and electrification drive
        crossing feasibility in the optimizer.
    main_lines:
        Number of through-running tracks (does not include loops).
    is_junction:
        True if the station branches to another main line.
    is_crew_change_point:
        True if a loco-pilot crew change depot is available.
    is_loco_change_point:
        True if loco change/attachment facilities exist.
    is_terminus:
        True for NDLS and CNB (end-of-line stations).
    electrification:
        Traction supply at the station.
    elevation_m:
        Station elevation in metres above mean sea level.
        Used to compute gradient-induced speed restrictions.
    notes:
        Operational remarks visible to the controller.
    """

    station_id: str
    name: str
    chainage_km: float
    station_class: StationClass
    latitude: float
    longitude: float

    platforms: tuple[Platform, ...]         = field(default_factory=tuple)
    loop_lines: tuple[LoopLine, ...]        = field(default_factory=tuple)
    main_lines: int                         = 2
    is_junction: bool                       = False
    is_crew_change_point: bool              = False
    is_loco_change_point: bool              = False
    is_terminus: bool                       = False
    electrification: ElectrificationType   = ElectrificationType.AC_25KV
    elevation_m: float                      = 200.0
    notes: str                              = ""

    # ── Derived properties ───────────────────────────────────────────────────

    @property
    def num_platforms(self) -> int:
        return len(self.platforms)

    @property
    def num_loop_lines(self) -> int:
        return len(self.loop_lines)

    @property
    def max_loop_length_m(self) -> float:
        """Length of the longest loop at this station. 0 if no loops."""
        if not self.loop_lines:
            return 0.0
        return max(lp.length_meters for lp in self.loop_lines)

    @property
    def available_loops_for_crossing(self) -> tuple[LoopLine, ...]:
        """Loops whose type is CROSSING or OVERTAKING."""
        from .enums import LoopLineType
        return tuple(
            lp for lp in self.loop_lines
            if lp.loop_type in (LoopLineType.CROSSING, LoopLineType.OVERTAKING)
        )

    @property
    def min_halt_passenger_seconds(self) -> int:
        return _MIN_HALT_PASSENGER[self.station_class]

    @property
    def min_halt_goods_seconds(self) -> int:
        return _MIN_HALT_GOODS[self.station_class]

    def can_cross_trains(
        self,
        train_a_length_m: float,
        train_b_length_m: float,
        requires_electrification: bool = True,
    ) -> bool:
        """
        Return True if this station can host a crossing of two trains —
        i.e. at least one loop can accommodate the *longer* of the two trains.

        The longer train typically waits in the loop while the shorter
        (or higher-priority) train uses the main line.
        """
        longer = max(train_a_length_m, train_b_length_m)
        return any(
            lp.can_accommodate(longer, requires_electrification)
            for lp in self.available_loops_for_crossing
        )

    def best_loop_for(
        self,
        train_length_m: float,
        requires_electrification: bool = True,
    ) -> Optional[LoopLine]:
        """
        Return the shortest adequate loop for a given train length,
        or None if no suitable loop exists.

        Choosing the *shortest* adequate loop leaves longer loops
        available for goods trains — a real IR operational heuristic.
        """
        candidates = [
            lp for lp in self.available_loops_for_crossing
            if lp.can_accommodate(train_length_m, requires_electrification)
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda lp: lp.length_meters)

    def to_node_attrs(self) -> dict:
        """
        Serialise to NetworkX node attribute dict.
        Excludes nested objects to keep the graph lightweight;
        the full Station object is stored under ``"station"`` key.
        """
        return {
            "station":              self,          # full object reference
            "name":                 self.name,
            "chainage_km":          self.chainage_km,
            "station_class":        self.station_class.value,
            "latitude":             self.latitude,
            "longitude":            self.longitude,
            "num_platforms":        self.num_platforms,
            "num_loops":            self.num_loop_lines,
            "max_loop_length_m":    self.max_loop_length_m,
            "is_junction":          self.is_junction,
            "is_crew_change":       self.is_crew_change_point,
            "is_loco_change":       self.is_loco_change_point,
            "is_terminus":          self.is_terminus,
            "elevation_m":          self.elevation_m,
        }

    def __repr__(self) -> str:
        return (
            f"Station({self.station_id!r}, "
            f"{self.name!r}, "
            f"chainage={self.chainage_km:.1f}km, "
            f"class={self.station_class.name})"
        )
