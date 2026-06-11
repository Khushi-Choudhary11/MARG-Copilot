"""
Simulation Event Types
======================
Every state change in the digital twin is represented as an immutable Event.
The DES event engine processes events in strict time order.

Design
------
- Events are frozen dataclasses (immutable once created).
- EventType enum is the single discriminator — handlers are registered per type.
- Payload is typed per event using a union of specific payload dataclasses.
- Priority field allows same-timestamp ordering (lower = processed first).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional


# ── Event type discriminator ──────────────────────────────────────────────────

class EventType(Enum):
    # Train lifecycle
    TRAIN_DEPART          = auto()   # Train departs a station
    TRAIN_ARRIVE          = auto()   # Train arrives at next station
    TRAIN_HOLD            = auto()   # Train held at signal (headway / crossing)
    TRAIN_RELEASE         = auto()   # Held train released to proceed
    TRAIN_ENTER_LOOP      = auto()   # Train diverted into crossing loop
    TRAIN_EXIT_LOOP       = auto()   # Train leaves crossing loop

    # Disruptions — injected externally or stochastically
    SIGNAL_FAIL           = auto()   # Signal failure on a section
    SIGNAL_RESTORE        = auto()   # Signal restored after failure
    TRACK_BLOCK           = auto()   # Track blocked (loco failure, landslide, …)
    TRACK_CLEAR           = auto()   # Track blockage cleared
    WEATHER_UPDATE        = auto()   # Weather factor change on section(s)

    # Congestion
    CONGESTION_UPDATE     = auto()   # Section congestion score updated

    # Housekeeping
    TICK                  = auto()   # Periodic snapshot tick (every N sim-minutes)
    SIMULATION_END        = auto()   # Sentinel: stop the event loop


# ── Priority constants (lower = higher priority at same timestamp) ─────────────

class EventPriority(int, Enum):
    """Within the same sim-minute, events fire in priority order."""
    SIMULATION_END   = 0
    TRACK_CLEAR      = 10
    SIGNAL_RESTORE   = 10
    TRAIN_RELEASE    = 20
    TRAIN_EXIT_LOOP  = 25
    TRAIN_DEPART     = 30
    TRAIN_ARRIVE     = 30
    TRAIN_ENTER_LOOP = 35
    TRAIN_HOLD       = 40
    SIGNAL_FAIL      = 50
    TRACK_BLOCK      = 50
    WEATHER_UPDATE   = 60
    CONGESTION_UPDATE= 70
    TICK             = 90
    DEFAULT          = 50


# ── Payload dataclasses ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class TrainDepartPayload:
    train_id: str
    from_station: str
    to_station: str
    section_id: str
    scheduled_depart_min: float    # scheduled departure time (min-since-midnight)
    actual_depart_min: float       # actual (may differ due to delay)


@dataclass(frozen=True)
class TrainArrivePayload:
    train_id: str
    station_id: str
    from_station: str
    section_id: str
    scheduled_arrive_min: float
    actual_arrive_min: float
    travel_time_min: float         # actual travel time on the section


@dataclass(frozen=True)
class TrainHoldPayload:
    train_id: str
    station_id: str                # where the train is being held
    section_id: str                # section it was about to enter
    reason: str                    # "headway" | "crossing" | "signal_fail" | "block"
    hold_duration_min: float       # expected hold time


@dataclass(frozen=True)
class TrainReleasePayload:
    train_id: str
    station_id: str
    section_id: str
    reason: str


@dataclass(frozen=True)
class TrainEnterLoopPayload:
    train_id: str
    station_id: str
    loop_id: str
    wait_for_train_id: str         # oncoming train that gets priority


@dataclass(frozen=True)
class TrainExitLoopPayload:
    train_id: str
    station_id: str
    loop_id: str
    wait_minutes: float            # actual time spent in loop


@dataclass(frozen=True)
class SignalFailPayload:
    section_id: str
    station_id: str                # signal location
    expected_restore_min: float    # when signal is expected to be restored
    severity: str                  # "minor" | "major" | "total"


@dataclass(frozen=True)
class SignalRestorePayload:
    section_id: str
    station_id: str


@dataclass(frozen=True)
class TrackBlockPayload:
    section_id: str
    from_station: str
    to_station: str
    cause: str                     # "loco_failure" | "landslide" | "flood" | "accident"
    expected_clear_min: float
    affects_both_directions: bool = True


@dataclass(frozen=True)
class TrackClearPayload:
    section_id: str
    from_station: str
    to_station: str


@dataclass(frozen=True)
class WeatherUpdatePayload:
    section_ids: tuple[str, ...]   # affected sections
    weather_type: str              # "fog" | "rain" | "clear" | "storm"
    speed_factor: float            # 0.15 (dense fog) … 1.0 (clear)
    visibility_m: int              # visibility in metres


@dataclass(frozen=True)
class CongestionUpdatePayload:
    section_id: str
    congestion_score: float        # 0.0 … 1.0


@dataclass(frozen=True)
class TickPayload:
    tick_number: int
    sim_time_min: float


# ── Core Event ────────────────────────────────────────────────────────────────

@dataclass(frozen=True, order=True)
class Event:
    """
    An immutable simulation event.

    Ordering is by (sim_time, priority, sequence) so the priority queue
    always returns events in deterministic, physically meaningful order.
    """
    sim_time: float                                  # minutes-since-midnight
    priority: int                                    # lower = first at same time
    sequence: int                                    # tie-breaker (monotone counter)

    event_type: EventType   = field(compare=False)
    payload: Any            = field(compare=False)
    event_id: str           = field(compare=False, default_factory=lambda: uuid.uuid4().hex[:8])

    def __repr__(self) -> str:
        from services.simulation.core.clock import SimClock
        t = SimClock.minutes_to_hhmm(self.sim_time)
        return f"Event({t} {self.event_type.name} seq={self.sequence})"


# ── Factory helpers ───────────────────────────────────────────────────────────

_seq_counter: int = 0

def _next_seq() -> int:
    global _seq_counter
    _seq_counter += 1
    return _seq_counter


def make_event(
    event_type: EventType,
    sim_time: float,
    payload: Any,
    priority: Optional[int] = None,
) -> Event:
    """
    Convenience factory that auto-assigns sequence number and default priority.
    """
    if priority is None:
        priority = _PRIORITY_MAP.get(event_type, EventPriority.DEFAULT)
    return Event(
        sim_time=sim_time,
        priority=priority,
        sequence=_next_seq(),
        event_type=event_type,
        payload=payload,
    )


_PRIORITY_MAP: dict[EventType, int] = {
    EventType.SIMULATION_END:   EventPriority.SIMULATION_END,
    EventType.TRACK_CLEAR:      EventPriority.TRACK_CLEAR,
    EventType.SIGNAL_RESTORE:   EventPriority.SIGNAL_RESTORE,
    EventType.TRAIN_RELEASE:    EventPriority.TRAIN_RELEASE,
    EventType.TRAIN_EXIT_LOOP:  EventPriority.TRAIN_EXIT_LOOP,
    EventType.TRAIN_DEPART:     EventPriority.TRAIN_DEPART,
    EventType.TRAIN_ARRIVE:     EventPriority.TRAIN_ARRIVE,
    EventType.TRAIN_ENTER_LOOP: EventPriority.TRAIN_ENTER_LOOP,
    EventType.TRAIN_HOLD:       EventPriority.TRAIN_HOLD,
    EventType.SIGNAL_FAIL:      EventPriority.SIGNAL_FAIL,
    EventType.TRACK_BLOCK:      EventPriority.TRACK_BLOCK,
    EventType.WEATHER_UPDATE:   EventPriority.WEATHER_UPDATE,
    EventType.CONGESTION_UPDATE:EventPriority.CONGESTION_UPDATE,
    EventType.TICK:             EventPriority.TICK,
}
