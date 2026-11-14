"""Baseline allocators (CLAUDE.md section 4). Each takes the same inputs and returns grants.

These have no ledger/negotiation: they are what the independent checker is run against.
"""
from __future__ import annotations

PRIORITY_ORDER = ["hospital", "emergency", "telecom", "water"]
STRATEGIES = ("ours", "blind", "proportional", "priority")
# Ablations of our system (same engine, features switched off). Not part of the default compare.
ABLATIONS = ("ours_no_l2", "ours_no_credit")
OURS_FAMILY = ("ours",) + ABLATIONS


def blind_request(caps: dict[str, float]) -> dict[str, float]:
    """Blind grab: every agent requests its full need (capped at max_draw), independently."""
    return dict(caps)


def curtail_proportional(requests: dict[str, float], supply: float) -> dict[str, float]:
    total = sum(requests.values())
    if total <= supply or total <= 0:
        return dict(requests)
    f = max(0.0, supply) / total
    return {a: q * f for a, q in requests.items()}


def proportional_allocate(caps: dict[str, float], supply: float) -> dict[str, float]:
    """served_i = need_i * min(1, S/D)."""
    return curtail_proportional(caps, supply)


def priority_allocate(
    caps: dict[str, float], supply: float, order: list[str] | None = None
) -> dict[str, float]:
    """Static priority: satisfy in fixed ranking."""
    order = order or PRIORITY_ORDER
    remaining = max(0.0, supply)
    out = {a: 0.0 for a in caps}
    for a in order:
        if a in caps:
            g = min(caps[a], remaining)
            out[a] = g
            remaining -= g
    return out
