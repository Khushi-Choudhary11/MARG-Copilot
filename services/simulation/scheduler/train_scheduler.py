"""
Train Scheduler
===============
Reads the Working Timetable and:
  1. Instantiates Train and StopRecord objects for every schedule entry.
  2. Generates the initial TRAIN_DEPART events so the EventEngine can
     fire them at the correct simulation time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from services.simulation.core.event_types import EventType, make_event, Event
from services.simulation.models.train import Train, StopRecord
from services.simulation.scheduler.timetable import ScheduledStop, TrainSchedule

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DepartPayload:
    """Payload for TRAIN_DEPART events."""
    train_id:       str
    from_station:   str
    to_station:     str    # next TIMETABLE stop (may not be adjacent)
    is_origin:      bool
    next_hop:       str  = ""
    is_passthrough: bool = False


class TrainScheduler:
    """Converts TrainSchedule list into Train instances and initial DES events."""

    def __init__(
        self,
        timetable: Sequence[TrainSchedule],
        filter_direction: str | None = None,
        start_after_min: float = 0.0,
    ) -> None:
        self._timetable = [
            s for s in timetable
            if (filter_direction is None or s.direction == filter_direction)
            and s.origin.depart_min >= start_after_min
        ]
        self._trains: dict[str, Train] = {}
        self._events: list[Event] = []
        self._built = False

    @property
    def train_count(self) -> int:
        return len(self._timetable)

    def build_trains(self) -> dict[str, Train]:
        if not self._built:
            self._build()
        return dict(self._trains)

    def build_initial_events(self) -> list[Event]:
        if not self._built:
            self._build()
        return list(self._events)

    def _build(self) -> None:
        self._trains.clear()
        self._events.clear()
        for schedule in self._timetable:
            train = self._make_train(schedule)
            self._trains[train.train_id] = train
            event = self._make_origin_event(schedule)
            self._events.append(event)
            logger.debug(
                "Scheduled train %s '%s' — origin depart %.1fmin, stops=%d",
                schedule.train_id, schedule.train_name,
                schedule.origin.depart_min, len(schedule.stops),
            )
        self._events.sort(key=lambda e: e.sim_time)
        self._built = True
        logger.info(
            "TrainScheduler: loaded %d trains, %d origin events",
            len(self._trains), len(self._events),
        )

    def _make_train(self, s: TrainSchedule) -> Train:
        stop_records = [self._stop_to_record(stop) for stop in s.stops]
        return Train(
            train_id=s.train_id,
            train_name=s.train_name,
            category=s.category,
            priority=s.priority,
            origin_station=s.stops[0].station_id,
            terminus_station=s.stops[-1].station_id,
            stops=stop_records,
            length_m=s.length_m,
            max_speed_kmh=s.max_speed_kmh,
            requires_electrification=s.requires_elec,
        )

    @staticmethod
    def _stop_to_record(stop: ScheduledStop) -> StopRecord:
        return StopRecord(
            station_id=stop.station_id,
            scheduled_arrive=stop.arrive_min,
            scheduled_depart=stop.depart_min,
        )

    @staticmethod
    def _make_origin_event(s: TrainSchedule) -> Event:
        stops = s.stops
        origin = stops[0]
        next_stn = stops[1].station_id if len(stops) > 1 else origin.station_id
        payload = DepartPayload(
            train_id=s.train_id,
            from_station=origin.station_id,
            to_station=next_stn,
            is_origin=True,
        )
        return make_event(
            event_type=EventType.TRAIN_DEPART,
            sim_time=origin.depart_min,
            payload=payload,
        )


def build_scheduler_from_timetable(
    timetable: Sequence[TrainSchedule],
    *,
    direction: str | None = None,
    start_after_min: float = 0.0,
) -> TrainScheduler:
    """One-liner factory for common usage."""
    return TrainScheduler(
        timetable,
        filter_direction=direction,
        start_after_min=start_after_min,
    )
