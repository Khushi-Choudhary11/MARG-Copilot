"""
MARG Railway Graph Engine
=========================

A production-grade NetworkX-based graph engine modelling the
Delhi–Kanpur (NDLS–CNB) railway corridor.

Quick start
-----------
>>> from services.graph import GraphQueries
>>> gq = GraphQueries.build()
>>> result = gq.path("NDLS", "CNB")
>>> print(f"Travel time: {result.total_travel_min:.0f} min over {result.total_length_km:.0f} km")

>>> plan = gq.crossing_plan(
...     "12301", "ALJN", 640, 0, 5.0,   # Rajdhani, near Aligarh, 5 min late
...     "70501", "TDL",  720, 4, 45.0,  # Goods, near Tundla, 45 min late
... )
>>> print(f"Cross at {plan.crossing_station.name}, {plan.waiter} waits {plan.estimated_wait_minutes:.0f} min")
"""

from .graph.corridor_graph import CorridorGraph, GraphError
from .graph.algorithms import (
    Bottleneck,
    CascadeNode,
    CascadeResult,
    CrossingOption,
    CrossingPlan,
    PathResult,
    RailwayAlgorithms,
)
from .graph.queries import CorridorSummary, GraphQueries
from .models import (
    Direction,
    ElectrificationType,
    LineType,
    LoopLine,
    LoopLineType,
    Platform,
    SectionStatus,
    SignalAspect,
    SignalBlock,
    Station,
    StationClass,
    TrackSection,
    TrainCategory,
    TrainPriority,
)

__all__ = [
    # Primary interface
    "GraphQueries",
    "CorridorGraph",
    "GraphError",
    # Algorithm results
    "Bottleneck",
    "CascadeNode",
    "CascadeResult",
    "CorridorSummary",
    "CrossingOption",
    "CrossingPlan",
    "PathResult",
    "RailwayAlgorithms",
    # Models
    "Direction",
    "ElectrificationType",
    "LineType",
    "LoopLine",
    "LoopLineType",
    "Platform",
    "SectionStatus",
    "SignalAspect",
    "SignalBlock",
    "Station",
    "StationClass",
    "TrackSection",
    "TrainCategory",
    "TrainPriority",
]

__version__ = "1.0.0"
