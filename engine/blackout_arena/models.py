"""Frozen contracts (CLAUDE.md section 7): events and UI snapshot."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel

AGENTS = ("hospital", "water", "telecom", "emergency")


class EventType(str, Enum):
    SUPPLY_UPDATE = "SUPPLY_UPDATE"
    CHAOS_INJECTED = "CHAOS_INJECTED"
    PRICE_BROADCAST = "PRICE_BROADCAST"
    BID = "BID"
    OFFER = "OFFER"
    COUNTER = "COUNTER"
    CONCESSION = "CONCESSION"
    CREDIT_UPDATE = "CREDIT_UPDATE"
    PROPOSE = "PROPOSE"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    COMMIT = "COMMIT"
    FALLBACK = "FALLBACK"
    DAMAGE_TICK = "DAMAGE_TICK"
    CASCADE_TRIGGERED = "CASCADE_TRIGGERED"
    TICK_SUMMARY = "TICK_SUMMARY"
    EXPLANATION = "EXPLANATION"


class Event(BaseModel):
    seq: int
    tick: int
    t: str
    type: EventType
    agent: str | None
    payload: dict[str, Any]


class Snapshot(BaseModel):
    tick: int
    supply: float
    grants: dict[str, float]
    need: dict[str, float]
    served_pct: dict[str, float]
    damage_cum: float
    jain: float
    cascades: int
    credits: dict[str, float]
    status: dict[str, str]  # ok | degraded | down


def tick_to_hhmm(tick: int) -> str:
    """1 tick = 1 simulated minute."""
    return f"{tick // 60:02d}:{tick % 60:02d}"
