"""
Track Blockage Disruption
=========================
Models hard track blocks: derailments, level-crossing accidents, engineering
possession blocks, or any event that completely closes a section.

Unlike a signal failure (trains proceed with caution), a full block means
NO train may enter the section until it is cleared.

Integration
-----------
  TRACK_BLOCK  event → engine handler → state.apply_blockage(section_id)
  TRACK_CLEAR  event → engine handler → state.clear_blockage(section_id)

The engine's TRAIN_DEPART handler must check section.headway_satisfied()
AND section.condition != BLOCKED before dispatching a train.  If blocked,
it should reschedule the depart event for after the expected clear time.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from services.simulation.core.event_types import EventType, make_event, Event

logger = logging.getLogger(__name__)


class BlockageType(str):
    DERAILMENT           = "derailment"
    LEVEL_CROSSING       = "level_crossing_accident"
    ENGINEERING_BLOCK    = "engineering_possession"
    ANIMAL_ON_TRACK      = "animal_on_track"
    FLOOD                = "flood_washout"


@dataclass(frozen=True)
class TrackBlockPayload:
    """Payload for TRACK_BLOCK events."""
    section_id:     str
    clear_time:     float     # sim_time when block is lifted
    blockage_type:  str
    description:    str
    divert_trains:  bool = True   # whether MARG should suggest reroutes


@dataclass(frozen=True)
class TrackClearPayload:
    """Payload for TRACK_CLEAR events."""
    section_id:    str
    description:   str


class TrackBlockageController:
    """
    Schedules TRACK_BLOCK + TRACK_CLEAR event pairs.

    Parameters
    ----------
    seed:
        RNG seed for reproducible stochastic scenarios.
    """

    def __init__(self, seed: int = 77) -> None:
        self._rng    = random.Random(seed)
        self._events: list[Event] = []

    # ── Explicit scheduling ───────────────────────────────────────────────────

    def schedule_blockage(
        self,
        section_id:    str,
        block_time:    float,
        clear_time:    float,
        blockage_type: str = BlockageType.ENGINEERING_BLOCK,
        divert_trains: bool = True,
    ) -> None:
        """
        Schedule a hard block on *section_id* from *block_time* to *clear_time*.
        """
        if clear_time <= block_time:
            raise ValueError(
                f"clear_time ({clear_time}) must be after block_time ({block_time})"
            )

        block_payload = TrackBlockPayload(
            section_id    = section_id,
            clear_time    = clear_time,
            blockage_type = blockage_type,
            description   = (
                f"{blockage_type.replace('_', ' ').title()} on {section_id} "
                f"(block={block_time:.1f}, clear={clear_time:.1f})"
            ),
            divert_trains = divert_trains,
        )
        clear_payload = TrackClearPayload(
            section_id  = section_id,
            description = f"Block cleared on {section_id} at t={clear_time:.1f}",
        )

        self._events.append(
            make_event(EventType.TRACK_BLOCK, block_time, block_payload)
        )
        self._events.append(
            make_event(EventType.TRACK_CLEAR, clear_time, clear_payload)
        )
        logger.info(
            "TrackBlockageController: %s block=%.1f clear=%.1f type=%s",
            section_id, block_time, clear_time, blockage_type,
        )

    # ── Stochastic scheduling ─────────────────────────────────────────────────

    def schedule_random_blockages(
        self,
        section_ids:  list[str],
        sim_start:    float = 360.0,
        sim_end:      float = 1440.0,
        num_blockages: int  = 1,
    ) -> None:
        """
        Randomly place *num_blockages* hard blocks across *section_ids*.
        """
        types = [
            BlockageType.DERAILMENT,
            BlockageType.LEVEL_CROSSING,
            BlockageType.ENGINEERING_BLOCK,
            BlockageType.ANIMAL_ON_TRACK,
        ]
        durations = {
            BlockageType.DERAILMENT:        (60, 180),
            BlockageType.LEVEL_CROSSING:    (15, 45),
            BlockageType.ENGINEERING_BLOCK: (30, 120),
            BlockageType.ANIMAL_ON_TRACK:   (5, 20),
        }

        available = list(section_ids)
        for _ in range(min(num_blockages, len(available))):
            section_id = self._rng.choice(available)
            available.remove(section_id)

            btype         = self._rng.choice(types)
            lo, hi        = durations[btype]
            block_time    = self._rng.uniform(sim_start + 60, sim_end - hi - 30)
            duration      = self._rng.uniform(lo, hi)
            clear_time    = block_time + duration

            self.schedule_blockage(
                section_id    = section_id,
                block_time    = block_time,
                clear_time    = clear_time,
                blockage_type = btype,
                divert_trains = btype in (
                    BlockageType.DERAILMENT, BlockageType.LEVEL_CROSSING
                ),
            )

    # ── Generate events ───────────────────────────────────────────────────────

    def generate_events(self) -> list[Event]:
        return sorted(self._events, key=lambda e: e.sim_time)


# ── Canonical demo scenario ───────────────────────────────────────────────────

def tundla_blockage(
    block_time: float = 540.0,   # 09:00
    clear_time: float = 660.0,   # 11:00
) -> list[Event]:
    """
    Demo: derailment at Tundla (TDL→FZD section) at 09:00, cleared at 11:00.
    This is the primary demo disruption in MARG's pitch.
    """
    ctrl = TrackBlockageController()
    ctrl.schedule_blockage(
        section_id    = "TDL_FZD_UP",
        block_time    = block_time,
        clear_time    = clear_time,
        blockage_type = BlockageType.DERAILMENT,
        divert_trains = True,
    )
    return ctrl.generate_events()
