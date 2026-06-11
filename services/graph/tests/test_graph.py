"""
MARG Railway Graph Engine — Test Suite
=======================================
Run with:
    cd /tmp/marg_test && python -m pytest test_graph.py -v
"""
from __future__ import annotations
import math, sys, pytest
sys.path.insert(0, '/sessions/jolly-charming-heisenberg/mnt/MARG-Copilot')

from services.graph.models.enums import (
    Direction, ElectrificationType, LineType, LoopLineType,
    SectionStatus, StationClass, TrainCategory, TrainPriority,
)
from services.graph.models.loop_line import LoopLine
from services.graph.models.station import Platform, Station
from services.graph.models.section import SignalBlock, TrackSection
from services.graph.graph.corridor_graph import CorridorGraph, GraphError
from services.graph.graph.algorithms import (
    Bottleneck, CascadeNode, CascadeResult, CrossingPlan, PathResult, RailwayAlgorithms,
)
from services.graph.graph.queries import CorridorSummary, GraphQueries
from services.graph.data.ndls_cnb import (
    STATIONS, SECTIONS, STATION_INDEX, SECTION_INDEX, get_station, get_section,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def graph():
    return CorridorGraph.build()

@pytest.fixture(scope="session")
def algo(graph):
    return RailwayAlgorithms(graph)

@pytest.fixture(scope="session")
def gq():
    return GraphQueries.build()

# ── 1. Enums ──────────────────────────────────────────────────────────────────

class TestEnums:
    def test_station_class_ordering(self):
        assert StationClass.A1 < StationClass.A < StationClass.B

    def test_train_priority_ordering(self):
        assert TrainPriority.P0 < TrainPriority.P1 < TrainPriority.P4

    def test_direction_values(self):
        assert Direction.UP.value == "up"
        assert Direction.DOWN.value == "down"

    def test_line_type_values(self):
        assert LineType.SINGLE.value == "single"
        assert LineType.DOUBLE.value == "double"

    def test_section_status_members(self):
        assert SectionStatus.CLEAR in SectionStatus
        assert SectionStatus.BLOCKED in SectionStatus
        assert SectionStatus.RESTRICTED in SectionStatus

# ── 2. LoopLine ───────────────────────────────────────────────────────────────

def _loop(length, electrified=True):
    return LoopLine("L1", "T", LoopLineType.CROSSING, length,
                    ElectrificationType.AC_25KV if electrified else ElectrificationType.DIESEL,
                    22.9)

class TestLoopLine:
    def test_can_hold_passenger_adequate(self):
        assert _loop(650, True).can_hold_passenger_train is True

    def test_cannot_hold_passenger_short(self):
        assert _loop(500, True).can_hold_passenger_train is False

    def test_cannot_hold_passenger_diesel(self):
        assert _loop(700, False).can_hold_passenger_train is False

    def test_can_hold_goods(self):
        assert _loop(750).can_hold_goods_train is True

    def test_cannot_hold_goods_short(self):
        assert _loop(600).can_hold_goods_train is False

    def test_can_accommodate_no_electrification_required(self):
        assert _loop(700, False).can_accommodate(680, requires_electrification=False) is True

    def test_cannot_accommodate_too_long(self):
        assert _loop(600).can_accommodate(650) is False

    def test_can_accommodate_exact_fit(self):
        assert _loop(600).can_accommodate(600) is True

# ── 3. Station ────────────────────────────────────────────────────────────────

class TestStation:
    def test_ndls_is_terminus(self):
        assert get_station("NDLS").is_terminus is True

    def test_cnb_is_terminus(self):
        assert get_station("CNB").is_terminus is True

    def test_aljn_is_junction(self):
        assert get_station("ALJN").is_junction is True

    def test_chainage_ascending(self):
        ch = [s.chainage_km for s in STATIONS]
        assert ch == sorted(ch)

    def test_ndls_chainage_zero(self):
        assert get_station("NDLS").chainage_km == 0.0

    def test_cnb_chainage(self):
        assert 430 <= get_station("CNB").chainage_km <= 450

    def test_best_loop_adequate(self):
        loop = get_station("ALJN").best_loop_for(640)
        assert loop is not None and loop.length_meters >= 640

    def test_best_loop_none_for_huge_train(self):
        assert get_station("ALJN").best_loop_for(2000) is None

    def test_can_cross_trains_returns_bool(self):
        assert isinstance(get_station("ALJN").can_cross_trains(600, 600), bool)

    def test_halt_passenger_a1(self):
        assert get_station("NDLS").min_halt_passenger_seconds == 120

    def test_halt_goods_a1(self):
        assert get_station("NDLS").min_halt_goods_seconds == 300

    def test_num_loop_lines_positive(self):
        assert get_station("ALJN").num_loop_lines > 0

    def test_max_loop_length_positive(self):
        assert get_station("ALJN").max_loop_length_m > 0

    def test_to_node_attrs_keys(self):
        attrs = get_station("NDLS").to_node_attrs()
        for k in ("name", "chainage_km", "latitude", "longitude"):
            assert k in attrs, f"Missing key: {k}"

    def test_lat_lon_in_india(self):
        for st in STATIONS:
            assert 20 <= st.latitude <= 35
            assert 72 <= st.longitude <= 82

# ── 4. TrackSection ───────────────────────────────────────────────────────────

class TestTrackSection:
    def test_section_count(self):
        assert len(SECTIONS) == 48

    def test_positive_lengths(self):
        for s in SECTIONS:
            assert s.length_km > 0

    def test_pax_speed_gte_freight(self):
        for s in SECTIONS:
            assert s.max_speed_passenger_kmh >= s.max_speed_freight_kmh

    def test_theoretical_capacity_positive(self):
        for s in SECTIONS:
            assert s.theoretical_capacity_trains_per_hour > 0

    def test_min_transit_time_consistent(self):
        sec = get_section("NDLS_TKJ_UP")
        expected = (sec.length_km / sec.max_speed_passenger_kmh) * 60
        assert abs(sec.min_transit_time_passenger_minutes - expected) < 0.5

    def test_single_line_sections_exist(self):
        assert len([s for s in SECTIONS if s.is_single_line]) > 0

    def test_fzd_skb_is_single(self):
        assert get_section("FZD_SKB_UP").is_single_line

    def test_ndls_tkj_is_double(self):
        assert get_section("NDLS_TKJ_UP").is_double_line

    def test_effective_speed_no_factors(self):
        sec = get_section("NDLS_TKJ_UP")
        assert sec.effective_speed_kmh(True, weather_speed_factor=1.0) == sec.max_speed_passenger_kmh

    def test_effective_speed_weather(self):
        sec = get_section("NDLS_TKJ_UP")
        assert sec.effective_speed_kmh(True, weather_speed_factor=0.5) < sec.max_speed_passenger_kmh

    def test_effective_speed_caution(self):
        sec = get_section("ALJN_BSWA_UP")
        assert sec.effective_speed_kmh(True, caution_order_kmh=30.0) <= 30.0

    def test_transit_time_fog_longer(self):
        sec = get_section("ALJN_BSWA_UP")
        t_clear = sec.transit_time_minutes(True, weather_speed_factor=1.0)
        t_fog   = sec.transit_time_minutes(True, weather_speed_factor=0.15)
        assert t_fog > t_clear

    def test_has_adverse_gradient_is_list(self):
        result = [s for s in SECTIONS if s.has_adverse_gradient]
        assert isinstance(result, list)

    def test_to_edge_attrs_keys(self):
        attrs = get_section("NDLS_TKJ_UP").to_edge_attrs()
        for k in ("section", "travel_min", "congestion_score", "status"):
            assert k in attrs

    def test_to_edge_attrs_initial_congestion_zero(self):
        assert get_section("NDLS_TKJ_UP").to_edge_attrs()["congestion_score"] == 0.0

    def test_to_edge_attrs_initial_status_clear(self):
        assert get_section("NDLS_TKJ_UP").to_edge_attrs()["status"] == SectionStatus.CLEAR.value

# ── 5. CorridorGraph construction ─────────────────────────────────────────────

class TestCorridorGraphConstruction:
    def test_station_count(self, graph):
        assert graph.num_stations == 25

    def test_section_count(self, graph):
        assert graph.num_sections == 48

    def test_all_station_ids_present(self, graph):
        for st in STATIONS:
            assert st.station_id in graph.station_ids

    def test_station_accessor(self, graph):
        assert graph.station("NDLS").name == "New Delhi"

    def test_section_accessor(self, graph):
        sec = graph.section("NDLS_TKJ_UP")
        assert sec.from_station_id == "NDLS" and sec.to_station_id == "TKJ"

    def test_unknown_station_raises(self, graph):
        with pytest.raises(GraphError, match="Unknown station"):
            graph.station("XXXX")

    def test_unknown_section_raises(self, graph):
        with pytest.raises(GraphError, match="Unknown section"):
            graph.section("XXXX_YYYY_UP")

    def test_no_direct_edge_raises(self, graph):
        with pytest.raises(GraphError, match="No edge"):
            graph.edge_attrs("NDLS", "CNB")

    def test_invalid_section_raises_at_build(self):
        bad = TrackSection("BAD_UP", "XXXX", "NDLS", Direction.UP, 10.0,
                           LineType.DOUBLE, 130, 75, 0.0, ElectrificationType.AC_25KV, [])
        with pytest.raises(GraphError, match="references unknown station"):
            CorridorGraph.build(stations=STATIONS, sections=[bad])

    def test_single_line_filter(self, graph):
        singles = graph.single_line_sections()
        assert all(s.line_type == LineType.SINGLE for s in singles)

    def test_double_line_filter(self, graph):
        doubles = graph.double_line_sections()
        assert all(s.line_type == LineType.DOUBLE for s in doubles)

    def test_junction_stations(self, graph):
        assert "ALJN" in [j.station_id for j in graph.junction_stations()]

    def test_crew_change_stations(self, graph):
        assert len(graph.crew_change_stations()) > 0

    def test_stations_ordered_up(self, graph):
        ch = [s.chainage_km for s in graph.stations_ordered_up()]
        assert ch == sorted(ch)

    def test_outgoing_sections_ndls(self, graph):
        secs = graph.outgoing_sections("NDLS")
        assert all(s.from_station_id == "NDLS" for s in secs)

    def test_incoming_sections_cnb(self, graph):
        secs = graph.incoming_sections("CNB")
        assert all(s.to_station_id == "CNB" for s in secs)

    def test_sections_between(self, graph):
        assert len(graph.sections_between("NDLS", "TKJ")) > 0

    def test_repr(self, graph):
        r = repr(graph)
        assert "CorridorGraph" in r and "25" in r

# ── 6. Runtime updates ────────────────────────────────────────────────────────

class TestRuntimeUpdates:
    def test_congestion_increases_travel_min(self, graph):
        sid = "NDLS_TKJ_UP"
        graph.update_congestion(sid, 0.0)
        before = graph.section_attrs(sid)["travel_min"]
        graph.update_congestion(sid, 0.9)
        assert graph.section_attrs(sid)["travel_min"] > before
        graph.update_congestion(sid, 0.0)

    def test_congestion_zero_restores_base(self, graph):
        sid = "NDLS_TKJ_UP"
        sec = graph.section(sid)
        graph.update_congestion(sid, 0.0)
        assert abs(graph.section_attrs(sid)["travel_min"] - sec.min_transit_time_passenger_minutes) < 0.1

    def test_congestion_invalid_raises(self, graph):
        with pytest.raises(ValueError):
            graph.update_congestion("NDLS_TKJ_UP", 1.5)

    def test_weather_increases_travel(self, graph):
        sid = "NDLS_TKJ_UP"
        graph.update_congestion(sid, 0.0)
        graph.update_weather(sid, 1.0)
        clear = graph.section_attrs(sid)["travel_min"]
        graph.update_weather(sid, 0.15)
        assert graph.section_attrs(sid)["travel_min"] > clear
        graph.update_weather(sid, 1.0)

    def test_weather_invalid_raises(self, graph):
        with pytest.raises(ValueError):
            graph.update_weather("NDLS_TKJ_UP", 0.0)

    def test_blocked_sets_high_travel_min(self, graph):
        sid = "GZB_DDN_UP"
        graph.update_status(sid, SectionStatus.BLOCKED)
        assert graph.section_attrs(sid)["travel_min"] >= 1e8
        graph.update_status(sid, SectionStatus.CLEAR)

    def test_clear_restores_travel_min(self, graph):
        sid = "GZB_DDN_UP"
        graph.update_status(sid, SectionStatus.BLOCKED)
        graph.update_status(sid, SectionStatus.CLEAR)
        assert graph.section_attrs(sid)["travel_min"] < 1e8

    def test_caution_order_increases_travel(self, graph):
        sid = "ALJN_BSWA_UP"
        graph.update_congestion(sid, 0.0)
        graph.update_weather(sid, 1.0)
        normal = graph.section_attrs(sid)["travel_min"]
        graph.set_caution_order(sid, 30.0)
        assert graph.section_attrs(sid)["travel_min"] > normal
        assert graph.section_attrs(sid)["active_caution_order"] is True
        graph.clear_caution_order(sid)

    def test_clear_caution_removes_restriction(self, graph):
        sid = "ALJN_BSWA_UP"
        graph.set_caution_order(sid, 30.0)
        graph.clear_caution_order(sid)
        attrs = graph.section_attrs(sid)
        assert attrs["active_caution_order"] is False
        assert attrs["caution_order_kmh"] is None

    def test_bulk_update_congestion(self, graph):
        graph.bulk_update_congestion({"NDLS_TKJ_UP": 0.5, "TKJ_SZM_UP": 0.7})
        assert graph.section_attrs("NDLS_TKJ_UP")["congestion_score"] == 0.5
        assert graph.section_attrs("TKJ_SZM_UP")["congestion_score"] == 0.7
        graph.bulk_update_congestion({"NDLS_TKJ_UP": 0.0, "TKJ_SZM_UP": 0.0})

    def test_bulk_update_weather(self, graph):
        graph.bulk_update_weather({"NDLS_TKJ_UP": 0.5})
        assert graph.section_attrs("NDLS_TKJ_UP")["weather_speed_factor"] == 0.5
        graph.bulk_update_weather({"NDLS_TKJ_UP": 1.0})

    def test_bulk_ignores_unknown(self, graph):
        graph.bulk_update_congestion({"UNKNOWN": 0.8})  # must not raise

    def test_geojson_nodes(self, graph):
        gj = graph.to_geojson_nodes()
        assert gj["type"] == "FeatureCollection" and len(gj["features"]) == 25

    def test_geojson_edges(self, graph):
        gj = graph.to_geojson_edges()
        assert gj["type"] == "FeatureCollection" and len(gj["features"]) > 0

    def test_state_snapshot(self, graph):
        snap = graph.current_state_snapshot()
        assert len(snap) == 48
        sample = next(iter(snap.values()))
        assert "congestion_score" in sample and "travel_min" in sample

    def test_weight_function(self, graph):
        attrs = graph.section_attrs("NDLS_TKJ_UP")
        assert graph.travel_time_weight("NDLS", "TKJ", attrs) == attrs["travel_min"]

# ── 7. Shortest path ──────────────────────────────────────────────────────────

class TestShortestPath:
    def test_feasible(self, algo):
        r = algo.shortest_path("NDLS", "CNB")
        assert r.is_feasible and r.path[0] == "NDLS" and r.path[-1] == "CNB"

    def test_travel_time_realistic(self, algo):
        r = algo.shortest_path("NDLS", "CNB")
        assert 180 <= r.total_travel_min <= 400

    def test_distance_realistic(self, algo):
        r = algo.shortest_path("NDLS", "CNB")
        assert 420 <= r.total_length_km <= 460

    def test_sections_count_matches_hops(self, algo):
        r = algo.shortest_path("NDLS", "CNB")
        assert r.num_hops == len(r.path) - 1

    def test_adjacent(self, algo):
        r = algo.shortest_path("NDLS", "TKJ")
        assert r.is_feasible and r.path == ["NDLS", "TKJ"]

    def test_unknown_source_infeasible(self, algo):
        assert not algo.shortest_path("XXXX", "CNB").is_feasible

    def test_unknown_target_infeasible(self, algo):
        assert not algo.shortest_path("NDLS", "XXXX").is_feasible

    def test_freight_feasible(self, algo):
        assert algo.shortest_path("NDLS", "CNB", is_passenger=False).is_feasible

    def test_freight_slower(self, algo):
        pax = algo.shortest_path("NDLS", "CNB", True)
        frgt = algo.shortest_path("NDLS", "CNB", False)
        assert frgt.total_travel_min >= pax.total_travel_min

    def test_congestion_increases_time(self, graph, algo):
        sid = "ALJN_BSWA_UP"
        graph.update_congestion(sid, 0.0)
        normal = algo.shortest_path("ALJN", "BSWA")
        graph.update_congestion(sid, 0.95)
        congested = algo.shortest_path("ALJN", "BSWA")
        assert congested.total_travel_min > normal.total_travel_min
        graph.update_congestion(sid, 0.0)

# ── 8. Rerouting ──────────────────────────────────────────────────────────────

class TestRerouting:
    def test_returns_path_result(self, algo):
        assert isinstance(algo.reroute_avoiding("NDLS", "GZB", "NDLS_TKJ_UP"), PathResult)

    def test_avoids_blocked_section(self, algo):
        blocked = "GZB_DDN_UP"
        r = algo.reroute_avoiding("NDLS", "CNB", blocked)
        if r.is_feasible:
            assert blocked not in {s.section_id for s in r.sections}

    def test_reason_populated(self, algo):
        r = algo.reroute_avoiding("NDLS", "CNB", "NDLS_TKJ_UP")
        assert isinstance(r.reason, str)

    def test_unknown_section_raises(self, algo):
        with pytest.raises(GraphError, match="Unknown section"):
            algo.reroute_avoiding("NDLS", "CNB", "NONEXISTENT_UP")

# ── 9. Crossing ───────────────────────────────────────────────────────────────

class TestCrossing:
    def _plan(self, algo, radius=120.0):
        return algo.find_crossing_stations(
            "12301", "NDLS", 640, 0, 5.0,
            "70501", "ALJN", 720, 4, 45.0,
            search_radius_km=radius,
        )

    def test_plan_found(self, algo):
        assert isinstance(self._plan(algo), CrossingPlan)

    def test_train_ids(self, algo):
        p = self._plan(algo)
        assert p.train_a_id == "12301" and p.train_b_id == "70501"

    def test_waiter_and_mover_valid(self, algo):
        p = self._plan(algo)
        assert p.waiter in {"12301", "70501"}
        assert p.mover != p.waiter

    def test_loop_fits_train(self, algo):
        p = self._plan(algo)
        assert p.loop is not None and p.loop.length_meters >= 640

    def test_alternatives_is_list(self, algo):
        assert isinstance(self._plan(algo).alternatives, list)

    def test_wait_non_negative(self, algo):
        assert self._plan(algo).estimated_wait_minutes >= 0

    def test_no_feasible_station_raises(self, algo):
        with pytest.raises(GraphError, match="No feasible crossing point"):
            algo.find_crossing_stations(
                "A", "NDLS", 640, 0, 0,
                "B", "CNB",  640, 4, 0,
                search_radius_km=0.1,
            )

# ── 10. Bottlenecks ───────────────────────────────────────────────────────────

class TestBottlenecks:
    def test_no_trains_empty(self, algo):
        assert algo.detect_bottlenecks({}) == []

    def test_low_utilisation_no_bottleneck(self, algo):
        assert algo.detect_bottlenecks({"NDLS_TKJ_UP": 1}) == []

    def test_high_utilisation_warning(self, algo):
        sec = get_section("FZD_SKB_UP")
        count = math.ceil(sec.theoretical_capacity_trains_per_hour * 0.80)
        result = algo.detect_bottlenecks({"FZD_SKB_UP": count})
        assert len(result) > 0

    def test_overloaded_critical(self, algo):
        sec = get_section("FZD_SKB_UP")
        count = math.ceil(sec.theoretical_capacity_trains_per_hour * 1.1)
        result = algo.detect_bottlenecks({"FZD_SKB_UP": count})
        assert any(b.severity == "critical" for b in result)

    def test_sorted_descending(self, algo):
        s1 = get_section("FZD_SKB_UP")
        s2 = get_section("SKB_JSN_UP")
        counts = {
            "FZD_SKB_UP": math.ceil(s1.theoretical_capacity_trains_per_hour * 1.1),
            "SKB_JSN_UP": math.ceil(s2.theoretical_capacity_trains_per_hour * 0.80),
        }
        result = algo.detect_bottlenecks(counts)
        if len(result) >= 2:
            assert result[0].utilisation_ratio >= result[1].utilisation_ratio

    def test_unknown_section_skipped(self, algo):
        assert algo.detect_bottlenecks({"UNKNOWN": 999}) == []

    def test_contributing_stations(self, algo):
        sec = get_section("FZD_SKB_UP")
        count = math.ceil(sec.theoretical_capacity_trains_per_hour * 1.1)
        result = algo.detect_bottlenecks({"FZD_SKB_UP": count})
        if result:
            assert len(result[0].contributing_station_ids) == 2

# ── 11. Cascade ───────────────────────────────────────────────────────────────

class TestCascade:
    def test_no_deps_empty(self, algo):
        r = algo.trace_cascade("12301", 30.0, [])
        assert r.num_trains_affected == 0 and r.total_delay_minutes == 0.0

    def test_root_not_in_graph(self, algo):
        r = algo.trace_cascade("UNKNOWN", 30.0, [("OTHER", "THIRD", 10.0, "ALJN")])
        assert r.num_trains_affected == 0

    def test_single_hop(self, algo):
        r = algo.trace_cascade("12301", 30.0, [("12301", "14015", 15.0, "ALJN")])
        assert r.num_trains_affected == 1
        assert r.affected[0].train_id == "14015"
        assert abs(r.affected[0].delay_minutes - 18.5) < 0.5

    def test_multi_hop(self, algo):
        deps = [("12301","14015",15.0,"ALJN"), ("14015","14311",18.0,"TDL")]
        assert algo.trace_cascade("12301", 30.0, deps).num_trains_affected == 2

    def test_max_depth_respected(self, algo):
        deps = [(str(i), str(i+1), 5.0, "ALJN") for i in range(20)]
        r = algo.trace_cascade("0", 10.0, deps, max_depth=3)
        assert r.max_depth <= 3

    def test_total_delay_is_sum(self, algo):
        deps = [("12301","14015",10.0,"ALJN"), ("12301","14311",8.0,"TDL")]
        r = algo.trace_cascade("12301", 20.0, deps)
        assert abs(r.total_delay_minutes - sum(n.delay_minutes for n in r.affected)) < 0.1

# ── 12. Spatial helpers ───────────────────────────────────────────────────────

class TestSpatial:
    def test_chainage_ndls_cnb(self, algo):
        assert 420 <= algo.chainage_distance_km("NDLS", "CNB") <= 460

    def test_chainage_symmetric(self, algo):
        assert abs(algo.chainage_distance_km("NDLS","ALJN") - algo.chainage_distance_km("ALJN","NDLS")) < 0.01

    def test_stations_in_range(self, algo):
        result = algo.stations_in_range("ALJN", 50.0)
        assert len(result) > 0 and all(s.station_id != "ALJN" for s in result)

    def test_direction_up_only(self, algo):
        ref = get_station("ALJN")
        for st in algo.stations_in_range("ALJN", 60.0, Direction.UP):
            assert st.chainage_km > ref.chainage_km

    def test_direction_down_only(self, algo):
        ref = get_station("ALJN")
        for st in algo.stations_in_range("ALJN", 60.0, Direction.DOWN):
            assert st.chainage_km < ref.chainage_km

    def test_saturation_zero_trains(self, algo):
        assert algo.corridor_saturation({}) == 0.0

    def test_saturation_bounded(self, algo):
        counts = {sid: 100 for sid in list(SECTION_INDEX.keys())[:5]}
        assert 0.0 <= algo.corridor_saturation(counts) <= 1.0

    def test_saturation_monotone(self, algo):
        s1 = algo.corridor_saturation({"FZD_SKB_UP": 2})
        s2 = algo.corridor_saturation({"FZD_SKB_UP": 4})
        assert s2 >= s1 or (s1 == 1.0 and s2 == 1.0)

# ── 13. GraphQueries facade ───────────────────────────────────────────────────

class TestGraphQueries:
    def test_build(self):
        assert isinstance(GraphQueries.build(), GraphQueries)

    def test_summary(self, gq):
        s = gq.summary()
        assert isinstance(s, CorridorSummary)
        assert s.num_stations == 25 and s.num_sections == 48

    def test_all_stations_ordered(self, gq):
        stations = gq.all_stations()
        ch = [s.chainage_km for s in stations]
        assert ch == sorted(ch) and len(stations) == 25

    def test_all_sections(self, gq):
        assert len(gq.all_sections()) == 48

    def test_path_feasible(self, gq):
        assert gq.path("NDLS", "CNB").is_feasible

    def test_path_infeasible(self, gq):
        assert not gq.path("NDLS", "XXXX").is_feasible

    def test_reroute(self, gq):
        assert isinstance(gq.reroute("NDLS", "CNB", "GZB_DDN_UP"), PathResult)

    def test_crossing_plan(self, gq):
        plan = gq.crossing_plan("12301","NDLS",640,0,5.0,"70501","ALJN",720,4,45.0,120.0)
        assert isinstance(plan, CrossingPlan)

    def test_can_cross_at(self, gq):
        assert isinstance(gq.can_cross_at("ALJN", 640, 640), bool)

    def test_bottlenecks_empty(self, gq):
        assert gq.bottlenecks({}) == []

    def test_cascade_empty(self, gq):
        assert gq.cascade("12301", 30.0, []).num_trains_affected == 0

    def test_saturation_zero(self, gq):
        assert gq.corridor_saturation({}) == 0.0

    def test_distance_km(self, gq):
        assert 420 <= gq.distance_km("NDLS", "CNB") <= 460

    def test_stations_near(self, gq):
        assert len(gq.stations_near("ALJN", 50.0)) > 0

    def test_apply_snapshot_no_error(self, gq):
        gq.apply_snapshot({"NDLS_TKJ_UP": 0.5}, {"NDLS_TKJ_UP": 0.8}, [], {})
        gq.apply_snapshot({"NDLS_TKJ_UP": 0.0}, {"NDLS_TKJ_UP": 1.0}, [], {})

    def test_apply_snapshot_unknown_sections(self, gq):
        gq.apply_snapshot({"UNKNOWN": 0.9}, {}, ["ALSO_UNKNOWN"], {})  # no raise

    def test_geojson_nodes(self, gq):
        assert gq.geojson_nodes()["type"] == "FeatureCollection"

    def test_geojson_edges(self, gq):
        assert gq.geojson_edges()["type"] == "FeatureCollection"

    def test_state_snapshot(self, gq):
        assert len(gq.state_snapshot()) == 48

# ── 14. Data helpers ──────────────────────────────────────────────────────────

class TestDataHelpers:
    def test_station_index_count(self):
        assert len(STATION_INDEX) == 25

    def test_section_index_count(self):
        assert len(SECTION_INDEX) == 48

    def test_get_station_known(self):
        assert get_station("ALJN").name == "Aligarh Junction"

    def test_get_station_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown station"):
            get_station("XXXX")

    def test_get_section_known(self):
        assert get_section("ALJN_BSWA_UP").from_station_id == "ALJN"

    def test_get_section_unknown_raises(self):
        with pytest.raises(KeyError, match="Unknown section"):
            get_section("XXXX_YYYY_UP")

    def test_all_sections_have_up_and_down(self):
        up_pairs   = {(s.from_station_id, s.to_station_id) for s in SECTIONS if s.direction == Direction.UP}
        down_pairs = {(s.from_station_id, s.to_station_id) for s in SECTIONS if s.direction == Direction.DOWN}
        for (a, b) in up_pairs:
            assert (b, a) in down_pairs, f"Missing DOWN section for UP pair ({a}→{b})"
