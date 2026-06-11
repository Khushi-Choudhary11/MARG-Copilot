"""
CorridorGraph — the central NetworkX graph of the NDLS–CNB corridor.

Design
------
* Underlying structure: ``networkx.DiGraph``
  - Nodes  → stations (station_id strings)
  - Edges  → directed track sections (from_station → to_station)
  - For DOUBLE-line sections, two directed edges are added (UP and DOWN).
  - For SINGLE-line sections, two directed edges with ``line_type=SINGLE``
    are added; crossing constraints are enforced by the optimizer, not here.

* Node and edge attributes are initialised from static infrastructure data
  and updated at runtime by the simulation layer via ``update_*`` methods.

* The graph is a **singleton per corridor** — construct once, update in place.

Thread safety: ``update_*`` methods mutate edge attributes. If the graph is
shared across threads (e.g. FastAPI + background worker), callers must
synchronise externally.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator, Optional, Sequence

import networkx as nx

from ..models.enums import Direction, LineType, SectionStatus
from ..models.loop_line import LoopLine
from ..models.section import TrackSection
from ..models.station import Station
from ..data.ndls_cnb import (
    SECTIONS,
    STATIONS,
    STATION_INDEX,
    SECTION_INDEX,
    STATION_ORDER_UP,
)

logger = logging.getLogger(__name__)


class GraphError(Exception):
    """Raised when the graph is queried in an invalid way."""


class CorridorGraph:
    """
    NetworkX DiGraph wrapper for the NDLS–CNB railway corridor.

    Responsibilities
    ----------------
    * Build and hold the static graph topology.
    * Expose typed accessors for nodes (stations) and edges (sections).
    * Accept runtime updates from the simulation engine
      (congestion scores, speed factors, blockages).
    * Provide a weight function used by shortest-path algorithms.

    Usage
    -----
    >>> graph = CorridorGraph.build()
    >>> graph.station("ALJN").name
    'Aligarh Junction'
    >>> graph.section("ALJN_TDL_UP").length_km
    52.0
    >>> graph.update_congestion("ALJN_TDL_UP", 0.85)
    """

    def __init__(self) -> None:
        self._g: nx.DiGraph = nx.DiGraph()
        self._stations: dict[str, Station]      = {}
        self._sections: dict[str, TrackSection] = {}

    # ── Construction ─────────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        stations: Sequence[Station]      = STATIONS,
        sections: Sequence[TrackSection] = SECTIONS,
    ) -> "CorridorGraph":
        """
        Factory method — constructs a CorridorGraph from the given
        station and section sequences.

        Parameters
        ----------
        stations:
            Ordered collection of Station objects (default: NDLS–CNB data).
        sections:
            Collection of TrackSection objects (default: NDLS–CNB data).

        Returns
        -------
        CorridorGraph
            Fully initialised graph ready for queries.
        """
        cg = cls()
        cg._add_stations(stations)
        cg._add_sections(sections)
        logger.info(
            "CorridorGraph built: %d stations, %d sections (%d nodes, %d edges)",
            len(cg._stations),
            len(cg._sections),
            cg._g.number_of_nodes(),
            cg._g.number_of_edges(),
        )
        return cg

    def _add_stations(self, stations: Sequence[Station]) -> None:
        for st in stations:
            self._stations[st.station_id] = st
            self._g.add_node(st.station_id, **st.to_node_attrs())

    def _add_sections(self, sections: Sequence[TrackSection]) -> None:
        for sec in sections:
            if sec.from_station_id not in self._g:
                raise GraphError(
                    f"Section '{sec.section_id}' references unknown station "
                    f"'{sec.from_station_id}'"
                )
            if sec.to_station_id not in self._g:
                raise GraphError(
                    f"Section '{sec.section_id}' references unknown station "
                    f"'{sec.to_station_id}'"
                )
            self._sections[sec.section_id] = sec
            self._g.add_edge(
                sec.from_station_id,
                sec.to_station_id,
                **sec.to_edge_attrs(),
            )

    # ── Static accessors ─────────────────────────────────────────────────────

    @property
    def graph(self) -> nx.DiGraph:
        """Direct access to the underlying NetworkX DiGraph (read-only intent)."""
        return self._g

    @property
    def station_ids(self) -> list[str]:
        return list(self._stations.keys())

    @property
    def section_ids(self) -> list[str]:
        return list(self._sections.keys())

    @property
    def num_stations(self) -> int:
        return self._g.number_of_nodes()

    @property
    def num_sections(self) -> int:
        return self._g.number_of_edges()

    def station(self, station_id: str) -> Station:
        """Return the Station object for a given ID."""
        if station_id not in self._stations:
            raise GraphError(f"Unknown station: '{station_id}'")
        return self._stations[station_id]

    def section(self, section_id: str) -> TrackSection:
        """Return the TrackSection object for a given ID."""
        if section_id not in self._sections:
            raise GraphError(f"Unknown section: '{section_id}'")
        return self._sections[section_id]

    def edge_attrs(self, from_s: str, to_s: str) -> dict:
        """Return mutable edge attribute dict for a (from, to) pair."""
        if not self._g.has_edge(from_s, to_s):
            raise GraphError(f"No edge from '{from_s}' to '{to_s}'")
        return self._g[from_s][to_s]

    def section_attrs(self, section_id: str) -> dict:
        """Return mutable edge attribute dict looked up by section_id."""
        sec = self.section(section_id)
        return self.edge_attrs(sec.from_station_id, sec.to_station_id)

    def sections_between(
        self, from_s: str, to_s: str
    ) -> list[TrackSection]:
        """
        Return all TrackSection objects on direct edges between two stations.
        Typically returns 0–2 sections (UP and DOWN for double line,
        or 1 for single line if only one direction modelled).
        """
        if not self._g.has_edge(from_s, to_s):
            return []
        attrs = self._g[from_s][to_s]
        return [attrs["section"]]

    def outgoing_sections(self, station_id: str) -> list[TrackSection]:
        """All sections departing from a station."""
        return [
            self._g[station_id][nbr]["section"]
            for nbr in self._g.successors(station_id)
        ]

    def incoming_sections(self, station_id: str) -> list[TrackSection]:
        """All sections arriving at a station."""
        return [
            self._g[pred][station_id]["section"]
            for pred in self._g.predecessors(station_id)
        ]

    def single_line_sections(self) -> list[TrackSection]:
        """All sections where line_type is SINGLE."""
        return [
            s for s in self._sections.values()
            if s.is_single_line
        ]

    def double_line_sections(self) -> list[TrackSection]:
        """All sections where line_type is DOUBLE."""
        return [
            s for s in self._sections.values()
            if s.is_double_line
        ]

    def junction_stations(self) -> list[Station]:
        return [s for s in self._stations.values() if s.is_junction]

    def crew_change_stations(self) -> list[Station]:
        return [s for s in self._stations.values() if s.is_crew_change_point]

    def stations_ordered_up(self) -> list[Station]:
        """Stations in increasing chainage order (NDLS → CNB)."""
        return sorted(self._stations.values(), key=lambda s: s.chainage_km)

    # ── Runtime state updates (called by simulation engine each tick) ────────

    def update_congestion(self, section_id: str, score: float) -> None:
        """
        Update congestion score for a section.

        The score drives the ``travel_min`` edge weight used by shortest-path
        algorithms: heavier congestion → longer effective travel time.

        Parameters
        ----------
        section_id:
            Section identifier, e.g. ``"ALJN_TDL_UP"``.
        score:
            Float in [0.0, 1.0]. 0 = clear, 1 = saturated.
        """
        if not (0.0 <= score <= 1.0):
            raise ValueError(f"Congestion score must be in [0, 1]; got {score}")
        attrs = self.section_attrs(section_id)
        attrs["congestion_score"] = score
        # Recompute travel_min: congestion adds up to 3× normal travel time
        sec: TrackSection = attrs["section"]
        congestion_factor = 1.0 + 2.0 * (score ** 2)
        weather_factor    = attrs.get("weather_speed_factor", 1.0)
        attrs["travel_min"] = sec.min_transit_time_passenger_minutes * congestion_factor / max(weather_factor, 0.01)

    def update_weather(self, section_id: str, speed_factor: float) -> None:
        """
        Apply a weather-derived speed factor to a section.

        Parameters
        ----------
        speed_factor:
            Multiplier in (0, 1]. 1.0 = clear, 0.15 = dense fog (15 km/h cap).
        """
        if not (0.0 < speed_factor <= 1.0):
            raise ValueError(f"Speed factor must be in (0, 1]; got {speed_factor}")
        attrs = self.section_attrs(section_id)
        attrs["weather_speed_factor"] = speed_factor
        sec: TrackSection = attrs["section"]
        congestion_factor = 1.0 + 2.0 * (attrs.get("congestion_score", 0.0) ** 2)
        attrs["travel_min"] = sec.min_transit_time_passenger_minutes * congestion_factor / speed_factor

    def update_status(self, section_id: str, status: SectionStatus) -> None:
        """Update the operational status of a section."""
        attrs = self.section_attrs(section_id)
        attrs["status"] = status.value
        if status == SectionStatus.BLOCKED:
            # Effectively infinite travel time — path algorithms will avoid it
            attrs["travel_min"] = 1e9
        elif status == SectionStatus.CLEAR:
            # Recompute from current congestion/weather
            self.update_congestion(section_id, attrs.get("congestion_score", 0.0))

    def set_caution_order(
        self, section_id: str, speed_kmh: float
    ) -> None:
        """
        Apply an engineering caution order (speed restriction) to a section.

        Parameters
        ----------
        speed_kmh:
            Maximum permitted speed under the caution order.
        """
        attrs = self.section_attrs(section_id)
        sec: TrackSection = attrs["section"]
        attrs["caution_order_kmh"]    = speed_kmh
        attrs["active_caution_order"] = True
        # Update travel_min
        restricted_speed = min(sec.max_speed_passenger_kmh, speed_kmh)
        if restricted_speed <= 0:
            attrs["travel_min"] = 1e9
        else:
            attrs["travel_min"] = (sec.length_km / restricted_speed) * 60

    def clear_caution_order(self, section_id: str) -> None:
        """Remove an active caution order from a section."""
        attrs = self.section_attrs(section_id)
        attrs["caution_order_kmh"]    = None
        attrs["active_caution_order"] = False
        self.update_congestion(section_id, attrs.get("congestion_score", 0.0))

    def bulk_update_congestion(
        self, scores: dict[str, float]
    ) -> None:
        """
        Update congestion scores for multiple sections at once.
        Called each simulation tick with the full snapshot.

        Parameters
        ----------
        scores:
            Mapping of section_id → congestion score.
        """
        for section_id, score in scores.items():
            if section_id in self._sections:
                self.update_congestion(section_id, score)

    def bulk_update_weather(
        self, factors: dict[str, float]
    ) -> None:
        """
        Update weather speed factors for multiple sections at once.

        Parameters
        ----------
        factors:
            Mapping of section_id → speed factor (0, 1].
        """
        for section_id, factor in factors.items():
            if section_id in self._sections:
                self.update_weather(section_id, factor)

    # ── Weight function ───────────────────────────────────────────────────────

    def travel_time_weight(
        self, u: str, v: str, attrs: dict
    ) -> float:
        """
        Edge weight function for use with ``nx.shortest_path``.
        Returns the current effective travel time in minutes.
        Blocked sections return a very large value to exclude them from paths.

        Compatible with the ``weight`` callable parameter in NetworkX ≥ 2.6.
        """
        return attrs.get("travel_min", 1e9)

    def freight_travel_time_weight(
        self, u: str, v: str, attrs: dict
    ) -> float:
        """Edge weight function for freight trains (lower speed limits)."""
        return attrs.get("freight_travel_min", attrs.get("travel_min", 1e9))

    # ── Snapshot / export ─────────────────────────────────────────────────────

    def to_geojson_nodes(self) -> dict:
        """Export stations as a GeoJSON FeatureCollection for Leaflet."""
        features = []
        for st in self._stations.values():
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [st.longitude, st.latitude],
                },
                "properties": {
                    "station_id":   st.station_id,
                    "name":         st.name,
                    "chainage_km":  st.chainage_km,
                    "class":        st.station_class.name,
                    "is_junction":  st.is_junction,
                    "num_loops":    st.num_loop_lines,
                    "max_loop_m":   st.max_loop_length_m,
                },
            })
        return {"type": "FeatureCollection", "features": features}

    def to_geojson_edges(self) -> dict:
        """
        Export track sections as a GeoJSON FeatureCollection.
        Line geometry is approximated as a straight line between station
        coordinates; replace with real track geometry for production.
        """
        features = []
        seen: set[frozenset] = set()

        for sec in self._sections.values():
            pair = frozenset({sec.from_station_id, sec.to_station_id})
            if pair in seen:
                continue  # only export one geometry per station pair
            seen.add(pair)

            st_from = self._stations[sec.from_station_id]
            st_to   = self._stations[sec.to_station_id]
            attrs   = self.edge_attrs(sec.from_station_id, sec.to_station_id)

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [st_from.longitude, st_from.latitude],
                        [st_to.longitude,   st_to.latitude],
                    ],
                },
                "properties": {
                    "section_id":         sec.section_id,
                    "from":               sec.from_station_id,
                    "to":                 sec.to_station_id,
                    "length_km":          sec.length_km,
                    "line_type":          sec.line_type.value,
                    "max_speed_pax":      sec.max_speed_passenger_kmh,
                    "max_speed_frt":      sec.max_speed_freight_kmh,
                    "congestion_score":   attrs.get("congestion_score", 0.0),
                    "status":             attrs.get("status", SectionStatus.CLEAR.value),
                },
            })
        return {"type": "FeatureCollection", "features": features}

    def current_state_snapshot(self) -> dict:
        """
        Return a lightweight snapshot of all runtime edge attributes.
        Used by the simulation engine to publish state to Redis.
        """
        return {
            section_id: {
                "congestion_score":    self._g[sec.from_station_id][sec.to_station_id].get("congestion_score", 0.0),
                "travel_min":          self._g[sec.from_station_id][sec.to_station_id].get("travel_min", sec.min_transit_time_passenger_minutes),
                "status":              self._g[sec.from_station_id][sec.to_station_id].get("status", SectionStatus.CLEAR.value),
                "weather_speed_factor":self._g[sec.from_station_id][sec.to_station_id].get("weather_speed_factor", 1.0),
                "active_caution_order":self._g[sec.from_station_id][sec.to_station_id].get("active_caution_order", False),
            }
            for section_id, sec in self._sections.items()
        }

    def __repr__(self) -> str:
        return (
            f"CorridorGraph("
            f"stations={self.num_stations}, "
            f"sections={self.num_sections}, "
            f"single_line={len(self.single_line_sections())})"
        )
