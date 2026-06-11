"""MARG Simulation — state layer."""
from .state_manager import StateManager, StateError
from .metrics import MetricsCollector, TrainMetrics, SectionMetrics
from .snapshot import SimSnapshot, SnapshotRing, diff_snapshots

__all__ = [
    "StateManager", "StateError",
    "MetricsCollector", "TrainMetrics", "SectionMetrics",
    "SimSnapshot", "SnapshotRing", "diff_snapshots",
]
