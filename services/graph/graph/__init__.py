"""MARG Graph Engine — graph layer."""

from .corridor_graph import CorridorGraph, GraphError
from .algorithms import (
    Bottleneck,
    CascadeNode,
    CascadeResult,
    CrossingOption,
    CrossingPlan,
    PathResult,
    RailwayAlgorithms,
)
from .queries import CorridorSummary, GraphQueries

__all__ = [
    "Bottleneck",
    "CascadeNode",
    "CascadeResult",
    "CorridorGraph",
    "CorridorSummary",
    "CrossingOption",
    "CrossingPlan",
    "GraphError",
    "GraphQueries",
    "PathResult",
    "RailwayAlgorithms",
]
