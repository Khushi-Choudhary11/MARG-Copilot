"""
Metrics Collector
=================
Records time-series performance data throughout the simulation and
exposes aggregated statistics for the dashboard impact counter and
post-run analysis.

All timestamps are in simulation minutes-since-midnight.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Optional

logger = logging.getLogger(__name__)


# ── Per-train metrics ─────────────────────────────────────────────────────────

@dataclass
class TrainMetrics:
    train_id:       str
    train_name:     str
    category:       str
    priority:       int

    # Arrival delays at each stop (station_id → delay_minutes)
    arrival_delays: dict[str, float] = field(default_factory=dict)

    # How long the train spent in loops / held at signals
    loop_time_min:  float = 0.0
    hold_time_min:  float = 0.0

    # Disruptions that directly affected this train
    disruptions_encountered: list[str] = field(default_factory=list)

    # Status transitions (sim_time, status_name)
    status_log: list[tuple[float, str]] = field(default_factory=list)

    @property
    def max_delay(self) -> float:
        return max(self.arrival_delays.values(), default=0.0)

    @property
    def mean_delay(self) -> float:
        vals = list(self.arrival_delays.values())
        return mean(vals) if vals else 0.0

    @property
    def on_time(self) -> bool:
        """True if max arrival delay ≤ 5 minutes."""
        return self.max_delay <= 5.0

    def record_arrival(self, station_id: str, delay_min: float) -> None:
        self.arrival_delays[station_id] = delay_min

    def record_hold(self, duration_min: float, reason: str) -> None:
        self.hold_time_min += duration_min
        self.disruptions_encountered.append(f"HOLD {duration_min:.1f}min: {reason}")

    def record_loop(self, duration_min: float) -> None:
        self.loop_time_min += duration_min

    def to_dict(self) -> dict:
        return {
            "train_id":     self.train_id,
            "train_name":   self.train_name,
            "category":     self.category,
            "priority":     self.priority,
            "max_delay":    round(self.max_delay, 1),
            "mean_delay":   round(self.mean_delay, 1),
            "on_time":      self.on_time,
            "loop_time":    round(self.loop_time_min, 1),
            "hold_time":    round(self.hold_time_min, 1),
            "disruptions":  self.disruptions_encountered,
        }


# ── Per-section metrics ───────────────────────────────────────────────────────

@dataclass
class SectionMetrics:
    section_id:     str
    # Sampled congestion scores (one per tick)
    congestion_samples: list[float] = field(default_factory=list)
    # Count of disruption events by type
    signal_failures: int = 0
    blockage_events: int = 0
    weather_updates: int = 0
    total_trains_passed: int = 0

    @property
    def mean_congestion(self) -> float:
        return mean(self.congestion_samples) if self.congestion_samples else 0.0

    @property
    def max_congestion(self) -> float:
        return max(self.congestion_samples, default=0.0)

    def to_dict(self) -> dict:
        return {
            "section_id":        self.section_id,
            "mean_congestion":   round(self.mean_congestion, 3),
            "max_congestion":    round(self.max_congestion, 3),
            "signal_failures":   self.signal_failures,
            "blockage_events":   self.blockage_events,
            "trains_passed":     self.total_trains_passed,
        }


# ── Time-series snapshot ──────────────────────────────────────────────────────

@dataclass
class TimePoint:
    sim_time:          float
    active_trains:     int
    total_delay_min:   float
    congested_sections: int
    blocked_sections:  int


# ── Main collector ────────────────────────────────────────────────────────────

class MetricsCollector:
    """
    Accumulates all simulation metrics.

    Usage (inside event handlers or the engine tick):
        metrics.record_tick(state_snapshot, sim_time)
        metrics.record_arrival(train_id, station_id, delay_min, sim_time)
        metrics.record_disruption("signal_fail", section_id, sim_time)
    """

    def __init__(self) -> None:
        self._trains:   dict[str, TrainMetrics]   = {}
        self._sections: dict[str, SectionMetrics] = {}
        self._timeline: list[TimePoint]           = []

        # Running totals updated on each relevant event
        self._total_delay_saved:   float = 0.0   # delay saved by MARG interventions
        self._baseline_delay:      float = 0.0   # what delay would have been without MARG
        self._disruption_events:   int   = 0

        # Tracks when holds started, to compute durations on release
        self._hold_start: dict[str, float] = {}  # train_id → sim_time hold began
        self._loop_start: dict[str, float] = {}

    # ── Registration ──────────────────────────────────────────────────────────

    def register_train(self, train_id: str, name: str, category: str, priority: int) -> None:
        self._trains[train_id] = TrainMetrics(
            train_id=train_id, train_name=name,
            category=category, priority=priority,
        )

    def register_section(self, section_id: str) -> None:
        self._sections[section_id] = SectionMetrics(section_id=section_id)

    # ── Event recording ───────────────────────────────────────────────────────

    def record_arrival(self, train_id: str, station_id: str, delay_min: float) -> None:
        if train_id in self._trains:
            self._trains[train_id].record_arrival(station_id, delay_min)

    def record_hold_start(self, train_id: str, sim_time: float, reason: str) -> None:
        self._hold_start[train_id] = sim_time
        if train_id in self._trains:
            self._trains[train_id].disruptions_encountered.append(
                f"HELD at {sim_time:.1f}: {reason}"
            )

    def record_hold_end(self, train_id: str, sim_time: float, reason: str = "") -> None:
        start = self._hold_start.pop(train_id, None)
        if start is not None and train_id in self._trains:
            duration = sim_time - start
            self._trains[train_id].record_hold(duration, reason)

    def record_loop_start(self, train_id: str, sim_time: float) -> None:
        self._loop_start[train_id] = sim_time

    def record_loop_end(self, train_id: str, sim_time: float) -> None:
        start = self._loop_start.pop(train_id, None)
        if start is not None and train_id in self._trains:
            self._trains[train_id].record_loop(sim_time - start)

    def record_disruption(self, kind: str, entity_id: str, sim_time: float) -> None:
        """Record a disruption event (signal_fail, blockage, weather)."""
        self._disruption_events += 1
        if entity_id in self._sections:
            sec = self._sections[entity_id]
            if kind == "signal_fail":
                sec.signal_failures += 1
            elif kind == "blockage":
                sec.blockage_events += 1
            elif kind == "weather":
                sec.weather_updates += 1

    def record_section_tick(self, section_id: str, congestion_score: float) -> None:
        if section_id in self._sections:
            self._sections[section_id].congestion_samples.append(congestion_score)

    def record_delay_saved(self, minutes: float) -> None:
        """Called when MARG's intervention demonstrably reduces cascade delay."""
        self._total_delay_saved += minutes

    def record_tick(
        self,
        sim_time:           float,
        active_trains:      int,
        total_delay_min:    float,
        congested_sections: int,
        blocked_sections:   int,
    ) -> None:
        self._timeline.append(TimePoint(
            sim_time=sim_time,
            active_trains=active_trains,
            total_delay_min=total_delay_min,
            congested_sections=congested_sections,
            blocked_sections=blocked_sections,
        ))

    # ── Aggregated report ─────────────────────────────────────────────────────

    def summary(self) -> dict:
        all_delays = [
            d
            for tm in self._trains.values()
            for d in tm.arrival_delays.values()
        ]
        on_time_count = sum(1 for tm in self._trains.values() if tm.on_time)

        return {
            "trains_tracked":       len(self._trains),
            "disruption_events":    self._disruption_events,
            "delay_stats": {
                "total_min":        round(sum(all_delays), 1),
                "mean_min":         round(mean(all_delays), 1) if all_delays else 0.0,
                "median_min":       round(median(all_delays), 1) if all_delays else 0.0,
                "stdev_min":        round(stdev(all_delays), 1) if len(all_delays) > 1 else 0.0,
                "max_min":          round(max(all_delays, default=0.0), 1),
            },
            "on_time_trains":       on_time_count,
            "otp_pct":              round(
                100 * on_time_count / max(len(self._trains), 1), 1
            ),
            "delay_saved_by_marg":  round(self._total_delay_saved, 1),
            "congestion_peaks": {
                sid: round(sm.max_congestion, 3)
                for sid, sm in self._sections.items()
                if sm.max_congestion > 0.5
            },
        }

    def train_report(self) -> list[dict]:
        return sorted(
            [tm.to_dict() for tm in self._trains.values()],
            key=lambda d: d["max_delay"],
            reverse=True,
        )

    def section_report(self) -> list[dict]:
        return sorted(
            [sm.to_dict() for sm in self._sections.values()],
            key=lambda d: d["mean_congestion"],
            reverse=True,
        )

    def timeline_as_dicts(self) -> list[dict]:
        return [
            {
                "sim_time":           tp.sim_time,
                "active_trains":      tp.active_trains,
                "total_delay_min":    round(tp.total_delay_min, 1),
                "congested_sections": tp.congested_sections,
                "blocked_sections":   tp.blocked_sections,
            }
            for tp in self._timeline
        ]

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {
                "summary":  self.summary(),
                "trains":   self.train_report(),
                "sections": self.section_report(),
            },
            indent=indent,
        )

    def __repr__(self) -> str:
        return (
            f"MetricsCollector("
            f"trains={len(self._trains)} "
            f"sections={len(self._sections)} "
            f"ticks={len(self._timeline)})"
        )
