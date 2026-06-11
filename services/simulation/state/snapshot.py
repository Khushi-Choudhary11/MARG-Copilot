"""
Snapshot
========
Lightweight helpers for capturing, comparing, and replaying simulation
state snapshots.  Used by:
  - The WebSocket publisher (sends diff-compressed state to frontend)
  - The replay engine (re-runs scenarios from a saved starting point)
  - The test harness (asserts state at specific sim times)
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SimSnapshot:
    """
    Immutable record of complete simulation state at one sim_time.

    Attributes
    ----------
    sim_time:
        The simulation clock value (minutes-since-midnight).
    wall_time:
        Wall-clock Unix timestamp when the snapshot was taken.
    sequence:
        Monotonically increasing snapshot counter for ordering.
    state:
        Full state dict from StateManager.snapshot().
    metadata:
        Optional free-form dict (e.g. scenario name, disruption labels).
    """
    sim_time:  float
    wall_time: float
    sequence:  int
    state:     dict[str, Any]
    metadata:  dict[str, Any] = field(default_factory=dict)

    def to_json(self, indent: int = 0) -> str:
        return json.dumps(
            {
                "sim_time":  self.sim_time,
                "wall_time": self.wall_time,
                "sequence":  self.sequence,
                "metadata":  self.metadata,
                "state":     self.state,
            },
            indent=indent or None,
        )

    @classmethod
    def from_json(cls, raw: str) -> "SimSnapshot":
        d = json.loads(raw)
        return cls(
            sim_time  = d["sim_time"],
            wall_time = d["wall_time"],
            sequence  = d["sequence"],
            state     = d["state"],
            metadata  = d.get("metadata", {}),
        )

    def get_train(self, train_id: str) -> Optional[dict]:
        return self.state.get("trains", {}).get(train_id)

    def get_section(self, section_id: str) -> Optional[dict]:
        return self.state.get("sections", {}).get(section_id)

    def summary(self) -> dict:
        return self.state.get("summary", {})


class SnapshotRing:
    """
    Fixed-capacity ring buffer of SimSnapshot objects.
    Older snapshots are discarded automatically when capacity is exceeded.
    Thread-safe for single-producer / multiple-consumer use (GIL sufficient).

    Parameters
    ----------
    capacity:
        Maximum number of snapshots to retain (default 1 440 — one per
        simulated minute over a full 24-hour run).
    """

    def __init__(self, capacity: int = 1_440) -> None:
        self._capacity = capacity
        self._ring:    list[Optional[SimSnapshot]] = [None] * capacity
        self._head:    int = 0        # next write position
        self._count:   int = 0        # number of valid entries
        self._seq:     int = 0        # global sequence counter

    def push(
        self,
        sim_time: float,
        state:    dict,
        metadata: Optional[dict] = None,
    ) -> SimSnapshot:
        """Take a deep copy of *state* and store as a new snapshot."""
        snap = SimSnapshot(
            sim_time  = sim_time,
            wall_time = time.time(),
            sequence  = self._seq,
            state     = copy.deepcopy(state),
            metadata  = metadata or {},
        )
        self._ring[self._head] = snap
        self._head  = (self._head + 1) % self._capacity
        self._count = min(self._count + 1, self._capacity)
        self._seq  += 1
        return snap

    def latest(self) -> Optional[SimSnapshot]:
        """Return the most recent snapshot."""
        if self._count == 0:
            return None
        idx = (self._head - 1) % self._capacity
        return self._ring[idx]

    def all(self) -> list[SimSnapshot]:
        """Return all retained snapshots in chronological order."""
        if self._count == 0:
            return []
        if self._count < self._capacity:
            return [s for s in self._ring[:self._count] if s is not None]
        # Ring has wrapped
        ordered = self._ring[self._head:] + self._ring[:self._head]
        return [s for s in ordered if s is not None]

    def at_sim_time(self, sim_time: float, tolerance: float = 0.5) -> Optional[SimSnapshot]:
        """
        Return the snapshot closest to *sim_time*, within *tolerance* minutes.
        Returns None if no snapshot is within tolerance.
        """
        best: Optional[SimSnapshot] = None
        best_diff = float("inf")
        for snap in self.all():
            diff = abs(snap.sim_time - sim_time)
            if diff < best_diff:
                best_diff = diff
                best = snap
        if best_diff <= tolerance:
            return best
        return None

    def between(self, start_min: float, end_min: float) -> list[SimSnapshot]:
        """Return all snapshots whose sim_time falls in [start_min, end_min]."""
        return [s for s in self.all() if start_min <= s.sim_time <= end_min]

    def __len__(self) -> int:
        return self._count

    def __repr__(self) -> str:
        latest = self.latest()
        return (
            f"SnapshotRing("
            f"count={self._count}/{self._capacity} "
            f"latest={latest.sim_time if latest else 'none'})"
        )


def diff_snapshots(a: SimSnapshot, b: SimSnapshot) -> dict:
    """
    Compute a lightweight diff between two snapshots.
    Returns a dict describing which trains, sections, and stations changed.

    Used by the WebSocket publisher to send partial updates instead of
    full state dumps every tick.
    """
    result: dict[str, Any] = {
        "sim_time_from": a.sim_time,
        "sim_time_to":   b.sim_time,
        "trains":   {},
        "sections": {},
        "stations": {},
    }

    a_trains = a.state.get("trains", {})
    b_trains = b.state.get("trains", {})

    for tid in set(a_trains) | set(b_trains):
        at = a_trains.get(tid, {})
        bt = b_trains.get(tid, {})
        if at != bt:
            result["trains"][tid] = bt  # send full new state for changed trains

    a_secs = a.state.get("sections", {})
    b_secs = b.state.get("sections", {})
    for sid in set(a_secs) | set(b_secs):
        if a_secs.get(sid) != b_secs.get(sid):
            result["sections"][sid] = b_secs.get(sid, {})

    a_stns = a.state.get("stations", {})
    b_stns = b.state.get("stations", {})
    for sid in set(a_stns) | set(b_stns):
        if a_stns.get(sid) != b_stns.get(sid):
            result["stations"][sid] = b_stns.get(sid, {})

    return result
