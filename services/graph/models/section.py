"""
TrackSection model — graph edge.

A track section is the directed edge between two adjacent stations.
It encodes all static infrastructure properties that govern train movement:
speed limits, capacity, gradient, electrification, and signal block count.

Real-time state (occupation, speed restrictions, blockages) is tracked
in the simulation layer and stored as edge attributes that are updated
each simulation tick.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .enums import (
    Direction,
    ElectrificationType,
    LineType,
    SectionStatus,
)


@dataclass(frozen=True)
class SignalBlock:
    """
    A single absolute-block signalling section within a track section.

    On Indian Railways, each signal block is bounded by a home signal
    at its entry and a starter signal at its exit. Only one train may
    occupy a block at a time (Absolute Block System).

    Attributes
    ----------
    block_id:
        Unique identifier, e.g. ``"ALJN_TDL_B1"``.
    length_km:
        Physical length of this block.
    min_headway_seconds:
        Minimum time gap required between two consecutive trains
        entering this block. Typically 180–420 s on IR main lines.
    """
    block_id: str
    length_km: float
    min_headway_seconds: int = 300  # 5 minutes default


@dataclass(frozen=True)
class TrackSection:
    """
    A directed track section — directed edge in the corridor graph.

    Direction convention: UP = towards Kanpur (increasing chainage).
    For double-line sections, two TrackSection objects exist between
    the same station pair — one UP, one DOWN.
    For single-line sections, a single object with ``line_type=SINGLE``
    represents the shared track; crossing logic uses ``loop_lines``
    on each adjacent station.

    Attributes
    ----------
    section_id:
        Unique identifier, e.g. ``"ALJN_TDL_UP"``.
    from_station_id:
        Origin station code.
    to_station_id:
        Destination station code.
    direction:
        UP or DOWN. BOTH is not used for sections (only infrastructure).
    length_km:
        Track length in kilometres (may differ from chainage difference
        due to curves).
    line_type:
        SINGLE or DOUBLE.
    max_speed_passenger_kmh:
        Maximum permitted speed for passenger trains (km/h).
    max_speed_freight_kmh:
        Maximum permitted speed for freight trains (km/h).
        Always <= max_speed_passenger_kmh.
    ruling_gradient_pct:
        Steepest gradient on the section as a percentage.
        Positive = rising (towards destination), negative = falling.
        Values > 0.5% affect goods train speed noticeably.
    electrification:
        Traction supply type. Determines which loco types can operate.
    signal_blocks:
        Ordered tuple of SignalBlock objects from origin to destination.
    theoretical_capacity_trains_per_hour:
        Calculated maximum throughput under ideal conditions.
        Derived from minimum headway of signal blocks.
    notes:
        Engineering or operational remarks.
    """

    section_id:             str
    from_station_id:        str
    to_station_id:          str
    direction:              Direction
    length_km:              float
    line_type:              LineType
    max_speed_passenger_kmh: float
    max_speed_freight_kmh:  float
    ruling_gradient_pct:    float               = 0.0
    electrification:        ElectrificationType = ElectrificationType.AC_25KV
    signal_blocks:          tuple[SignalBlock, ...] = field(default_factory=tuple)
    notes:                  str                 = ""

    # ── Derived properties ───────────────────────────────────────────────────

    @property
    def num_signal_blocks(self) -> int:
        return len(self.signal_blocks)

    @property
    def theoretical_capacity_trains_per_hour(self) -> float:
        """
        Maximum trains per hour under clear-signal conditions.

        Derived from the tightest block headway on the section.
        Formula: 3600 / max(headway_seconds across all blocks).
        """
        if not self.signal_blocks:
            # Fallback: assume one block, 10-minute headway
            return 3600 / 600
        tightest = max(b.min_headway_seconds for b in self.signal_blocks)
        return 3600 / tightest

    @property
    def min_transit_time_passenger_minutes(self) -> float:
        """
        Minimum end-to-end transit time for a passenger train at line speed.
        Does not include station halt time at either end.
        """
        return (self.length_km / self.max_speed_passenger_kmh) * 60

    @property
    def min_transit_time_freight_minutes(self) -> float:
        """Minimum end-to-end transit time for a freight train at line speed."""
        return (self.length_km / self.max_speed_freight_kmh) * 60

    @property
    def has_adverse_gradient(self) -> bool:
        """
        True if the ruling gradient is steep enough to materially
        affect freight train performance (> 0.5%).
        """
        return abs(self.ruling_gradient_pct) > 0.5

    @property
    def is_single_line(self) -> bool:
        return self.line_type == LineType.SINGLE

    @property
    def is_double_line(self) -> bool:
        return self.line_type == LineType.DOUBLE

    # ── Speed computation ────────────────────────────────────────────────────

    def effective_speed_kmh(
        self,
        is_passenger: bool,
        weather_speed_factor: float = 1.0,
        caution_order_kmh: Optional[float] = None,
    ) -> float:
        """
        Compute effective speed limit after applying weather and
        any engineering caution order.

        Parameters
        ----------
        is_passenger:
            True for passenger trains, False for freight.
        weather_speed_factor:
            Multiplier from WeatherEngine (0.15 for dense fog → 1.0 clear).
        caution_order_kmh:
            Engineering caution order speed, if active. None = no restriction.
        """
        base = (
            self.max_speed_passenger_kmh
            if is_passenger
            else self.max_speed_freight_kmh
        )
        weather_limited = base * weather_speed_factor

        if caution_order_kmh is not None:
            return min(weather_limited, caution_order_kmh)
        return weather_limited

    def transit_time_minutes(
        self,
        is_passenger: bool,
        weather_speed_factor: float = 1.0,
        caution_order_kmh: Optional[float] = None,
        gradient_penalty_factor: float = 1.0,
    ) -> float:
        """
        Estimated transit time in minutes for a train on this section,
        accounting for weather, caution orders, and gradient penalties.

        Parameters
        ----------
        gradient_penalty_factor:
            Multiplier for gradient-induced slowdown. Typically 1.0–1.3
            for freight on steep adverse gradients.
        """
        speed = self.effective_speed_kmh(
            is_passenger, weather_speed_factor, caution_order_kmh
        )
        if speed <= 0:
            return float("inf")
        base_time = (self.length_km / speed) * 60
        return base_time * gradient_penalty_factor

    # ── Graph serialisation ──────────────────────────────────────────────────

    def to_edge_attrs(self) -> dict:
        """
        Serialise to NetworkX edge attribute dict.
        The full TrackSection object is stored under ``"section"`` key;
        scalar values are duplicated at the top level for fast NetworkX
        attribute lookups (e.g. ``nx.shortest_path weight="travel_min"``).
        """
        return {
            "section":                          self,
            "section_id":                       self.section_id,
            "direction":                        self.direction.value,
            "length_km":                        self.length_km,
            "line_type":                        self.line_type.value,
            "max_speed_passenger_kmh":          self.max_speed_passenger_kmh,
            "max_speed_freight_kmh":            self.max_speed_freight_kmh,
            "ruling_gradient_pct":              self.ruling_gradient_pct,
            "electrification":                  self.electrification.value,
            "num_signal_blocks":                self.num_signal_blocks,
            "capacity_trains_per_hour":         self.theoretical_capacity_trains_per_hour,
            # Runtime-mutable — defaults; updated by simulation
            "travel_min":                       self.min_transit_time_passenger_minutes,
            "freight_travel_min":               self.min_transit_time_freight_minutes,
            "status":                           SectionStatus.CLEAR.value,
            "congestion_score":                 0.0,
            "weather_speed_factor":             1.0,
            "caution_order_kmh":                None,
            "active_caution_order":             False,
        }

    def __repr__(self) -> str:
        return (
            f"TrackSection({self.section_id!r}, "
            f"{self.from_station_id}→{self.to_station_id}, "
            f"{self.length_km:.1f}km, "
            f"{self.line_type.value}, "
            f"pax={self.max_speed_passenger_kmh:.0f}kmh)"
        )
