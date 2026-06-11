"""
Discrete Event Simulation Engine
=================================
A priority-queue-based DES engine. Events are processed in strict
(sim_time, priority, sequence) order. Each event handler is a callable
registered for one or more EventTypes.

Design principles
-----------------
* Single-threaded: event processing is deterministic and reproducible.
* Handlers may schedule new events by calling ``engine.schedule()``.
* The engine does NOT own state — it only drives the event loop.
  State lives in StateManager; handlers close over it.
* Configurable termination: wall-clock timeout OR sim-time limit OR sentinel event.
"""

from __future__ import annotations

import heapq
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Optional

from .clock import SimClock
from .event_types import Event, EventType, make_event

logger = logging.getLogger(__name__)

# Handler signature: (engine, event) → None
Handler = Callable[["EventEngine", Event], None]


@dataclass
class EngineStats:
    """Running statistics collected by the engine."""
    events_processed: int = 0
    events_skipped: int   = 0
    handler_errors: int   = 0
    max_queue_depth: int  = 0
    run_start_wall: float = field(default_factory=time.monotonic)

    @property
    def wall_elapsed(self) -> float:
        return time.monotonic() - self.run_start_wall


class EventEngine:
    """
    Core DES event loop.

    Usage
    -----
    >>> engine = EventEngine(clock=SimClock(start_minutes=360.0))
    >>> engine.register(EventType.TRAIN_DEPART, my_handler)
    >>> engine.schedule(make_event(EventType.TRAIN_DEPART, 360.0, payload))
    >>> engine.run(until_sim_time=480.0)
    """

    def __init__(
        self,
        clock: SimClock,
        max_events: int = 500_000,
        tick_interval_min: float = 1.0,
        on_tick: Optional[Callable[[float], None]] = None,
    ) -> None:
        """
        Parameters
        ----------
        clock:
            SimClock instance shared with the rest of the simulation.
        max_events:
            Safety cap on total events processed (prevents infinite loops).
        tick_interval_min:
            How often TICK events fire (sim-minutes).  Set to 0 to disable.
        on_tick:
            Optional callback called with current sim_time on each TICK.
        """
        self._clock       = clock
        self._max_events  = max_events
        self._tick_interval = tick_interval_min
        self._on_tick     = on_tick

        self._queue: list[Event] = []          # heapq (min-heap)
        self._handlers: dict[EventType, list[Handler]] = defaultdict(list)
        self._stats   = EngineStats()
        self._running = False
        self._paused  = False

        # Register built-in TICK handler
        if tick_interval_min > 0:
            self.register(EventType.TICK, self._handle_tick)

    # ── Handler registration ──────────────────────────────────────────────────

    def register(self, event_type: EventType, handler: Handler) -> None:
        """Register a handler for an event type. Multiple handlers allowed."""
        self._handlers[event_type].append(handler)
        logger.debug("Registered handler for %s: %s", event_type.name, handler.__name__)

    def unregister(self, event_type: EventType, handler: Handler) -> None:
        """Remove a specific handler."""
        try:
            self._handlers[event_type].remove(handler)
        except ValueError:
            pass

    # ── Event scheduling ──────────────────────────────────────────────────────

    def schedule(self, event: Event) -> None:
        """Push an event onto the priority queue."""
        if event.sim_time < self._clock.now:
            logger.warning(
                "Scheduling event in the past: %s (now=%.2f, event=%.2f)",
                event.event_type.name, self._clock.now, event.sim_time,
            )
        heapq.heappush(self._queue, event)
        depth = len(self._queue)
        if depth > self._stats.max_queue_depth:
            self._stats.max_queue_depth = depth

    def schedule_many(self, events: list[Event]) -> None:
        """Schedule a batch of events."""
        for e in events:
            self.schedule(e)

    def peek_next_time(self) -> Optional[float]:
        """Return the sim_time of the next queued event without consuming it."""
        return self._queue[0].sim_time if self._queue else None

    @property
    def queue_depth(self) -> int:
        return len(self._queue)

    # ── Main event loop ───────────────────────────────────────────────────────

    def run(
        self,
        until_sim_time: Optional[float] = None,
        wall_timeout_seconds: Optional[float] = None,
    ) -> EngineStats:
        """
        Process events until one of the termination conditions is met:

        1. Queue is empty.
        2. Next event's sim_time > ``until_sim_time``.
        3. ``wall_timeout_seconds`` exceeded.
        4. ``max_events`` processed.
        5. A ``SIMULATION_END`` event is dequeued.
        6. ``engine.stop()`` is called from a handler.

        Returns engine statistics.
        """
        if self._running:
            raise RuntimeError("EventEngine is already running")

        self._running = True
        self._paused  = False
        self._stats   = EngineStats()
        wall_deadline = (
            time.monotonic() + wall_timeout_seconds
            if wall_timeout_seconds else float("inf")
        )
        sim_deadline = until_sim_time if until_sim_time is not None else float("inf")

        logger.info(
            "EventEngine starting: sim=%s, until=%.1f, queue=%d",
            self._clock.now_hhmm(), sim_deadline, len(self._queue),
        )

        try:
            while self._queue and self._running:
                # Wall-clock timeout guard
                if time.monotonic() > wall_deadline:
                    logger.warning("EventEngine: wall-clock timeout reached")
                    break

                # Max-events guard
                if self._stats.events_processed >= self._max_events:
                    logger.warning("EventEngine: max_events cap reached (%d)", self._max_events)
                    break

                # Peek at the next event
                next_event = self._queue[0]

                # Sim-time deadline check
                if next_event.sim_time > sim_deadline:
                    logger.info(
                        "EventEngine: sim deadline %.1f reached at event time %.1f",
                        sim_deadline, next_event.sim_time,
                    )
                    break

                # Consume the event
                event = heapq.heappop(self._queue)

                # Advance the simulation clock
                if event.sim_time > self._clock.now:
                    self._clock.jump_to(event.sim_time)

                # Terminal event
                if event.event_type == EventType.SIMULATION_END:
                    logger.info("EventEngine: SIMULATION_END event received")
                    self._running = False
                    break

                # Dispatch to handlers
                self._dispatch(event)

        finally:
            self._running = False

        logger.info(
            "EventEngine finished: processed=%d, errors=%d, wall=%.2fs, "
            "sim_elapsed=%.1fmin, queue_remaining=%d",
            self._stats.events_processed,
            self._stats.handler_errors,
            self._stats.wall_elapsed,
            self._clock.elapsed_sim_minutes,
            len(self._queue),
        )
        return self._stats

    def stop(self) -> None:
        """Signal the event loop to stop after the current handler returns."""
        self._running = False

    def pause(self) -> None:
        """Pause execution (cooperative — checked between events)."""
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    # ── Dispatch ──────────────────────────────────────────────────────────────

    def _dispatch(self, event: Event) -> None:
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            logger.debug("No handler for %s — skipping", event.event_type.name)
            self._stats.events_skipped += 1
            return

        self._stats.events_processed += 1
        for handler in handlers:
            try:
                handler(self, event)
            except Exception:
                self._stats.handler_errors += 1
                logger.exception(
                    "Handler %s raised for event %s",
                    handler.__name__, event,
                )

    # ── Built-in TICK handler ─────────────────────────────────────────────────

    def _handle_tick(self, engine: "EventEngine", event: Event) -> None:
        payload = event.payload
        if self._on_tick:
            try:
                self._on_tick(payload.sim_time_min)
            except Exception:
                logger.exception("on_tick callback raised")

        # Schedule next tick
        next_tick_time = event.sim_time + self._tick_interval
        from .event_types import TickPayload
        engine.schedule(make_event(
            EventType.TICK,
            next_tick_time,
            TickPayload(tick_number=payload.tick_number + 1, sim_time_min=next_tick_time),
        ))

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def stats(self) -> EngineStats:
        return self._stats

    @property
    def clock(self) -> SimClock:
        return self._clock

    @property
    def is_running(self) -> bool:
        return self._running

    def __repr__(self) -> str:
        return (
            f"EventEngine(sim={self._clock.now_hhmm()}, "
            f"queue={len(self._queue)}, "
            f"processed={self._stats.events_processed})"
        )
