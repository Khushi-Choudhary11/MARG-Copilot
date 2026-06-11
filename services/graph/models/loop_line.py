"""
LoopLine model — represents a crossing loop or siding at a station.

Loop lines are the core infrastructure resource for crossing decisions
on single-line sections. Their length determines which trains can use them.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from .enums import ElectrificationType, LoopLineType


@dataclass(frozen=True)
class LoopLine:
    """
    A single loop or siding track at a station.

    Immutable value object — runtime state (occupation) is tracked
    separately in the simulation layer, not here.

    Attributes
    ----------
    loop_id:
        Unique identifier, e.g. ``"ALJN_L1"``.
    station_id:
        Parent station this loop belongs to.
    loop_type:
        Operational role (crossing, overtaking, goods, stabling).
    length_meters:
        Usable length in metres. A goods train of 58 BOXN wagons
        is ~720 m; a 24-coach passenger train is ~640 m.
    electrification:
        Traction supply on the loop. Electric locos cannot use
        non-electrified loops.
    max_axle_load_tonnes:
        Structural rating. Heavier freight requires higher rating.
    can_hold_passenger_train:
        Derived convenience flag — True when length >= 600 m and
        electrification is compatible.
    notes:
        Operational notes, e.g. gradient on departure.
    """

    loop_id: str
    station_id: str
    loop_type: LoopLineType
    length_meters: float
    electrification: ElectrificationType = ElectrificationType.AC_25KV
    max_axle_load_tonnes: float = 22.9  # BOXN standard
    notes: str = ""

    # ── Computed properties ──────────────────────────────────────────────────

    @property
    def can_hold_passenger_train(self) -> bool:
        """True if loop is long enough for a standard 24-coach rake."""
        return (
            self.length_meters >= 600
            and self.electrification in (
                ElectrificationType.AC_25KV,
                ElectrificationType.DUAL,
            )
        )

    @property
    def can_hold_goods_train(self) -> bool:
        """
        True if loop can hold a standard BOXN goods rake (58 wagons + loco).
        Requires >= 720 m and adequate axle load rating.
        """
        return (
            self.length_meters >= 720
            and self.max_axle_load_tonnes >= 22.9
        )

    def can_accommodate(self, train_length_m: float,
                        requires_electrification: bool = True) -> bool:
        """
        Return True if this loop can physically hold a train.

        Parameters
        ----------
        train_length_m:
            Total train length including locomotive.
        requires_electrification:
            Whether the train needs electric traction supply on the loop.
        """
        if self.length_meters < train_length_m:
            return False
        if requires_electrification and self.electrification not in (
            ElectrificationType.AC_25KV,
            ElectrificationType.DUAL,
        ):
            return False
        return True

    def __repr__(self) -> str:
        return (
            f"LoopLine({self.loop_id!r}, "
            f"station={self.station_id!r}, "
            f"length={self.length_meters:.0f}m, "
            f"type={self.loop_type.value})"
        )
