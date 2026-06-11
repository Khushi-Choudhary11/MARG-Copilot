"""
High-level query interface for the MARG Railway Graph Engine.

Wraps CorridorGraph + RailwayAlgorithms behind a single, clean API
that the simulation engine, optimization engine, and FastAPI routes call.

All methods are pure reads (no state mutation) except ``apply_snapshot``,
which updates runtime edge attributes from a simulation snapshot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..models.enums import Direction, SectionStatus
from ..models.loop_line import LoopLine
from ..models.section import TrackSection
from ..models.station import Station
from .algorithms import (
    Bottleneck,
    CascadeResult,
    CrossingPlan,
    PathResult,
    RailwayAlgorithms,
)
from .corridor_graph import CorridorGraph

logger = logging.getLogger(__name__)


@dataclass
class CorridorSummary:
    """Top-level summary of corridor state — sent to the frontend every tick."""
    num_stations: int
    num_sections: int
    num_single_line_sections: int
    num_junctions: int
    num_crew_change_points: int
    total_length_km: float
    saturation_index: float
    critical_bottlenecks: int
    warning_bottlenecks: int


class GraphQueries:
    """
    Read-oriented query facade over the railway graph.

    Instantiate once and share across the application lifetime.

    >>> gq = GraphQueries.build()
    >>> gq.summary()
    >>> gq.path("NDLS", "CNB")
    >>> gq.crossing_plan("12301", "ALJN", 640, 0, 5, "70501", "TDL", 720, 4, 45)
    """

    def __init__(self, graph: CorridorGraph) -> None:
        self._cg   = graph
        self._algo = RailwayAlgorithms(graph)

    @classmethod
    def build(cls) -> "GraphQueries":
        """Build with default NDLS–CNB corridor data."""
        return cls(CorridorGraph.build())

    # ── Corridor structure queries ────────────────────────────────────────────

    def summary(
        self,
        train_counts_by_section: Optional[dict[str, int]] = None,
    ) -> CorridorSummary:
        """Return a top-level corridor summary."""
        bottlenecks = (
            self._algo.detect_bottlenecks(train_counts_by_section or {})
            if train_counts_by_section
            else []
        )
        sat = (
            self._algo.corridor_saturation(train_counts_by_section or {})
        )
        total_km = sum(
            s.length_km for s in self._cg._sections.values()
            if s.direction.value == "up"
        )
        return CorridorSummary(
            num_stations=self._cg.num_stations,
            num_sections=self._cg.num_sections,
            num_single_line_sections=len(self._cg.single_line_sections()),
            num_junctions=len(self._cg.junction_stations()),
            num_crew_change_points=len(self._cg.crew_change_stations()),
            total_length_km=round(total_km, 1),
            saturation_index=sat,
            critical_bottlenecks=sum(
                1 for b in bottlenecks if b.severity == "critical"
            ),
            warning_bottlenecks=sum(
                1 for b in bottlenecks if b.severity == "warning"
            ),
        )

    def station(self, station_id: str) -> Station:
        return self._cg.station(station_id)

    def section(self, section_id: str) -> TrackSection:
        return self._cg.section(section_id)

    def all_stations(self) -> list[Station]:
        return self._cg.stations_ordered_up()

    def all_sections(self) -> list[TrackSection]:
        return list(self._cg._sections.values())

    def single_line_sections(self) -> list[TrackSection]:
        return self._cg.single_line_sections()

    def junction_stations(self) -> list[Station]:
        return self._cg.junction_stations()

    def crew_change_stations(self) -> list[Station]:
        return self._cg.crew_change_stations()

    def stations_near(
        self,
        reference: str,
        radius_km: float,
        direction: Optional[Direction] = None,
    ) -> list[Station]:
        return self._algo.stations_in_range(reference, radius_km, direction)

    def distance_km(self, station_a: str, station_b: str) -> float:
        return self._algo.chainage_distance_km(station_a, station_b)

    # ── Path queries ──────────────────────────────────────────────────────────

    def path(
        self,
        source: str,
        target: str,
        is_passenger: bool = True,
    ) -> PathResult:
        """Shortest congestion-aware path from source to target."""
        return self._algo.shortest_path(source, target, is_passenger)

    def reroute(
        self,
        source: str,
        target: str,
        blocked_section_id: str,
        is_passenger: bool = True,
    ) -> PathResult:
        """Alternative path avoiding a blocked section."""
        return self._algo.reroute_avoiding(
            source, target, blocked_section_id, is_passenger
        )

    # ── Crossing queries ──────────────────────────────────────────────────────

    def crossing_plan(
        self,
        train_a_id: str,
        train_a_station: str,
        train_a_length_m: float,
        train_a_priority: int,
        train_a_delay_min: float,
        train_b_id: str,
        train_b_station: str,
        train_b_length_m: float,
        train_b_priority: int,
        train_b_delay_min: float,
        search_radius_km: float = 80.0,
    ) -> CrossingPlan:
        """Optimal crossing plan for two opposing trains."""
        return self._algo.find_crossing_stations(
            train_a_id=train_a_id,
            train_a_pos_station=train_a_station,
            train_a_length_m=train_a_length_m,
            train_a_priority=train_a_priority,
            train_a_delay_min=train_a_delay_min,
            train_b_id=train_b_id,
            train_b_pos_station=train_b_station,
            train_b_length_m=train_b_length_m,
            train_b_priority=train_b_priority,
            train_b_delay_min=train_b_delay_min,
            search_radius_km=search_radius_km,
        )

    def can_cross_at(
        self,
        station_id: str,
        train_a_length_m: float,
        train_b_length_m: float,
    ) -> bool:
        """Quick check: can two trains cross at a given station?"""
        st = self._cg.station(station_id)
        return st.can_cross_trains(train_a_length_m, train_b_length_m)

    # ── Bottleneck and cascade queries ────────────────────────────────────────

    def bottlenecks(
        self,
        train_counts_by_section: dict[str, int],
        window_hours: float = 1.0,
    ) -> list[Bottleneck]:
        """Detect capacity-constrained sections."""
        return self._algo.detect_bottlenecks(
            train_counts_by_section, window_hours
        )

    def cascade(
        self,
        root_train_id: str,
        root_delay_minutes: float,
        dependency_edges: list[tuple[str, str, float, str]],
    ) -> CascadeResult:
        """Trace the cascade from a delayed root train."""
        return self._algo.trace_cascade(
            root_train_id, root_delay_minutes, dependency_edges
        )

    def corridor_saturation(
        self,
        train_counts_by_section: dict[str, int],
    ) -> float:
        """Single [0, 1] corridor saturation index."""
        return self._algo.corridor_saturation(train_counts_by_section)

    # ── Runtime state updates (called by SimulationEngine) ───────────────────

    def apply_snapshot(
        self,
        congestion_scores: dict[str, float],
        weather_factors: dict[str, float],
        blocked_sections: list[str],
        caution_orders: dict[str, float],
    ) -> None:
        """
        Apply a simulation snapshot to the graph's runtime edge attributes.
        Called once per simulation tick before any queries are made.

        Parameters
        ----------
        congestion_scores:
            section_id → float in [0, 1].
        weather_factors:
            section_id → speed factor in (0, 1].
        blocked_sections:
            List of section IDs currently blocked.
        caution_orders:
            section_id → maximum speed in km/h.
        """
        self._cg.bulk_update_congestion(congestion_scores)
        self._cg.bulk_update_weather(weather_factors)

        for section_id in blocked_sections:
            if section_id in self._cg.section_ids:
                self._cg.update_status(section_id, SectionStatus.BLOCKED)

        for section_id, speed in caution_orders.items():
            if section_id in self._cg.section_ids:
                self._cg.set_caution_order(section_id, speed)

    # ── GeoJSON exports ───────────────────────────────────────────────────────

    def geojson_nodes(self) -> dict:
        """GeoJSON FeatureCollection of all stations."""
        return self._cg.to_geojson_nodes()

    def geojson_edges(self) -> dict:
        """GeoJSON FeatureCollection of all track sections."""
        return self._cg.to_geojson_edges()

    def state_snapshot(self) -> dict:
        """Lightweight runtime state dict for Redis publishing."""
        return self._cg.current_state_snapshot()
