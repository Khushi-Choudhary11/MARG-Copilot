"""
Signal Failure Disruption
=========================
Models signal equipment failures on track sections.
A signal failure forces all following trains to proceed under the
"fail-safe" rule: speed reduced, minimum block-interval extended.

When a signal fails:
  1. The affected section's condition → SIGNAL_FAIL
  2. effective_travel_min() adds a 1.5× penalty factor (from SectionState)
  3. A SIGNAL_RESTORE event is scheduled for the repair time

The handler in the main engine should:
  - Call state.apply_signal_failure(section_id, restore_time) on SIGNAL_FAIL event
  - Call state.restore_signal(section_id) on SIGNAL_RESTORE event
  - Publish the disruption to connected trains via add_delay_to_train
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from services.simulation.core.event_types import EventType, make_event, Event

logger = logging.getLogger(__name__)

# Typical IR signal repair times (minutes)
_REPAIR_MIN = 15
_REPAIR_MAX = 60


@dataclass(frozen=True)
class SignalFailPayload:
    """Payload for SIGNAL_FAIL events."""
    section_id:   str
    restore_time: float   # sim_time when signal will be restored
    severity:     str     # 'partial' | 'full'
    description:  str


@dataclass(frozen=True)
class SignalRestorePayload:
    """Payload for SIGNAL_RESTORE events."""
    section_id:  str
    description: str


class SignalFailureController:
    """
    Generates SIGNAL_FAIL + matching SIGNAL_RESTORE event pairs.

    Parameters
    ----------
    seed:
        RNG seed for reproducible stochastic scenarios.
    """

    def __init__(self, seed: int = 99) -> None:
        self._rng = random.Random(seed)
        self._events: list[Event] = []

    # ── Explicit scheduling ───────────────────────────────────────────────────

    def schedule_failure(
        self,
        section_id:   str,
        fail_time:    float,
        repair_time:  float,
        severity:     str = "full",
    ) -> None:
        """
        Schedule a single signal failure on *section_id*.

        Parameters
        ----------
        fail_time:
            Sim time (minutes) when the signal fails.
        repair_time:
            Sim time (minutes) when the signal is restored.
        severity:
            'partial' (trains proceed cautiously) or 'full' (full block).
        """
        if repair_time <= fail_time:
            raise ValueError(
                f"repair_time ({repair_time}) must be after fail_time ({fail_time})"
            )

        fail_payload = SignalFailPayload(
            section_id   = section_id,
            restore_time = repair_time,
            severity     = severity,
            description  = (
                f"Signal {'partial failure' if severity == 'partial' else 'failure'} "
                f"on {section_id} at t={fail_time:.1f}"
            ),
        )
        restore_payload = SignalRestorePayload(
            section_id  = section_id,
            description = f"Signal restored on {section_id} at t={repair_time:.1f}",
        )

        self._events.append(
            make_event(EventType.SIGNAL_FAIL, fail_time, fail_payload)
        )
        self._events.append(
            make_event(EventType.SIGNAL_RESTORE, repair_time, restore_payload)
        )
        logger.info(
            "SignalFailureController: %s fail=%.1f restore=%.1f severity=%s",
            section_id, fail_time, repair_time, severity,
        )

    # ── Stochastic scheduling ─────────────────────────────────────────────────

    def schedule_random_failures(
        self,
        section_ids: list[str],
        sim_start:   float = 360.0,
        sim_end:     float = 1440.0,
        num_failures: int  = 2,
    ) -> None:
        """
        Randomly place *num_failures* signal failures across *section_ids*
        within the sim window.
        """
        available = list(section_ids)
        for _ in range(min(num_failures, len(available))):
            section_id = self._rng.choice(available)
            available.remove(section_id)   # avoid double-failing same section

            fail_time   = self._rng.uniform(sim_start + 30, sim_end - 120)
            repair_min  = self._rng.randint(_REPAIR_MIN, _REPAIR_MAX)
            repair_time = fail_time + repair_min
            severity    = self._rng.choice(["partial", "full"])

            self.schedule_failure(section_id, fail_time, repair_time, severity)

    # ── Generate events ───────────────────────────────────────────────────────

    def generate_events(self) -> list[Event]:
        return sorted(self._events, key=lambda e: e.sim_time)


# ── Canonical demo scenario ───────────────────────────────────────────────────

def etawah_signal_failure(fail_time: float = 660.0, repair_time: float = 720.0) -> list[Event]:
    """
    Demo: signal failure at Etawah section at 11:00, restored at 12:00.
    """
    ctrl = SignalFailureController()
    ctrl.schedule_failure(
        section_id  = "ETW_PFD_UP",
        fail_time   = fail_time,
        repair_time = repair_time,
        severity    = "full",
    )
    return ctrl.generate_events()
