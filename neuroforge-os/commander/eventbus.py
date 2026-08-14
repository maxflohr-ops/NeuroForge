#!/usr/bin/env python3
"""
Event Bus
=========
Every state change in the fleet becomes an event: a run starts, an agent
begins a stage, a line is logged, a QA score lands. Events carry a monotonic
sequence number so a browser that reconnects can ask for everything after the
last one it saw instead of losing history.

Events are held in a ring buffer for replay and appended to a JSONL file so a
restarted commander still has the mission record.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Iterator

# Event types, kept as constants so typos surface at import time.
RUN_QUEUED = "run.queued"
RUN_STARTED = "run.started"
RUN_LOG = "run.log"
RUN_FINISHED = "run.finished"
RUN_CANCELLED = "run.cancelled"
STAGE_STARTED = "stage.started"
STAGE_FINISHED = "stage.finished"
ARTIFACT = "artifact"
METRIC = "metric"
FLEET = "fleet"


class EventBus:
    """Thread-safe fan-out with replay. One instance per commander process."""

    def __init__(self, log_path: Path | None = None, capacity: int = 4000):
        self._lock = threading.Lock()
        self._seq = 0
        self._capacity = capacity
        self._buffer: list[dict[str, Any]] = []
        self._subscribers: set[queue.Queue] = set()
        self._log_path = log_path
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)

    # ── publishing ────────────────────────────────────────────────────────

    def publish(self, type: str, **payload: Any) -> dict[str, Any]:
        """Record an event and hand it to every live subscriber."""
        with self._lock:
            self._seq += 1
            event = {
                "seq": self._seq,
                "ts": time.time(),
                "type": type,
                **payload,
            }
            self._buffer.append(event)
            if len(self._buffer) > self._capacity:
                del self._buffer[: len(self._buffer) - self._capacity]
            subscribers = list(self._subscribers)

        self._append_to_log(event)

        for sub in subscribers:
            try:
                sub.put_nowait(event)
            except queue.Full:
                # A subscriber that cannot keep up is dropped rather than
                # allowed to stall the agent it is watching.
                with self._lock:
                    self._subscribers.discard(sub)
        return event

    def _append_to_log(self, event: dict[str, Any]) -> None:
        if not self._log_path:
            return
        try:
            with open(self._log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, default=str) + "\n")
        except OSError:
            # Telemetry must never take the fleet down.
            pass

    # ── subscribing ───────────────────────────────────────────────────────

    def subscribe(self, maxsize: int = 1000) -> queue.Queue:
        sub: queue.Queue = queue.Queue(maxsize=maxsize)
        with self._lock:
            self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(sub)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    # ── replay ────────────────────────────────────────────────────────────

    def replay(self, since_seq: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        """Buffered events newer than since_seq, oldest first."""
        with self._lock:
            newer = [e for e in self._buffer if e["seq"] > since_seq]
        return newer[-limit:]

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    def stream(self, since_seq: int = 0, heartbeat: float = 15.0) -> Iterator[dict[str, Any]]:
        """Yield replayed events, then live ones, then periodic heartbeats.

        Heartbeats keep proxies from closing an idle connection and give the
        client a way to notice the commander went away.
        """
        sub = self.subscribe()
        try:
            backlog = self.replay(since_seq)
            seen = since_seq
            for event in backlog:
                seen = event["seq"]
                yield event

            while True:
                try:
                    event = sub.get(timeout=heartbeat)
                except queue.Empty:
                    yield {"type": "heartbeat", "seq": seen, "ts": time.time()}
                    continue
                if event["seq"] <= seen:
                    continue
                seen = event["seq"]
                yield event
        finally:
            self.unsubscribe(sub)
