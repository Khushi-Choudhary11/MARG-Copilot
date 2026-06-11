"""
State Manager
=============
Single source of truth for all runtime state in the simulation.
Owns the Train, StationState, and SectionState registries and
provides the authoritative lookup / mutation interface that event
handlers call.

Design principle: handlers never own state; they call StateManager
methods, which validate and apply mutations atomically.
"""

from __future__ import annotations

import logging
from typing import Optional

from services.simulation.models.section_state import SectionCondition, SectionState
from services.simulation.models.station_state import StationState
from services.simulation.models.train import Train, TrainStatus

logger = logging.getLogger(__name__)


class StateError(Exception):
    """Raised when a state mutation is invalid."""


class StateManager:
    """
    Manages all mutable simulation state.

    After construction, call:
        register_train(train)
        register_station(station_state)
        register_section(section_state)
    for every entity in the simulation before running the engine.
    """

    def __init__(self) -> None:
        self._trains:   dict[str, Train]         = {}
        self._stations: dict[str, StationState]  = {}
        self._sections: dict[str, SectionState]  = {}

        # Derived index: station_id → list of section_ids departing from it
        self._outgoing: dict[str, list[str]] = {}
        # station_id → list of section_ids arriving at it
        self._incoming: dict[str, list[str]] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register_train(self, train: Train) -> None:
        if train.train_id in self._trains:
            raise StateError(f"Train '{train.train_id}' already registered.")
        self._trains[train.train_id] = train

    def register_station(self, station: StationState) -> None:
        if station.station_id in self._stations:
            raise StateError(f"Station '{station.station_id}' already registered.")
        self._stations[station.station_id] = station

    def register_section(self, section: SectionState) -> None:
        if section.section_id in self._sections:
            raise StateError(f"Section '{section.section_id}' already registered.")
        self._sections[section.section_id] = section
        self._outgoing.setdefault(section.from_station, []).append(section.section_id)
        self._incoming.setdefault(section.to_station,   []).append(section.section_id)

    # ── Lookups ───────────────────────────────────────────────────────────────

    def get_train(self, train_id: str) -> Train:
        try:
            return self._trains[train_id]
        except KeyError:
            raise StateError(f"Unknown train '{train_id}'")

    def get_station(self, station_id: str) -> StationState:
        try:
            return self._stations[station_id]
        except KeyError:
            raise StateError(f"Unknown station '{station_id}'")

    def get_section(self, section_id: str) -> SectionState:
        try:
            return self._sections[section_id]
        except KeyError:
            raise StateError(f"Unknown section '{section_id}'")

    def find_section(self, from_station: str, to_station: str) -> Optional[SectionState]:
        """Return the section connecting two adjacent stations, or None."""
        for sid in self._outgoing.get(from_station, []):
            sec = self._sections[sid]
            if sec.to_station == to_station:
                return sec
        return None

    @property
    def trains(self)   -> dict[str, Train]:        return dict(self._trains)
    @property
    def stations(self) -> dict[str, StationState]: return dict(self._stations)
    @property
    def sections(self) -> dict[str, SectionState]: return dict(self._sections)

    # ── Train mutations ───────────────────────────────────────────────────────

    def depart_train(
        self,
        train_id:     str,
        from_station: str,
        to_station:   str,
        section_id:   str,
        sim_time:     float,
        is_origin:    bool = False,
    ) -> None:
        """
        Move a train out of *from_station* and onto *section_id*.
        Handles state machine transitions, station queue, and section entry.
        """
        train   = self.get_train(train_id)
        station = self.get_station(from_station)
        section = self.get_section(section_id)

        # Guard: headway check
        if not section.headway_satisfied(sim_time):
            wait = section.time_until_headway_clear(sim_time)
            raise StateError(
                f"Headway not satisfied on {section_id}: "
                f"wait {wait:.1f} more minutes"
            )

        # Guard: section passable
        if section.condition == SectionCondition.BLOCKED:
            raise StateError(f"Section {section_id} is BLOCKED — cannot depart {train_id}")

        # State machine
        if is_origin:
            train.transition(TrainStatus.EN_ROUTE, sim_time)
        else:
            train.transition(TrainStatus.EN_ROUTE, sim_time)

        # Update train pointers
        train.current_station = None
        train.next_station    = to_station
        train.current_section = section_id

        # Record departure on stop record
        train.record_departure(from_station, sim_time)

        # Station: remove from platform, remove hold, dequeue
        station.train_departs(train_id, sim_time)

        # Section: log entry
        section.train_enters(train_id, sim_time)

        logger.info(
            "DEPART  train=%-7s %s → %s via %-20s delay=%.1fmin",
            train_id, from_station, to_station, section_id, train.current_delay_min,
        )

    def arrive_train(
        self,
        train_id:     str,
        at_station:   str,
        section_id:   str,
        sim_time:     float,
        is_terminus:  bool = False,
    ) -> None:
        """
        Move a train off *section_id* and into *at_station*.
        """
        train   = self.get_train(train_id)
        station = self.get_station(at_station)
        section = self.get_section(section_id)

        # Update section: train has exited
        section.train_exits(train_id)

        # Update train pointers
        train.current_section = None
        train.current_station = at_station
        train.next_station    = None

        # Record arrival
        train.record_arrival(at_station, sim_time)

        # State machine
        new_status = TrainStatus.TERMINATED if is_terminus else TrainStatus.AT_STATION
        train.transition(new_status, sim_time)

        # Station: log arrival, enqueue for departure (unless terminus)
        station.train_arrives(train_id, sim_time)
        if not is_terminus:
            station.enqueue_departure(train_id)

        logger.info(
            "ARRIVE  train=%-7s at %-5s  via %-20s delay=%.1fmin  %s",
            train_id, at_station, section_id, train.current_delay_min,
            "TERMINUS" if is_terminus else "",
        )

    def hold_train(self, train_id: str, at_station: str, reason: str, sim_time: float) -> None:
        train   = self.get_train(train_id)
        station = self.get_station(at_station)
        train.transition(TrainStatus.HELD_SIGNAL, sim_time)
        station.hold_train(train_id, reason)
        train.add_delay(0, reason=reason)   # mark reason; actual delay added when released

    def release_train(self, train_id: str, at_station: str, sim_time: float) -> None:
        train   = self.get_train(train_id)
        station = self.get_station(at_station)
        train.transition(TrainStatus.AT_STATION, sim_time)
        station.release_train(train_id)

    def enter_loop(
        self,
        train_id:   str,
        at_station: str,
        loop_id:    str,
        sim_time:   float,
    ) -> None:
        train   = self.get_train(train_id)
        station = self.get_station(at_station)
        train.transition(TrainStatus.LOOPED, sim_time)
        station.occupy_loop(loop_id, train_id, sim_time)
        logger.info("LOOP_IN  train=%s station=%s loop=%s", train_id, at_station, loop_id)

    def exit_loop(
        self,
        train_id:   str,
        at_station: str,
        loop_id:    str,
        sim_time:   float,
    ) -> None:
        train   = self.get_train(train_id)
        station = self.get_station(at_station)
        train.transition(TrainStatus.AT_STATION, sim_time)
        station.vacate_loop(loop_id)
        logger.info("LOOP_OUT train=%s station=%s loop=%s", train_id, at_station, loop_id)

    def add_delay_to_train(self, train_id: str, minutes: float, reason: str) -> None:
        self.get_train(train_id).add_delay(minutes, reason)

    # ── Section disruptions ───────────────────────────────────────────────────

    def apply_signal_failure(self, section_id: str, restore_time: float) -> None:
        self.get_section(section_id).apply_signal_failure(restore_time)

    def restore_signal(self, section_id: str) -> None:
        self.get_section(section_id).restore_signal()

    def apply_blockage(self, section_id: str) -> None:
        self.get_section(section_id).apply_blockage()

    def clear_blockage(self, section_id: str) -> None:
        self.get_section(section_id).clear_blockage()

    def apply_weather_to_section(self, section_id: str, speed_factor: float) -> None:
        self.get_section(section_id).apply_weather(speed_factor)

    def apply_weather_to_all_sections(self, speed_factor: float) -> None:
        for sec in self._sections.values():
            sec.apply_weather(speed_factor)

    # ── Aggregated queries ────────────────────────────────────────────────────

    def active_trains(self) -> list[Train]:
        return [t for t in self._trains.values() if t.is_active]

    def delayed_trains(self, threshold_min: float = 5.0) -> list[Train]:
        return [
            t for t in self._trains.values()
            if t.current_delay_min > threshold_min
        ]

    def congested_sections(self) -> list[SectionState]:
        return [
            s for s in self._sections.values()
            if s.condition == SectionCondition.CONGESTED
        ]

    def blocked_sections(self) -> list[SectionState]:
        return [
            s for s in self._sections.values()
            if s.condition == SectionCondition.BLOCKED
        ]

    def total_delay_minutes(self) -> float:
        return sum(t.current_delay_min for t in self._trains.values())

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(self, sim_time: float) -> dict:
        """
        Return a serialisable snapshot of the entire simulation state.
        Used by the WebSocket publisher and the metrics recorder.
        """
        return {
            "sim_time":  sim_time,
            "trains":    {tid: t.to_dict()  for tid, t in self._trains.items()},
            "stations":  {sid: s.to_dict()  for sid, s in self._stations.items()},
            "sections":  {sid: s.to_dict()  for sid, s in self._sections.items()},
            "summary": {
                "active_trains":       len(self.active_trains()),
                "total_delay_minutes": round(self.total_delay_minutes(), 1),
                "congested_sections":  len(self.congested_sections()),
                "blocked_sections":    len(self.blocked_sections()),
            },
        }

    def __repr__(self) -> str:
        return (
            f"StateManager("
            f"trains={len(self._trains)} "
            f"stations={len(self._stations)} "
            f"sections={len(self._sections)})"
        )
