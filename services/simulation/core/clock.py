"""
Simulation Clock
================
Tracks simulation time independently of wall-clock time.
Supports acceleration (e.g. 1 sim-minute = 0.1 real seconds for demo).

All simulation time is stored as **minutes since midnight** (float).
The corridor timetable uses the same unit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class SimClock:
    """
    Monotonic simulation clock.

    Parameters
    ----------
    start_minutes:
        Simulation start time in minutes-since-midnight (e.g. 360.0 = 06:00).
    acceleration:
        Ratio of sim-time to wall-time.  60.0 means 1 real second = 60 sim-seconds = 1 sim-minute.
        Use 1.0 for real-time; use a large value for fast-forward.
    """

    start_minutes: float = 360.0          # 06:00
    acceleration: float  = 60.0           # 1 real-second = 1 sim-minute

    _sim_now: float = field(init=False)
    _wall_start: float = field(init=False)

    def __post_init__(self) -> None:
        self._sim_now   = self.start_minutes
        self._wall_start = time.monotonic()

    # ── Core time queries ─────────────────────────────────────────────────────

    @property
    def now(self) -> float:
        """Current simulation time in minutes-since-midnight."""
        return self._sim_now

    @property
    def elapsed_sim_minutes(self) -> float:
        """Sim-minutes elapsed since the clock was started."""
        return self._sim_now - self.start_minutes

    @property
    def elapsed_wall_seconds(self) -> float:
        """Real seconds elapsed since the clock was started."""
        return time.monotonic() - self._wall_start

    # ── Mutation ──────────────────────────────────────────────────────────────

    def advance(self, sim_minutes: float) -> None:
        """
        Advance the clock by ``sim_minutes``.
        Called by the event engine each time it processes an event.
        """
        if sim_minutes < 0:
            raise ValueError(f"Cannot advance clock backwards by {sim_minutes} min")
        self._sim_now += sim_minutes

    def jump_to(self, sim_time: float) -> None:
        """
        Jump the clock to an absolute simulation time.
        Used by the event engine to skip to the next event's timestamp.
        """
        if sim_time < self._sim_now:
            raise ValueError(
                f"Cannot jump backwards: current={self._sim_now:.2f}, target={sim_time:.2f}"
            )
        self._sim_now = sim_time

    # ── Formatting helpers ────────────────────────────────────────────────────

    @staticmethod
    def minutes_to_hhmm(minutes: float) -> str:
        """Convert float minutes-since-midnight to 'HH:MM' string."""
        h = int(minutes // 60) % 24
        m = int(minutes % 60)
        return f"{h:02d}:{m:02d}"

    @staticmethod
    def hhmm_to_minutes(hhmm: str) -> float:
        """Convert 'HH:MM' string to float minutes-since-midnight."""
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)

    def now_hhmm(self) -> str:
        """Current simulation time as 'HH:MM'."""
        return self.minutes_to_hhmm(self._sim_now)

    def __repr__(self) -> str:
        return (
            f"SimClock(sim={self.now_hhmm()}, "
            f"elapsed={self.elapsed_sim_minutes:.1f}min, "
            f"accel={self.acceleration}x)"
        )
