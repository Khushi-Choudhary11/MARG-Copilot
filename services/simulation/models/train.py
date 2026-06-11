"""
Train Model
===========
Represents the mutable runtime state of a single train as it moves through
the corridor.  Implements a formal state machine with valid transition guards.

State machine
-------------

    SCHEDULED
        │ TRAIN_DEPART (origin)
        ▼
    EN_ROUTE ──── TRAIN_HOLD ──► HELD_SIGNAL
        │               │             │ TRAIN_RELEASE
        │               └─ CROSSING──► LOOPED
        │                             │ TRAIN_EXIT_LOOP
        │◄────────────────────────────┘
        │ TRAIN_ARRIVE
        ▼
    AT_STATION
        │ TRAIN_DEPART (intermediate)
        ▼
    EN_ROUTE  (repeats until terminus)
        │ TRAIN_ARRIVE (terminus)
        ▼
    TERMINATED
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

logger = logging.getLogger(__name__)


class TrainStatus(Enum):
    SCHEDULED    = auto()   # Not yet departed origin
    EN_ROUTE     = auto()   # Moving between two stations
    AT_STATION   = auto()   # Stopped at an intermediate station
    HELD_SIGNAL  = auto()   # Halted at a signal
    LOOPED       = auto()   # Waiting in a crossing loop
    TERMINATED   = auto()   # Reached terminus / cancelled


# Valid transitions: current → set of allowed next states
_VALID_TRANSITIONS: dict[TrainStatus, set[TrainStatus]] = {
    TrainStatus.SCHEDULED:   {TrainStatus.EN_ROUTE},
    TrainStatus.EN_ROUTE:    {TrainStatus.AT_STATION, TrainStatus.HELD_SIGNAL,
                               TrainStatus.LOOPED, TrainStatus.TERMINATED},
    TrainStatus.AT_STATION:  {TrainStatus.EN_ROUTE, TrainStatus.TERMINATED},
    TrainStatus.HELD_SIGNAL: {TrainStatus.EN_ROUTE, TrainStatus.LOOPED},
    TrainStatus.LOOPED:      {TrainStatus.EN_ROUTE},
    TrainStatus.TERMINATED:  set(),
}


@dataclass
class StopRecord:
    """Immutable record of one station visit."""
    station_id: str
    scheduled_arrive: float       # min-since-midnight
    scheduled_depart: float
    actual_arrive:    Optional[float] = None
    actual_depart:    Optional[float] = None

    @property
    def arrive_delay(self) -> Optional[float]:
        if self.actual_arrive is None:
            return None
        return self.actual_arrive - self.scheduled_arrive

    @property
    def depart_delay(self) -> Optional[float]:
        if self.actual_depart is None:
            return None
        return self.actual_depart - self.scheduled_depart


@dataclass
class Train:
    """
    Mutable runtime state of a single train.

    Parameters
    ----------
    train_id:
        Unique identifier (e.g. '12301' for Howrah Rajdhani).
    train_name:
        Human-readable name.
    category:
        'superfast' | 'mail' | 'passenger' | 'goods'
    priority:
        0 = highest (Rajdhani), 4 = lowest (goods).
    origin_station:
        Station ID where the train starts.
    terminus_station:
        Station ID where the train ends.
    stops:
        Ordered list of all scheduled stops (including origin and terminus).
    length_m:
        Train length in metres (used for loop suitability check).
    max_speed_kmh:
        Train's maximum operating speed (may be less than section limit).
    requires_electrification:
        Whether the train needs an electrified loop.
    """

    train_id:               str
    train_name:             str
    category:               str
    priority:               int
    origin_station:         str
    terminus_station:       str
    stops:                  list[StopRecord]
    length_m:               float
    max_speed_kmh:          float
    requires_electrification: bool = True

    # ── Runtime state (mutable) ───────────────────────────────────────────────
    status: TrainStatus = field(default=TrainStatus.SCHEDULED, init=False)

    current_station:        Optional[str] = field(default=None, init=False)
    next_station:           Optional[str] = field(default=None, init=False)
    current_section:        Optional[str] = field(default=None, init=False)

    # How many minutes behind schedule the train currently is
    current_delay_min:      float = field(default=0.0, init=False)
    total_delay_accumulated: float = field(default=0.0, init=False)

    # Stop pointer: index into self.stops for the NEXT stop to be served
    _stop_index: int = field(default=0, init=False, repr=False)

    # History log
    _status_log:   list[tuple[float, TrainStatus]] = field(
        default_factory=list, init=False, repr=False
    )
    _hold_reasons: list[str] = field(default_factory=list, init=False, repr=False)

    # ── State machine ─────────────────────────────────────────────────────────

    def transition(self, new_status: TrainStatus, sim_time: float) -> None:
        """
        Move the train to a new status, enforcing valid transition rules.
        Raises ValueError on invalid transitions.
        """
        allowed = _VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Train {self.train_id}: invalid transition "
                f"{self.status.name} → {new_status.name}"
            )
        logger.debug(
            "Train %s: %s → %s at %.1f",
            self.train_id, self.status.name, new_status.name, sim_time,
        )
        self._status_log.append((sim_time, new_status))
        self.status = new_status

    # ── Stop navigation ───────────────────────────────────────────────────────

    @property
    def next_scheduled_stop(self) -> Optional[StopRecord]:
        """The next stop the train should serve (None if terminated)."""
        if self._stop_index < len(self.stops):
            return self.stops[self._stop_index]
        return None

    @property
    def current_stop_record(self) -> Optional[StopRecord]:
        """Stop record for the station the train is currently AT."""
        idx = self._stop_index - 1
        if 0 <= idx < len(self.stops):
            return self.stops[idx]
        return None

    def advance_stop(self) -> Optional[StopRecord]:
        """
        Advance the stop pointer.  Called when the train departs a station.
        Returns the next scheduled stop, or None if the train has terminated.
        """
        self._stop_index += 1
        return self.next_scheduled_stop

    def record_arrival(self, station_id: str, actual_time: float) -> None:
        """Record actual arrival time for the current stop."""
        stop = self.next_scheduled_stop
        if stop and stop.station_id == station_id:
            stop.actual_arrive = actual_time
            self.current_delay_min = actual_time - stop.scheduled_arrive
            if self.current_delay_min > 0:
                self.total_delay_accumulated += self.current_delay_min
            logger.debug(
                "Train %s arrived %s: delay=%.1fmin",
                self.train_id, station_id, self.current_delay_min,
            )

    def record_departure(self, station_id: str, actual_time: float) -> None:
        """Record actual departure time for the current stop."""
        stop = self.next_scheduled_stop
        if stop and stop.station_id == station_id:
            stop.actual_depart = actual_time
            depart_delay = actual_time - stop.scheduled_depart
            self.current_delay_min = max(self.current_delay_min, depart_delay)
        self._stop_index += 1

    # ── Delay management ─────────────────────────────────────────────────────

    def add_delay(self, minutes: float, reason: str = "") -> None:
        """Accumulate additional delay on this train."""
        self.current_delay_min += minutes
        self.total_delay_accumulated += minutes
        if reason:
            self._hold_reasons.append(f"+{minutes:.1f}min: {reason}")
        logger.debug(
            "Train %s: +%.1fmin delay (%s) → total=%.1fmin",
            self.train_id, minutes, reason, self.current_delay_min,
        )

    def clear_delay(self) -> None:
        """Reset running delay (e.g. after recovery stop)."""
        self.current_delay_min = 0.0

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self.status not in (TrainStatus.SCHEDULED, TrainStatus.TERMINATED)

    @property
    def is_moving(self) -> bool:
        return self.status == TrainStatus.EN_ROUTE

    @property
    def is_delayed(self) -> bool:
        return self.current_delay_min > 0

    @property
    def on_time_performance(self) -> float:
        """Fraction of stops served on time (delay <= 5 min). 0.0–1.0."""
        served = [s for s in self.stops if s.actual_arrive is not None]
        if not served:
            return 1.0
        on_time = sum(1 for s in served if (s.arrive_delay or 0) <= 5.0)
        return on_time / len(served)

    def to_dict(self) -> dict:
        """Serialise to dict for WebSocket / Redis publication."""
        next_stop = self.next_scheduled_stop
        return {
            "train_id":           self.train_id,
            "train_name":         self.train_name,
            "category":           self.category,
            "priority":           self.priority,
            "status":             self.status.name,
            "current_station":    self.current_station,
            "next_station":       self.next_station,
            "current_section":    self.current_section,
            "current_delay_min":  round(self.current_delay_min, 1),
            "total_delay_min":    round(self.total_delay_accumulated, 1),
            "otp":                round(self.on_time_performance, 3),
            "next_stop":          next_stop.station_id if next_stop else None,
            "length_m":           self.length_m,
        }

    def __repr__(self) -> str:
        return (
            f"Train({self.train_id} {self.train_name} "
            f"[{self.status.name}] delay={self.current_delay_min:.1f}min)"
        )
