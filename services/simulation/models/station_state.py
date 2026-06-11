"""
Station State
=============
Runtime occupancy and queue state for a single station.
Tracks which trains are present, loop utilisation, and the hold queue.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class LoopOccupancy:
    """Tracks which train (if any) is occupying a crossing loop."""
    loop_id: str
    length_m: float
    occupied_by: Optional[str] = None    # train_id
    since_sim_min: Optional[float] = None

    @property
    def is_free(self) -> bool:
        return self.occupied_by is None

    def occupy(self, train_id: str, sim_time: float) -> None:
        if not self.is_free:
            raise RuntimeError(
                f"Loop {self.loop_id} already occupied by {self.occupied_by}"
            )
        self.occupied_by = train_id
        self.since_sim_min = sim_time

    def vacate(self) -> Optional[str]:
        train = self.occupied_by
        self.occupied_by = None
        self.since_sim_min = None
        return train


@dataclass
class StationState:
    """
    Mutable runtime state for one station.

    Parameters
    ----------
    station_id:
        Station code (e.g. 'ALJN').
    name:
        Human-readable name.
    num_platforms:
        Total platforms (main + loop).
    loop_capacities:
        Mapping of loop_id → length in metres.
    """

    station_id:       str
    name:             str
    num_platforms:    int
    loop_capacities:  dict[str, float] = field(default_factory=dict)

    # ── Runtime fields ────────────────────────────────────────────────────────

    # Trains currently AT the station (on main platforms, not in loops)
    trains_present:   set[str] = field(default_factory=set, init=False)

    # Crossing loops and their occupancy
    loops: dict[str, LoopOccupancy] = field(default_factory=dict, init=False)

    # Queue of trains waiting to depart (in order)
    departure_queue: deque[str] = field(default_factory=deque, init=False)

    # Trains held at this station by signal or crossing constraint
    held_trains: dict[str, str] = field(  # train_id → reason
        default_factory=dict, init=False
    )

    # Counters
    total_arrivals:   int = field(default=0, init=False)
    total_departures: int = field(default=0, init=False)
    total_holds:      int = field(default=0, init=False)

    def __post_init__(self) -> None:
        for loop_id, length in self.loop_capacities.items():
            self.loops[loop_id] = LoopOccupancy(loop_id=loop_id, length_m=length)

    # ── Arrival / departure ───────────────────────────────────────────────────

    def train_arrives(self, train_id: str, sim_time: float) -> None:
        self.trains_present.add(train_id)
        self.total_arrivals += 1
        logger.debug("Station %s: train %s arrived (t=%.1f)", self.station_id, train_id, sim_time)

    def train_departs(self, train_id: str, sim_time: float) -> None:
        self.trains_present.discard(train_id)
        if train_id in self.departure_queue:
            # deque doesn't support O(1) removal by value; rebuild
            self.departure_queue = deque(
                t for t in self.departure_queue if t != train_id
            )
        self.held_trains.pop(train_id, None)
        self.total_departures += 1
        logger.debug("Station %s: train %s departed (t=%.1f)", self.station_id, train_id, sim_time)

    def enqueue_departure(self, train_id: str) -> None:
        """Add a train to the departure queue (FIFO within same priority)."""
        if train_id not in self.departure_queue:
            self.departure_queue.append(train_id)

    def next_to_depart(self) -> Optional[str]:
        """Return the next train_id in the departure queue without consuming."""
        return self.departure_queue[0] if self.departure_queue else None

    # ── Holds ─────────────────────────────────────────────────────────────────

    def hold_train(self, train_id: str, reason: str) -> None:
        self.held_trains[train_id] = reason
        self.total_holds += 1
        logger.debug(
            "Station %s: train %s HELD (%s)", self.station_id, train_id, reason
        )

    def release_train(self, train_id: str) -> bool:
        """Returns True if the train was held and has been released."""
        return self.held_trains.pop(train_id, None) is not None

    # ── Loop management ───────────────────────────────────────────────────────

    def best_free_loop(self, train_length_m: float) -> Optional[str]:
        """
        Return the loop_id of the shortest adequate free loop,
        or None if no loop can accommodate this train.
        """
        candidates = [
            lp for lp in self.loops.values()
            if lp.is_free and lp.length_m >= train_length_m
        ]
        if not candidates:
            return None
        # Prefer shortest adequate loop (pack loops efficiently)
        return min(candidates, key=lambda lp: lp.length_m).loop_id

    def occupy_loop(self, loop_id: str, train_id: str, sim_time: float) -> None:
        self.loops[loop_id].occupy(train_id, sim_time)

    def vacate_loop(self, loop_id: str) -> Optional[str]:
        return self.loops[loop_id].vacate()

    def num_free_loops(self) -> int:
        return sum(1 for lp in self.loops.values() if lp.is_free)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "station_id":       self.station_id,
            "name":             self.name,
            "trains_present":   list(self.trains_present),
            "held_trains":      dict(self.held_trains),
            "departure_queue":  list(self.departure_queue),
            "loops": {
                lid: {
                    "length_m":    lp.length_m,
                    "occupied_by": lp.occupied_by,
                    "since":       lp.since_sim_min,
                }
                for lid, lp in self.loops.items()
            },
            "total_arrivals":   self.total_arrivals,
            "total_departures": self.total_departures,
            "total_holds":      self.total_holds,
        }

    def __repr__(self) -> str:
        return (
            f"StationState({self.station_id} "
            f"present={len(self.trains_present)} "
            f"held={len(self.held_trains)} "
            f"free_loops={self.num_free_loops()})"
        )
