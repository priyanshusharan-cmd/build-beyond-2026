"""Append-only event log (JSONL), deterministic serialization."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Event, EventType, tick_to_hhmm


def _round(obj: Any) -> Any:
    if isinstance(obj, float):
        r = round(obj, 6)
        return 0.0 if r == 0 else r  # normalise -0.0
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v) for v in obj]
    return obj


class EventLog:
    def __init__(self) -> None:
        self.events: list[Event] = []

    def append(self, tick: int, type: EventType, agent: str | None, payload: dict) -> Event:
        ev = Event(
            seq=len(self.events),
            tick=tick,
            t=tick_to_hhmm(tick),
            type=EventType(type),
            agent=agent,
            payload=_round(payload),
        )
        self.events.append(ev)
        return ev

    def from_seq(self, n: int) -> list[Event]:
        return self.events[max(0, n):]

    @staticmethod
    def event_dict(ev: Event) -> dict:
        return {
            "seq": ev.seq,
            "tick": ev.tick,
            "t": ev.t,
            "type": ev.type.value,
            "agent": ev.agent,
            "payload": ev.payload,
        }

    def to_jsonl(self) -> str:
        lines = [
            json.dumps(self.event_dict(e), sort_keys=True, separators=(",", ":"))
            for e in self.events
        ]
        return "\n".join(lines) + ("\n" if lines else "")

    def write(self, path: str | Path) -> None:
        Path(path).write_text(self.to_jsonl(), encoding="utf-8", newline="\n")

    @classmethod
    def read(cls, path: str | Path) -> "EventLog":
        log = cls()
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                log.events.append(Event(**json.loads(line)))
        return log
