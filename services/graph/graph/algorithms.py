"""
Graph algorithms for the MARG Railway Graph Engine.

All algorithms operate on a CorridorGraph and return structured result
objects rather than raw NetworkX output. This keeps the calling code
(simulation engine, optimization engine) decoupled from NetworkX internals.

Algorithms implemented
----------------------
1.  shortest_path           — Dijkstra with congestion-aware weights.
2.  reroute_avoiding        — Shortest path excluding a blocked section.
3.  find_crossing_stations  — Feasible crossing points for two opposing trains.
4.  detect_bottlenecks      — Sections where flow will exceed capacity.
5.  trace_cascade           — BFS over a train-dependency graph.
6.  chainage_distance       — Direct distance between any two stations.
7.  stations_in_range       — Stations within N km of a reference point.
8.  corridor_saturation     — Global saturation index.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

import networkx as nx

from ..models.enums import Direction, LineType, SectionStatus
from ..models.loop_line import LoopLine
from ..models.section import TrackSection
from ..models.station import Station
from .corridor_graph import CorridorGraph, GraphError

logger = logging.getLogger(__name__)


# ── Result dataclasses ────────────────────────────────────────────────────────

@dataclass
class PathResult:
    """Result of a shortest-path query."""
    source: str
    target: str
    path: list[str]                  # ordered station IDs
    sections: list[TrackSection]     # sections traversed
    total_travel_min: float          # sum of current travel_min weights
    total_length_km: float
    is_feasible: bool
    reason: str = ""                 # populated when infeasible

    @property
    def num_hops(self) -> int:
        return len(self.sections)


@dataclass
class CrossingOption:
    """A candidate station at which two opposing trains can cross."""
    station: Station
    loop: LoopLine
    train_a_wait_min: float          # estimated wait for train A
    train_b_wait_min: float          # estimated wait for train B
    recommended_waiter: str          # train_id of lower-priority train
    cost_if_a_waits: float           # weighted delay cost
    cost_if_b_waits: float
    optimal_waiter: str              # train_id with minimum cost


@dataclass
class CrossingPlan:
    """Optimal crossing plan for two opposing trains."""
    train_a_id: str
    train_b_id: str
    crossing_station: Station
    loop: LoopLine
    waiter: str                      # train_id that enters the loop
    mover: str                       # train_id that uses main line
    estimated_wait_minutes: float
    total_delay_cost: float
    alternatives: list[CrossingOption] = field(default_factory=list)


@dataclass
class Bottleneck:
    """A section approaching or exceeding capacity."""
    section: TrackSection
    utilisation_ratio: float         # 0–1+ (> 1 = overloaded)
    trains_in_window: int
    capacity_in_window: float
    severity: str                    # "info" | "warning" | "critical"
    minutes_to_saturation: Optional[float]
    contributing_station_ids: list[str] = field(default_factory=list)


@dataclass
class CascadeNode:
    """A single train affected by a cascade."""
    train_id: str
    cascade_depth: int               # hops from root cause
    delay_minutes: float             # delay attributable to cascade
    conflict_station: str
    conflict_time_minutes: float     # minutes from now


@dataclass
class CascadeResult:
    """Full cascade chain rooted at one delayed/failed train."""
    root_train_id: str
    affected: list[CascadeNode]
    total_delay_minutes: float
    max_depth: int

    @property
    def num_trains_affected(self) -> int:
        return len(self.affected)


# ── Algorithm implementations ─────────────────────────────────────────────────

class RailwayAlgorithms:
    """
    Stateless collection of graph algorithms.
    Instantiate with a CorridorGraph; all methods operate on that graph.

    Parameters
    ----------
    graph:
        The CorridorGraph to operate on.
    """

    def __init__(self, graph: CorridorGraph) -> None:
        self._cg = graph

    # ── 1. Shortest path ──────────────────────────────────────────────────────

    def shortest_path(
        self,
        source: str,
        target: str,
        is_passenger: bool = True,
    ) -> PathResult:
        """
        Dijkstra shortest path between two stations using current
        congestion-aware travel times as edge weights.

        Parameters
        ----------
        source, target:
            Station IDs.
        is_passenger:
            Determines whether passenger or freight travel times are used.

        Returns
        -------
        PathResult
            Infeasible result if no path exists (e.g., full blockage).
        """
        weight_fn = (
            self._cg.travel_time_weight
            if is_passenger
            else self._cg.freight_travel_time_weight
        )

        try:
            path: list[str] = nx.shortest_path(
                self._cg.graph, source, target, weight=weight_fn
            )
            length: float = nx.shortest_path_length(
                self._cg.graph, source, target, weight=weight_fn
            )
        except nx.NetworkXNoPath:
            return PathResult(
                source=source, target=target, path=[], sections=[],
                total_travel_min=float("inf"), total_length_km=0.0,
                is_feasible=False, reason="No path between stations.",
            )
        except nx.NodeNotFound as exc:
            return PathResult(
                source=source, target=target, path=[], sections=[],
                total_travel_min=float("inf"), total_length_km=0.0,
                is_feasible=False, reason=str(exc),
            )

        sections = self._path_to_sections(path)
        total_km  = sum(s.length_km for s in sections)

        return PathResult(
            source=source,
            target=target,
            path=path,
            sections=sections,
            total_travel_min=length,
            total_length_km=total_km,
            is_feasible=True,
        )

    # ── 2. Rerouting around a blocked section ─────────────────────────────────

    def reroute_avoiding(
        self,
        source: str,
        target: str,
        blocked_section_id: str,
        is_passenger: bool = True,
    ) -> PathResult:
        """
        Find an alternative path that avoids a specific section.
        Used when a loco failure, track blockage, or flood closes a section.

        The blocked section is temporarily removed from the graph view;
        the original graph is never mutated.

        Parameters
        ----------
        blocked_section_id:
            ID of the section to exclude, e.g. ``"TDL_FZD_UP"``.

        Returns
        -------
        PathResult
            Infeasible if no alternative route exists (common on
            NDLS–CNB which is largely single-corridor).
        """
        sec = self._cg.section(blocked_section_id)
        u, v = sec.from_station_id, sec.to_station_id

        # Build a graph view with the edge removed — does not mutate self._cg
        g_view = nx.restricted_view(self._cg.graph, nodes=[], edges=[(u, v)])

        weight_fn = (
            self._cg.travel_time_weight
            if is_passenger
            else self._cg.freight_travel_time_weight
        )

        try:
            path: list[str] = nx.shortest_path(g_view, source, target, weight=weight_fn)
            length: float   = nx.shortest_path_length(g_view, source, target, weight=weight_fn)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return PathResult(
                source=source, target=target, path=[], sections=[],
                total_travel_min=float("inf"), total_length_km=0.0,
                is_feasible=False,
                reason=f"No alternative path avoiding '{blocked_section_id}'.",
            )

        sections  = self._path_to_sections(path)
        total_km  = sum(s.length_km for s in sections)
        orig      = self.shortest_path(source, target, is_passenger)
        extra_min = length - orig.total_travel_min if orig.is_feasible else 0.0

        return PathResult(
            source=source,
            target=target,
            path=path,
            sections=sections,
            total_travel_min=length,
            total_length_km=total_km,
            is_feasible=True,
            reason=f"Rerouted via {' → '.join(path)}. Extra time: {extra_min:.1f} min.",
        )

    # ── 3. Crossing station finder ────────────────────────────────────────────

    def find_crossing_stations(
        self,
        train_a_id: str,
        train_a_pos_station: str,
        train_a_length_m: float,
        train_a_priority: int,
        train_a_delay_min: float,
        train_b_id: str,
        train_b_pos_station: str,
        train_b_length_m: float,
        train_b_priority: int,
        train_b_delay_min: float,
        search_radius_km: float = 80.0,
        requires_electrification: bool = True,
    ) -> CrossingPlan:
        """
        Find the optimal crossing station for two trains heading towards
        each other on a single-line section.

        The algorithm:
        1. Collect all stations within ``search_radius_km`` of both trains.
        2. Filter to stations that have a suitable loop.
        3. Score each candidate by weighted delay cost.
        4. Return the minimum-cost plan.

        Parameters
        ----------
        train_a_id, train_b_id:
            Train identifiers (for labelling the result).
        train_a_pos_station, train_b_pos_station:
            Current station IDs of each train.
        train_a_length_m, train_b_length_m:
            Total train lengths including locomotive (metres).
        train_a_priority, train_b_priority:
            Integer priority 0–4 (lower = higher priority).
        train_a_delay_min, train_b_delay_min:
            Current delays in minutes.
        search_radius_km:
            How far to search from each train's current position.
        requires_electrification:
            Whether electric supply is needed on the loop.

        Returns
        -------
        CrossingPlan
            Raises GraphError if no feasible crossing point is found.
        """
        st_a = self._cg.station(train_a_pos_station)
        st_b = self._cg.station(train_b_pos_station)

        # Stations reachable by train A (towards B) within radius
        candidates_a = self._stations_towards(
            train_a_pos_station, train_b_pos_station, search_radius_km
        )
        # Stations reachable by train B (towards A) within radius
        candidates_b = self._stations_towards(
            train_b_pos_station, train_a_pos_station, search_radius_km
        )

        # Union of reachable stations that both trains can reach
        candidate_ids = set(candidates_a) & set(candidates_b)

        options: list[CrossingOption] = []

        for station_id in candidate_ids:
            st = self._cg.station(station_id)
            loop = st.best_loop_for(
                max(train_a_length_m, train_b_length_m),
                requires_electrification,
            )
            if loop is None:
                continue

            # Estimate wait times: distance / effective speed (simplified)
            dist_a = abs(st.chainage_km - st_a.chainage_km)
            dist_b = abs(st.chainage_km - st_b.chainage_km)

            # Approximate arrival difference → one train must wait
            speed_a = 90.0   # km/h representative
            speed_b = 90.0
            eta_a   = (dist_a / speed_a) * 60   # minutes
            eta_b   = (dist_b / speed_b) * 60

            wait_if_a_waits = max(0.0, eta_b - eta_a) + 2.0   # 2 min signal clearance
            wait_if_b_waits = max(0.0, eta_a - eta_b) + 2.0

            # Weighted cost (lower priority pays more to wait)
            weight_a = [10.0, 6.0, 3.0, 1.0, 0.3][train_a_priority]
            weight_b = [10.0, 6.0, 3.0, 1.0, 0.3][train_b_priority]

            cost_a_waits = weight_a * (train_a_delay_min + wait_if_a_waits)
            cost_b_waits = weight_b * (train_b_delay_min + wait_if_b_waits)

            optimal_waiter = (
                train_a_id if cost_a_waits <= cost_b_waits else train_b_id
            )

            options.append(CrossingOption(
                station=st,
                loop=loop,
                train_a_wait_min=wait_if_a_waits,
                train_b_wait_min=wait_if_b_waits,
                recommended_waiter=(
                    train_a_id
                    if train_a_priority > train_b_priority
                    else train_b_id
                ),
                cost_if_a_waits=cost_a_waits,
                cost_if_b_waits=cost_b_waits,
                optimal_waiter=optimal_waiter,
            ))

        if not options:
            raise GraphError(
                f"No feasible crossing point found for trains "
                f"'{train_a_id}' and '{train_b_id}' within {search_radius_km} km."
            )

        best = min(
            options,
            key=lambda o: min(o.cost_if_a_waits, o.cost_if_b_waits),
        )
        total_cost = min(best.cost_if_a_waits, best.cost_if_b_waits)
        waiter     = best.optimal_waiter
        mover      = train_b_id if waiter == train_a_id else train_a_id
        wait_min   = (
            best.train_a_wait_min
            if waiter == train_a_id
            else best.train_b_wait_min
        )

        return CrossingPlan(
            train_a_id=train_a_id,
            train_b_id=train_b_id,
            crossing_station=best.station,
            loop=best.loop,
            waiter=waiter,
            mover=mover,
            estimated_wait_minutes=wait_min,
            total_delay_cost=total_cost,
            alternatives=sorted(
                options, key=lambda o: min(o.cost_if_a_waits, o.cost_if_b_waits)
            )[1:4],   # top 3 alternatives
        )

    # ── 4. Bottleneck detection ───────────────────────────────────────────────

    def detect_bottlenecks(
        self,
        train_counts_by_section: dict[str, int],
        window_hours: float = 1.0,
        warning_threshold: float = 0.75,
        critical_threshold: float = 0.92,
    ) -> list[Bottleneck]:
        """
        Identify sections where projected train flow approaches or exceeds
        theoretical capacity.

        Parameters
        ----------
        train_counts_by_section:
            Mapping of section_id → number of trains projected to use
            the section within ``window_hours``.
        window_hours:
            Time window for capacity calculation.
        warning_threshold:
            Utilisation above which a WARNING bottleneck is raised.
        critical_threshold:
            Utilisation above which a CRITICAL bottleneck is raised.

        Returns
        -------
        list[Bottleneck]
            Sorted by utilisation_ratio descending.
        """
        bottlenecks: list[Bottleneck] = []

        for section_id, train_count in train_counts_by_section.items():
            if section_id not in self._cg.section_ids:
                continue
            sec = self._cg.section(section_id)
            capacity = sec.theoretical_capacity_trains_per_hour * window_hours
            util     = train_count / capacity if capacity > 0 else float("inf")

            if util < warning_threshold:
                continue

            severity = (
                "critical" if util >= critical_threshold
                else "warning"  if util >= warning_threshold
                else "info"
            )

            # Minutes until saturation: how long until the section is full?
            if train_count > 0 and util < 1.0:
                mins = ((capacity - train_count) / capacity) * window_hours * 60
            elif util >= 1.0:
                mins = 0.0
            else:
                mins = None

            bottlenecks.append(Bottleneck(
                section=sec,
                utilisation_ratio=round(util, 3),
                trains_in_window=train_count,
                capacity_in_window=round(capacity, 2),
                severity=severity,
                minutes_to_saturation=mins,
                contributing_station_ids=[
                    sec.from_station_id, sec.to_station_id
                ],
            ))

        return sorted(
            bottlenecks, key=lambda b: b.utilisation_ratio, reverse=True
        )

    # ── 5. Cascade tracing (dependency BFS) ──────────────────────────────────

    def trace_cascade(
        self,
        root_train_id: str,
        root_delay_minutes: float,
        dependency_edges: list[tuple[str, str, float, str]],
        max_depth: int = 6,
    ) -> CascadeResult:
        """
        Trace a cascade chain from a root delayed train using BFS
        over a train-dependency graph.

        The dependency graph is constructed externally by the simulation
        engine (which knows train positions and conflicts). This method
        only performs the BFS and accumulates delay.

        Parameters
        ----------
        root_train_id:
            The train whose delay initiates the cascade.
        root_delay_minutes:
            Current delay of the root train.
        dependency_edges:
            List of (blocker_train_id, waiter_train_id, wait_minutes, station_id)
            tuples representing "blocker causes waiter to wait".
        max_depth:
            Maximum BFS depth (prevents runaway traversal on complex graphs).

        Returns
        -------
        CascadeResult
        """
        dep_graph: nx.DiGraph = nx.DiGraph()
        for blocker, waiter, wait_min, station in dependency_edges:
            dep_graph.add_edge(
                blocker, waiter,
                wait_minutes=wait_min,
                station=station,
            )

        if root_train_id not in dep_graph:
            return CascadeResult(
                root_train_id=root_train_id,
                affected=[],
                total_delay_minutes=0.0,
                max_depth=0,
            )

        affected: list[CascadeNode] = []
        queue: list[tuple[str, int, float]] = [(root_train_id, 0, root_delay_minutes)]
        visited: dict[str, float] = {root_train_id: root_delay_minutes}

        while queue:
            current, depth, incoming_delay = queue.pop(0)
            if depth >= max_depth:
                continue

            for successor in dep_graph.successors(current):
                edge = dep_graph[current][successor]
                wait_min = edge["wait_minutes"]
                # Delay propagated = wait time + 1.5 min restart + signal clearance
                propagated = wait_min + 1.5 + 2.0

                if successor in visited:
                    # Update if this path gives more delay
                    if propagated <= visited[successor]:
                        continue

                visited[successor] = propagated
                affected.append(CascadeNode(
                    train_id=successor,
                    cascade_depth=depth + 1,
                    delay_minutes=round(propagated, 1),
                    conflict_station=edge["station"],
                    conflict_time_minutes=float(depth + 1) * 8.0,  # rough estimate
                ))
                queue.append((successor, depth + 1, propagated))

        total = sum(n.delay_minutes for n in affected)
        max_d = max((n.cascade_depth for n in affected), default=0)

        return CascadeResult(
            root_train_id=root_train_id,
            affected=sorted(affected, key=lambda n: n.cascade_depth),
            total_delay_minutes=round(total, 1),
            max_depth=max_d,
        )

    # ── 6. Chainage distance ──────────────────────────────────────────────────

    def chainage_distance_km(self, station_a: str, station_b: str) -> float:
        """
        Absolute chainage distance between two stations.
        Sign-less — does not indicate direction.
        """
        return abs(
            self._cg.station(station_a).chainage_km
            - self._cg.station(station_b).chainage_km
        )

    # ── 7. Stations in range ──────────────────────────────────────────────────

    def stations_in_range(
        self,
        reference_station: str,
        radius_km: float,
        direction: Optional[Direction] = None,
    ) -> list[Station]:
        """
        Return stations within ``radius_km`` of a reference station,
        optionally filtered to one direction.

        Parameters
        ----------
        reference_station:
            Centre of the search.
        radius_km:
            Maximum chainage distance from the reference.
        direction:
            If Direction.UP, only return stations with higher chainage.
            If Direction.DOWN, only return stations with lower chainage.
            If None, return stations in both directions.
        """
        ref = self._cg.station(reference_station)
        result: list[Station] = []

        for st in self._cg.stations_ordered_up():
            if st.station_id == reference_station:
                continue
            dist = abs(st.chainage_km - ref.chainage_km)
            if dist > radius_km:
                continue
            if direction == Direction.UP and st.chainage_km <= ref.chainage_km:
                continue
            if direction == Direction.DOWN and st.chainage_km >= ref.chainage_km:
                continue
            result.append(st)

        return sorted(result, key=lambda s: abs(s.chainage_km - ref.chainage_km))

    # ── 8. Corridor saturation index ─────────────────────────────────────────

    def corridor_saturation(
        self,
        train_counts_by_section: dict[str, int],
        window_hours: float = 1.0,
    ) -> float:
        """
        A single scalar [0, 1] representing the overall saturation level
        of the corridor. 0 = fully clear, 1 = fully saturated.

        Computed as the capacity-weighted mean of section utilisations,
        capped at 1.0.

        Used by the frontend to set the global alert level.
        """
        total_weighted_util   = 0.0
        total_capacity_weight = 0.0

        for section_id, train_count in train_counts_by_section.items():
            if section_id not in self._cg.section_ids:
                continue
            sec      = self._cg.section(section_id)
            capacity = sec.theoretical_capacity_trains_per_hour * window_hours
            util     = min(1.0, train_count / capacity) if capacity > 0 else 1.0

            total_weighted_util   += util * capacity
            total_capacity_weight += capacity

        if total_capacity_weight == 0:
            return 0.0
        return round(total_weighted_util / total_capacity_weight, 3)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _path_to_sections(self, path: list[str]) -> list[TrackSection]:
        """Convert a list of station IDs to the traversed TrackSection objects."""
        sections: list[TrackSection] = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            if self._cg.graph.has_edge(u, v):
                sections.append(self._cg.graph[u][v]["section"])
        return sections

    def _stations_towards(
        self,
        from_station: str,
        towards_station: str,
        max_km: float,
    ) -> list[str]:
        """
        Return station IDs reachable from ``from_station`` heading
        towards ``towards_station``, within ``max_km`` chainage distance.
        """
        ref      = self._cg.station(from_station)
        target   = self._cg.station(towards_station)
        going_up = target.chainage_km > ref.chainage_km
        direction = Direction.UP if going_up else Direction.DOWN

        return [
            st.station_id
            for st in self.stations_in_range(from_station, max_km, direction)
        ]
