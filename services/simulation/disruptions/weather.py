"""
Weather Disruption
==================
Models weather conditions (fog, rain, storms) that reduce train speeds
across the corridor.  Weather is applied as a speed_factor in [0.15, 1.0]
to all sections or a corridor sub-range.

Integration
-----------
The engine calls WeatherController.generate_events() to get a list of
WEATHER_UPDATE events that the EventEngine schedules.  When fired, the
handler calls StateManager.apply_weather_to_section() for each affected
section.

Weather scenarios available:
    WeatherEvent.CLEAR       → speed_factor 1.0
    WeatherEvent.LIGHT_FOG   → speed_factor 0.80
    WeatherEvent.MODERATE_FOG→ speed_factor 0.55
    WeatherEvent.DENSE_FOG   → speed_factor 0.15  (IR Speed Restriction SR-15)
    WeatherEvent.LIGHT_RAIN  → speed_factor 0.90
    WeatherEvent.HEAVY_RAIN  → speed_factor 0.70
    WeatherEvent.STORM       → speed_factor 0.50
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from services.simulation.core.event_types import EventType, make_event, Event

logger = logging.getLogger(__name__)


class WeatherCondition(Enum):
    CLEAR        = (1.00, "Clear — normal operations")
    LIGHT_FOG    = (0.80, "Light fog — minor speed restriction")
    MODERATE_FOG = (0.55, "Moderate fog — caution order in effect")
    DENSE_FOG    = (0.15, "Dense fog — SR-15 speed restriction")
    LIGHT_RAIN   = (0.90, "Light rain — slight speed reduction")
    HEAVY_RAIN   = (0.70, "Heavy rain — caution required")
    STORM        = (0.50, "Storm — significant restriction")

    def __init__(self, speed_factor: float, description: str) -> None:
        self.speed_factor = speed_factor
        self.description  = description

    @classmethod
    def from_speed_factor(cls, factor: float) -> "WeatherCondition":
        best = cls.CLEAR
        best_diff = abs(factor - cls.CLEAR.speed_factor)
        for cond in cls:
            diff = abs(factor - cond.speed_factor)
            if diff < best_diff:
                best_diff = diff
                best = cond
        return best


@dataclass(frozen=True)
class WeatherUpdatePayload:
    """Payload for WEATHER_UPDATE events."""
    condition:    WeatherCondition
    speed_factor: float
    section_ids:  tuple[str, ...]   # empty tuple = ALL sections
    description:  str


def _make_weather_event(
    sim_time:    float,
    condition:   WeatherCondition,
    section_ids: list[str],
) -> Event:
    payload = WeatherUpdatePayload(
        condition    = condition,
        speed_factor = condition.speed_factor,
        section_ids  = tuple(section_ids),
        description  = condition.description,
    )
    return make_event(EventType.WEATHER_UPDATE, sim_time, payload)


class WeatherController:
    """
    Generates WEATHER_UPDATE events from a predefined scenario or
    stochastically.

    Parameters
    ----------
    affected_sections:
        Section IDs this controller can affect.
        Empty list means the controller affects ALL sections.
    seed:
        Random seed for reproducible stochastic scenarios.
    """

    def __init__(
        self,
        affected_sections: Optional[list[str]] = None,
        seed: int = 42,
    ) -> None:
        self._sections = affected_sections or []
        self._rng = random.Random(seed)
        self._scheduled_events: list[Event] = []

    # ── Preset scenarios ──────────────────────────────────────────────────────

    def schedule_clear(self, sim_time: float) -> None:
        self._scheduled_events.append(
            _make_weather_event(sim_time, WeatherCondition.CLEAR, self._sections)
        )

    def schedule_fog(
        self,
        onset_time:   float,
        clear_time:   float,
        condition:    WeatherCondition = WeatherCondition.DENSE_FOG,
    ) -> None:
        """
        Schedule a fog event that starts at *onset_time* and clears at *clear_time*.
        """
        self._scheduled_events.append(
            _make_weather_event(onset_time, condition, self._sections)
        )
        self._scheduled_events.append(
            _make_weather_event(clear_time, WeatherCondition.CLEAR, self._sections)
        )
        logger.info(
            "WeatherController: %s onset=%.1f clear=%.1f sections=%s",
            condition.name, onset_time, clear_time,
            self._sections or "ALL",
        )

    def schedule_rain(
        self,
        onset_time: float,
        clear_time: float,
        heavy:      bool = False,
    ) -> None:
        cond = WeatherCondition.HEAVY_RAIN if heavy else WeatherCondition.LIGHT_RAIN
        self._scheduled_events.append(
            _make_weather_event(onset_time, cond, self._sections)
        )
        self._scheduled_events.append(
            _make_weather_event(clear_time, WeatherCondition.CLEAR, self._sections)
        )

    def schedule_storm(self, onset_time: float, clear_time: float) -> None:
        self._scheduled_events.append(
            _make_weather_event(onset_time, WeatherCondition.STORM, self._sections)
        )
        self._scheduled_events.append(
            _make_weather_event(clear_time, WeatherCondition.CLEAR, self._sections)
        )

    # ── Stochastic scenario ───────────────────────────────────────────────────

    def generate_stochastic_day(
        self,
        sim_start: float = 360.0,    # 06:00
        sim_end:   float = 1440.0,   # 24:00
        num_events: int = 3,
    ) -> None:
        """
        Randomly insert *num_events* weather disruptions over the sim window.
        Each event has a random onset, random condition, and random duration.
        """
        conditions = [
            WeatherCondition.LIGHT_FOG,
            WeatherCondition.MODERATE_FOG,
            WeatherCondition.DENSE_FOG,
            WeatherCondition.LIGHT_RAIN,
            WeatherCondition.HEAVY_RAIN,
        ]
        window = sim_end - sim_start - 60   # leave 1-hour tail buffer

        for _ in range(num_events):
            onset    = sim_start + self._rng.uniform(0, window)
            duration = self._rng.uniform(20, 90)   # 20–90 min disruption
            clear    = min(onset + duration, sim_end - 5)
            cond     = self._rng.choice(conditions)
            self.schedule_fog(onset, clear, cond)

    # ── Generate events ───────────────────────────────────────────────────────

    def generate_events(self) -> list[Event]:
        """Return all scheduled weather events, sorted by sim_time."""
        return sorted(self._scheduled_events, key=lambda e: e.sim_time)


# ── Canonical demo scenario ───────────────────────────────────────────────────

def ndls_cnb_morning_fog_scenario(section_ids: list[str]) -> WeatherController:
    """
    Standard demo scenario:
    Dense fog NDLS–ALJN corridor 06:00–09:30, then clears.
    Light rain ALJN–CNB 10:00–12:00.
    """
    ctrl = WeatherController(affected_sections=section_ids)
    ctrl.schedule_fog(onset_time=360.0, clear_time=570.0,
                      condition=WeatherCondition.DENSE_FOG)
    ctrl.schedule_rain(onset_time=600.0, clear_time=720.0, heavy=False)
    return ctrl
