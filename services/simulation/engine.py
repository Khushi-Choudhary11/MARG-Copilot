"""
MARG Simulation Engine
======================
Top-level orchestrator.  Wires together:
  - EventEngine (DES core)
  - StateManager (mutable railway state)
  - MetricsCollector (performance tracking)
  - SnapshotRing (state history)
  - TrainScheduler (timetable → initial events)
  - Disruption controllers (weather, signal, blockage)

Typical usage
-------------
    from services.simulation.engine import SimulationEngine, SimulationConfig

    config = SimulationConfig(
        sim_start_min    = 360.0,   # 06:00
        sim_end_min      = 720.0,   # 12:00
        acceleration     = 60.0,    # 1 real-second = 1 sim-minute
        tick_interval    = 1.0,     # state snapshot every 1 sim-minute
        enable_fog       = True,
        enable_blockage  = True,
        enable_signal_fail = True,
    )
    engine = SimulationEngine(config)
    engine.build()
    stats  = engine.run()
    report = engine.metrics.to_json()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from services.simulation.core.clock       import SimClock
from services.simulation.core.event_engine import EventEngine, EngineStats
from services.simulation.core.event_types  import (
    EventType, Event, make_event,
)
from services.simulation.disruptions.signal_failure import (
    SignalFailureController, SignalFailPayload, SignalRestorePayload,
    etawah_signal_failure,
)
from services.simulation.disruptions.track_blockage import (
    TrackBlockageController, TrackBlockPayload, TrackClearPayload,
    tundla_blockage,
)
from services.simulation.disruptions.weather import (
    WeatherController, WeatherUpdatePayload,
    ndls_cnb_morning_fog_scenario,
)
from services.simulation.models.section_state import SectionCondition, SectionState
from services.simulation.models.station_state import StationState
from services.simulation.models.train       import Train, TrainStatus
from services.simulation.scheduler.timetable import (
    NDLS_CNB_TIMETABLE, ScheduledStop,
)
from services.simulation.scheduler.train_scheduler import (
    TrainScheduler, DepartPayload,
)
from services.simulation.state.metrics   import MetricsCollector
from services.simulation.state.snapshot  import SnapshotRing
from services.simulation.state.state_manager import StateManager, StateError

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

@dataclass
class SimulationConfig:
    """All tunable parameters for one simulation run."""
    sim_start_min:      float = 360.0    # 06:00
    sim_end_min:        float = 900.0    # 15:00
    acceleration:       float = 60.0    # wall-seconds per sim-minute
    tick_interval:      float = 1.0     # sim-minutes between state snapshots
    snapshot_capacity:  int   = 1_440   # number of snapshots to retain

    # Disruption flags
    enable_fog:          bool = True
    enable_heavy_rain:   bool = False
    enable_blockage:     bool = True
    enable_signal_fail:  bool = True

    # Stochastic disruptions (if False, uses canonical demo scenarios)
    stochastic:          bool = False
    random_seed:         int  = 42

    # Simulation identifier
    scenario_name:       str  = "NDLS-CNB Demo"


# ── NDLS-CNB section data ─────────────────────────────────────────────────────
# Mirrors the graph engine's corridor data as lightweight runtime objects.

_NDLS_CNB_SECTIONS: list[dict] = [
    # fmt: off
    {"id":"NDLS_TKJ_UP",  "from":"NDLS","to":"TKJ",  "len_km":5,   "pax_spd":100,"frt_spd":65,"cap":6,"single":False},
    {"id":"TKJ_SZM_UP",   "from":"TKJ", "to":"SZM",  "len_km":10,  "pax_spd":110,"frt_spd":70,"cap":5,"single":False},
    {"id":"SZM_GZB_UP",   "from":"SZM", "to":"GZB",  "len_km":13,  "pax_spd":110,"frt_spd":70,"cap":5,"single":False},
    {"id":"GZB_DDN_UP",   "from":"GZB", "to":"DDN",  "len_km":19,  "pax_spd":120,"frt_spd":75,"cap":5,"single":False},
    {"id":"DDN_KRJ_UP",   "from":"DDN", "to":"KRJ",  "len_km":43,  "pax_spd":130,"frt_spd":75,"cap":4,"single":False},
    {"id":"KRJ_SKR_UP",   "from":"KRJ", "to":"SKR",  "len_km":19,  "pax_spd":130,"frt_spd":75,"cap":4,"single":True},
    {"id":"SKR_HRS_UP",   "from":"SKR", "to":"HRS",  "len_km":9,   "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"HRS_ALJN_UP",  "from":"HRS", "to":"ALJN", "len_km":14,  "pax_spd":110,"frt_spd":70,"cap":5,"single":False},
    {"id":"ALJN_BSWA_UP", "from":"ALJN","to":"BSWA", "len_km":16,  "pax_spd":120,"frt_spd":75,"cap":4,"single":True},
    {"id":"BSWA_MRA_UP",  "from":"BSWA","to":"MRA",  "len_km":12,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"MRA_TDL_UP",   "from":"MRA", "to":"TDL",  "len_km":24,  "pax_spd":130,"frt_spd":75,"cap":4,"single":False},
    {"id":"TDL_FZD_UP",   "from":"TDL", "to":"FZD",  "len_km":13,  "pax_spd":120,"frt_spd":75,"cap":5,"single":True},
    {"id":"FZD_SKB_UP",   "from":"FZD", "to":"SKB",  "len_km":23,  "pax_spd":130,"frt_spd":75,"cap":4,"single":True},
    {"id":"SKB_JSN_UP",   "from":"SKB", "to":"JSN",  "len_km":12,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"JSN_BRN_UP",   "from":"JSN", "to":"BRN",  "len_km":12,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"BRN_ETW_UP",   "from":"BRN", "to":"ETW",  "len_km":22,  "pax_spd":130,"frt_spd":75,"cap":4,"single":False},
    {"id":"ETW_PFD_UP",   "from":"ETW", "to":"PFD",  "len_km":17,  "pax_spd":120,"frt_spd":75,"cap":5,"single":True},
    {"id":"PFD_SFI_UP",   "from":"PFD", "to":"SFI",  "len_km":13,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"SFI_KNJ_UP",   "from":"SFI", "to":"KNJ",  "len_km":16,  "pax_spd":120,"frt_spd":75,"cap":4,"single":True},
    {"id":"KNJ_GSJ_UP",   "from":"KNJ", "to":"GSJ",  "len_km":16,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"GSJ_ALJP_UP",  "from":"GSJ", "to":"ALJP", "len_km":14,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"ALJP_PNK_UP",  "from":"ALJP","to":"PNK",  "len_km":16,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"PNK_RRL_UP",   "from":"PNK", "to":"RRL",  "len_km":16,  "pax_spd":100,"frt_spd":65,"cap":5,"single":True},
    {"id":"RRL_CNB_UP",   "from":"RRL", "to":"CNB",  "len_km":67,  "pax_spd":130,"frt_spd":75,"cap":4,"single":False},
    # DOWN direction
    {"id":"CNB_RRL_DOWN", "from":"CNB", "to":"RRL",  "len_km":67,  "pax_spd":130,"frt_spd":75,"cap":4,"single":False},
    {"id":"RRL_PNK_DOWN", "from":"RRL", "to":"PNK",  "len_km":16,  "pax_spd":100,"frt_spd":65,"cap":5,"single":True},
    {"id":"PNK_ALJP_DOWN","from":"PNK", "to":"ALJP", "len_km":16,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"ALJP_GSJ_DOWN","from":"ALJP","to":"GSJ",  "len_km":14,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"GSJ_KNJ_DOWN", "from":"GSJ", "to":"KNJ",  "len_km":16,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"KNJ_SFI_DOWN", "from":"KNJ", "to":"SFI",  "len_km":16,  "pax_spd":120,"frt_spd":75,"cap":4,"single":True},
    {"id":"SFI_PFD_DOWN", "from":"SFI", "to":"PFD",  "len_km":13,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"PFD_ETW_DOWN", "from":"PFD", "to":"ETW",  "len_km":17,  "pax_spd":120,"frt_spd":75,"cap":5,"single":True},
    {"id":"ETW_BRN_DOWN", "from":"ETW", "to":"BRN",  "len_km":22,  "pax_spd":130,"frt_spd":75,"cap":4,"single":False},
    {"id":"BRN_JSN_DOWN", "from":"BRN", "to":"JSN",  "len_km":12,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"JSN_SKB_DOWN", "from":"JSN", "to":"SKB",  "len_km":12,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"SKB_FZD_DOWN", "from":"SKB", "to":"FZD",  "len_km":23,  "pax_spd":130,"frt_spd":75,"cap":4,"single":True},
    {"id":"FZD_TDL_DOWN", "from":"FZD", "to":"TDL",  "len_km":13,  "pax_spd":120,"frt_spd":75,"cap":5,"single":True},
    {"id":"TDL_MRA_DOWN", "from":"TDL", "to":"MRA",  "len_km":24,  "pax_spd":130,"frt_spd":75,"cap":4,"single":False},
    {"id":"MRA_BSWA_DOWN","from":"MRA", "to":"BSWA", "len_km":12,  "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"BSWA_ALJN_DOWN","from":"BSWA","to":"ALJN","len_km":16,  "pax_spd":120,"frt_spd":75,"cap":4,"single":True},
    {"id":"ALJN_HRS_DOWN","from":"ALJN","to":"HRS",  "len_km":14,  "pax_spd":110,"frt_spd":70,"cap":5,"single":False},
    {"id":"HRS_SKR_DOWN", "from":"HRS", "to":"SKR",  "len_km":9,   "pax_spd":110,"frt_spd":70,"cap":5,"single":True},
    {"id":"SKR_KRJ_DOWN", "from":"SKR", "to":"KRJ",  "len_km":19,  "pax_spd":130,"frt_spd":75,"cap":4,"single":True},
    {"id":"KRJ_DDN_DOWN", "from":"KRJ", "to":"DDN",  "len_km":43,  "pax_spd":130,"frt_spd":75,"cap":4,"single":False},
    {"id":"DDN_GZB_DOWN", "from":"DDN", "to":"GZB",  "len_km":19,  "pax_spd":120,"frt_spd":75,"cap":5,"single":False},
    {"id":"GZB_SZM_DOWN", "from":"GZB", "to":"SZM",  "len_km":13,  "pax_spd":110,"frt_spd":70,"cap":5,"single":False},
    {"id":"SZM_TKJ_DOWN", "from":"SZM", "to":"TKJ",  "len_km":10,  "pax_spd":110,"frt_spd":70,"cap":5,"single":False},
    {"id":"TKJ_NDLS_DOWN","from":"TKJ", "to":"NDLS", "len_km":5,   "pax_spd":100,"frt_spd":65,"cap":6,"single":False},
    # fmt: on
]

_STATION_IDS = [
    "NDLS","TKJ","SZM","GZB","DDN","KRJ","SKR","HRS",
    "ALJN","BSWA","MRA","TDL","FZD","SKB","JSN","BRN",
    "ETW","PFD","SFI","KNJ","GSJ","ALJP","PNK","RRL","CNB",
]

# Station index for adjacent-hop routing
_STATION_IDX: dict[str, int] = {s: i for i, s in enumerate(_STATION_IDS)}


def _adjacent_hops(from_station: str, to_station: str) -> list[str]:
    """
    Return the list of intermediate stations (inclusive of from, inclusive of to)
    along the corridor between two non-adjacent timetable stops.
    Returns [from_station, to_station] if they are already adjacent.
    Returns [] if either station is unknown.
    """
    ia = _STATION_IDX.get(from_station, -1)
    ib = _STATION_IDX.get(to_station, -1)
    if ia < 0 or ib < 0:
        return []
    if ia <= ib:
        return _STATION_IDS[ia: ib + 1]       # UP direction
    return list(reversed(_STATION_IDS[ib: ia + 1]))  # DOWN direction

_STATION_NAMES = {
    "NDLS": "New Delhi",       "TKJ": "Tilak Bridge",
    "SZM":  "Sahibabad",       "GZB": "Ghaziabad",
    "DDN":  "Dadri",           "KRJ": "Khurja",
    "SKR":  "Sikandra Rao",    "HRS": "Hathras",
    "ALJN": "Aligarh",         "BSWA":"Bharthana Bulandshahar",
    "MRA":  "Mathura",         "TDL": "Tundla",
    "FZD":  "Firozabad",       "SKB": "Shikohabad",
    "JSN":  "Jasrana",         "BRN": "Barhan",
    "ETW":  "Etawah",          "PFD": "Phaphund",
    "SFI":  "Saifai",          "KNJ": "Kannauj",
    "GSJ":  "Gursahaiganj",    "ALJP":"Allahabad City",
    "PNK":  "Panki",           "RRL": "Rawatpur",
    "CNB":  "Kanpur Central",
}


# ── Engine ────────────────────────────────────────────────────────────────────

class SimulationEngine:
    """
    MARG Digital Twin — NDLS–CNB Corridor.

    Call sequence:
        engine = SimulationEngine(config)
        engine.build()          # initialise all subsystems
        stats  = engine.run()   # run until sim_end_min
        # inspect engine.metrics, engine.snapshots, engine.state
    """

    def __init__(self, config: Optional[SimulationConfig] = None) -> None:
        self.config   = config or SimulationConfig()
        self.clock    = SimClock(
            start_minutes = self.config.sim_start_min,
            acceleration  = self.config.acceleration,
        )
        self.state    = StateManager()
        self.metrics  = MetricsCollector()
        self.snapshots = SnapshotRing(capacity=self.config.snapshot_capacity)

        self._des: Optional[EventEngine] = None
        self._built = False

    # ── Setup ─────────────────────────────────────────────────────────────────

    def build(self) -> None:
        """Initialise all subsystems in dependency order."""
        logger.info("SimulationEngine: building '%s'", self.config.scenario_name)
        self._build_sections()
        self._build_stations()
        self._build_scheduler()
        self._build_event_engine()
        self._register_handlers()
        self._schedule_disruptions()
        self._schedule_simulation_end()
        self._built = True
        logger.info(
            "SimulationEngine: ready — trains=%d sections=%d",
            len(self.state.trains), len(self.state.sections),
        )

    def _build_sections(self) -> None:
        for s in _NDLS_CNB_SECTIONS:
            is_pax = True   # use passenger speed for base travel
            spd    = s["pax_spd"]
            base_p = (s["len_km"] / spd) * 60
            base_f = (s["len_km"] / s["frt_spd"]) * 60
            sec = SectionState(
                section_id                    = s["id"],
                from_station                  = s["from"],
                to_station                    = s["to"],
                length_km                     = s["len_km"],
                max_speed_passenger_kmh       = s["pax_spd"],
                max_speed_freight_kmh         = s["frt_spd"],
                theoretical_capacity_per_hour = s["cap"],
                is_single_line                = s["single"],
                base_travel_min_passenger     = base_p,
                base_travel_min_freight       = base_f,
            )
            self.state.register_section(sec)
            self.metrics.register_section(s["id"])

    def _build_stations(self) -> None:
        for sid in _STATION_IDS:
            stn = StationState(
                station_id      = sid,
                name            = _STATION_NAMES.get(sid, sid),
                num_platforms   = 4 if sid in ("NDLS", "CNB", "ALJN", "GZB", "ETW") else 2,
                loop_capacities = {
                    f"{sid}_L1": 750.0,
                    f"{sid}_L2": 750.0,
                } if sid not in ("NDLS", "CNB") else {},
            )
            self.state.register_station(stn)

    def _build_scheduler(self) -> None:
        scheduler = TrainScheduler(
            NDLS_CNB_TIMETABLE,
            start_after_min = self.config.sim_start_min - 1,
        )
        trains = scheduler.build_trains()
        for train in trains.values():
            self.state.register_train(train)
            self.metrics.register_train(
                train.train_id, train.train_name,
                train.category, train.priority,
            )
        self._initial_events = scheduler.build_initial_events()
        logger.info("Scheduler loaded %d trains", len(trains))

    def _build_event_engine(self) -> None:
        self._des = EventEngine(
            clock           = self.clock,
            tick_interval_min = self.config.tick_interval,
            on_tick         = self._on_tick,
        )
        self._des.schedule_many(self._initial_events)
        # Seed the first TICK event so the tick chain starts
        if self.config.tick_interval > 0:
            from services.simulation.core.event_types import TickPayload
            first_tick_time = self.config.sim_start_min + self.config.tick_interval
            self._des.schedule(make_event(
                EventType.TICK,
                first_tick_time,
                TickPayload(tick_number=1, sim_time_min=first_tick_time),
            ))

    def _register_handlers(self) -> None:
        reg = self._des.register
        reg(EventType.TRAIN_DEPART,       self._handle_depart)
        reg(EventType.TRAIN_ARRIVE,       self._handle_arrive)
        reg(EventType.TRAIN_HOLD,         self._handle_hold)
        reg(EventType.TRAIN_RELEASE,      self._handle_release)
        reg(EventType.TRAIN_ENTER_LOOP,   self._handle_enter_loop)
        reg(EventType.TRAIN_EXIT_LOOP,    self._handle_exit_loop)
        reg(EventType.SIGNAL_FAIL,        self._handle_signal_fail)
        reg(EventType.SIGNAL_RESTORE,     self._handle_signal_restore)
        reg(EventType.TRACK_BLOCK,        self._handle_track_block)
        reg(EventType.TRACK_CLEAR,        self._handle_track_clear)
        reg(EventType.WEATHER_UPDATE,     self._handle_weather)

    def _schedule_disruptions(self) -> None:
        cfg = self.config
        all_section_ids = list(self.state.sections.keys())

        if cfg.enable_fog:
            up_secs = [s for s in all_section_ids if s.endswith("_UP")]
            ctrl = ndls_cnb_morning_fog_scenario(up_secs)
            self._des.schedule_many(ctrl.generate_events())

        if cfg.enable_blockage:
            self._des.schedule_many(tundla_blockage())

        if cfg.enable_signal_fail:
            self._des.schedule_many(etawah_signal_failure())

    def _schedule_simulation_end(self) -> None:
        from services.simulation.core.event_types import EventPriority
        end_event = make_event(
            EventType.SIMULATION_END,
            self.config.sim_end_min,
            payload=None,
        )
        self._des.schedule(end_event)

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self, wall_timeout_seconds: Optional[float] = None) -> EngineStats:
        if not self._built:
            raise RuntimeError("Call build() before run()")
        logger.info(
            "SimulationEngine: running %.1f → %.1f sim-minutes",
            self.config.sim_start_min, self.config.sim_end_min,
        )
        stats = self._des.run(
            until_sim_time       = self.config.sim_end_min,
            wall_timeout_seconds = wall_timeout_seconds,
        )
        logger.info(
            "SimulationEngine: done — events=%d",
            stats.events_processed,
        )
        return stats

    def stop(self) -> None:
        if self._des:
            self._des.stop()

    # ── Tick callback ─────────────────────────────────────────────────────────

    def _on_tick(self, sim_time: float) -> None:
        """Called once per tick_interval sim-minutes."""
        snap = self.state.snapshot(sim_time)
        self.snapshots.push(sim_time, snap)

        summary = snap["summary"]
        self.metrics.record_tick(
            sim_time           = sim_time,
            active_trains      = summary["active_trains"],
            total_delay_min    = summary["total_delay_minutes"],
            congested_sections = summary["congested_sections"],
            blocked_sections   = summary["blocked_sections"],
        )
        # Record per-section congestion samples
        for sid, sec_dict in snap["sections"].items():
            self.metrics.record_section_tick(sid, sec_dict.get("congestion_score", 0.0))

    # ── Event handlers ────────────────────────────────────────────────────────

    def _resolve_next_hop(self, from_station: str, timetable_dest: str) -> Optional[str]:
        """
        Return the adjacent station the train should travel to NEXT on the
        way from *from_station* toward *timetable_dest*.
        Returns None if routing is impossible.
        """
        hops = _adjacent_hops(from_station, timetable_dest)
        if len(hops) < 2:
            return None
        return hops[1]   # first station after from_station

    def _handle_depart(self, engine: EventEngine, event: Event) -> None:
        p: DepartPayload = event.payload
        sim_time = event.sim_time
        train_id = p.train_id

        # Resolve the immediate adjacent hop
        # p.to_station may be a non-adjacent timetable stop
        next_adjacent = p.next_hop if p.next_hop else p.to_station
        if next_adjacent != p.to_station:
            # Already resolved; use it directly
            pass
        else:
            # Try to find direct section; if not, resolve via corridor routing
            resolved = self._resolve_next_hop(p.from_station, p.to_station)
            if resolved is None:
                logger.warning(
                    "DEPART  train=%s: cannot route %s→%s — dropping",
                    train_id, p.from_station, p.to_station,
                )
                return
            next_adjacent = resolved

        # Find the adjacent section
        section = self.state.find_section(p.from_station, next_adjacent)
        if section is None:
            logger.warning(
                "DEPART  train=%s: no section %s→%s — dropping",
                train_id, p.from_station, next_adjacent,
            )
            return

        # Check headway
        if not section.headway_satisfied(sim_time):
            wait = section.time_until_headway_clear(sim_time)
            retry_time = sim_time + wait + 0.5
            engine.schedule(make_event(EventType.TRAIN_DEPART, retry_time, p))
            self.state.add_delay_to_train(train_id, wait + 0.5, "headway")
            return

        # Check blockage
        if section.condition == SectionCondition.BLOCKED:
            engine.schedule(make_event(EventType.TRAIN_DEPART, sim_time + 5, p))
            self.state.add_delay_to_train(train_id, 5, f"blocked:{section.section_id}")
            return

        # Mutate state
        try:
            self.state.depart_train(
                train_id     = train_id,
                from_station = p.from_station,
                to_station   = next_adjacent,
                section_id   = section.section_id,
                sim_time     = sim_time,
                is_origin    = p.is_origin,
            )
        except StateError as exc:
            logger.warning("DEPART state error: %s", exc)
            return

        # Schedule arrival at the adjacent station
        train      = self.state.get_train(train_id)
        travel_min = section.effective_travel_min(
            is_passenger = train.category != "goods"
        )
        arrive_time = sim_time + travel_min

        from services.simulation.handlers import ArrivePayload
        # Is next_adjacent a timetable stop for this train?
        timetable_stop_ids = {s.station_id for s in train.stops}
        is_timetable_stop = next_adjacent in timetable_stop_ids
        is_terminus       = (next_adjacent == train.terminus_station)

        arrive_payload = ArrivePayload(
            train_id      = train_id,
            at_station    = next_adjacent,
            section_id    = section.section_id,
            is_terminus   = is_terminus,
        )
        engine.schedule(make_event(EventType.TRAIN_ARRIVE, arrive_time, arrive_payload))

    def _handle_arrive(self, engine: EventEngine, event: Event) -> None:
        from services.simulation.handlers import ArrivePayload
        p: ArrivePayload = event.payload
        sim_time  = event.sim_time
        train_id  = p.train_id

        train = self.state.get_train(train_id)
        timetable_stop_ids = {s.station_id for s in train.stops}
        is_timetable_stop  = p.at_station in timetable_stop_ids

        try:
            self.state.arrive_train(
                train_id    = train_id,
                at_station  = p.at_station,
                section_id  = p.section_id,
                sim_time    = sim_time,
                is_terminus = p.is_terminus,
            )
        except StateError as exc:
            logger.warning("ARRIVE state error: %s", exc)
            return

        if is_timetable_stop:
            self.metrics.record_arrival(train_id, p.at_station, train.current_delay_min)

        if p.is_terminus:
            return

        # Find the next timetable destination
        next_stop = train.next_scheduled_stop
        if next_stop is None:
            return

        if is_timetable_stop:
            # Normal dwell at a timetable stop
            current_stop = train.stops[train._stop_index - 1]
            sched_dwell  = current_stop.scheduled_depart - current_stop.scheduled_arrive
            actual_dwell = max(sched_dwell - max(0, train.current_delay_min * 0.5), 2.0)
            depart_time  = sim_time + actual_dwell
        else:
            # Pass-through intermediate station — depart immediately
            depart_time = sim_time + 0.1

        depart_payload = DepartPayload(
            train_id     = train_id,
            from_station = p.at_station,
            to_station   = next_stop.station_id,
            is_origin    = False,
            is_passthrough = not is_timetable_stop,
        )
        engine.schedule(make_event(EventType.TRAIN_DEPART, depart_time, depart_payload))

    def _handle_hold(self, engine: EventEngine, event: Event) -> None:
        p = event.payload
        try:
            self.state.hold_train(p.train_id, p.at_station, p.reason, event.sim_time)
        except StateError as exc:
            logger.warning("HOLD state error: %s", exc)
        self.metrics.record_hold_start(p.train_id, event.sim_time, p.reason)

    def _handle_release(self, engine: EventEngine, event: Event) -> None:
        p = event.payload
        try:
            self.state.release_train(p.train_id, p.at_station, event.sim_time)
        except StateError as exc:
            logger.warning("RELEASE state error: %s", exc)
        self.metrics.record_hold_end(p.train_id, event.sim_time)

    def _handle_enter_loop(self, engine: EventEngine, event: Event) -> None:
        p = event.payload
        try:
            self.state.enter_loop(p.train_id, p.at_station, p.loop_id, event.sim_time)
        except (StateError, RuntimeError) as exc:
            logger.warning("ENTER_LOOP state error: %s", exc)
        self.metrics.record_loop_start(p.train_id, event.sim_time)

    def _handle_exit_loop(self, engine: EventEngine, event: Event) -> None:
        p = event.payload
        try:
            self.state.exit_loop(p.train_id, p.at_station, p.loop_id, event.sim_time)
        except StateError as exc:
            logger.warning("EXIT_LOOP state error: %s", exc)
        self.metrics.record_loop_end(p.train_id, event.sim_time)

    def _handle_signal_fail(self, engine: EventEngine, event: Event) -> None:
        p: SignalFailPayload = event.payload
        self.state.apply_signal_failure(p.section_id, p.restore_time)
        self.metrics.record_disruption("signal_fail", p.section_id, event.sim_time)
        logger.info("SIGNAL_FAIL  section=%s restore=%.1f", p.section_id, p.restore_time)

    def _handle_signal_restore(self, engine: EventEngine, event: Event) -> None:
        p: SignalRestorePayload = event.payload
        self.state.restore_signal(p.section_id)
        logger.info("SIGNAL_RESTORE section=%s", p.section_id)

    def _handle_track_block(self, engine: EventEngine, event: Event) -> None:
        p: TrackBlockPayload = event.payload
        self.state.apply_blockage(p.section_id)
        self.metrics.record_disruption("blockage", p.section_id, event.sim_time)
        logger.info("TRACK_BLOCK  section=%s type=%s clear=%.1f",
                    p.section_id, p.blockage_type, p.clear_time)

    def _handle_track_clear(self, engine: EventEngine, event: Event) -> None:
        p: TrackClearPayload = event.payload
        self.state.clear_blockage(p.section_id)
        logger.info("TRACK_CLEAR  section=%s", p.section_id)

    def _handle_weather(self, engine: EventEngine, event: Event) -> None:
        p: WeatherUpdatePayload = event.payload
        if p.section_ids:
            for sid in p.section_ids:
                try:
                    self.state.apply_weather_to_section(sid, p.speed_factor)
                except StateError:
                    pass
        else:
            self.state.apply_weather_to_all_sections(p.speed_factor)
        self.metrics.record_disruption("weather", "ALL", event.sim_time)
        logger.info("WEATHER  condition=%s factor=%.2f", p.condition.name, p.speed_factor)

    def current_snapshot(self) -> Optional[dict]:
        snap = self.snapshots.latest()
        return snap.state if snap else None

    def __repr__(self) -> str:
        return (
            f"SimulationEngine(scenario='{self.config.scenario_name}' "
            f"built={self._built})"
        )
