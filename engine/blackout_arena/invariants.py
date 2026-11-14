from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import math


@dataclass(frozen=True)
class Violation:
    code: str
    tick: int
    message: str


def _is_finite(x: float) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _is_nan(x: float) -> bool:
    return isinstance(x, (int, float)) and math.isnan(x)


def check_tick(
    tick: int,
    supply: float,
    grants: dict[str, float],
    max_draw: dict[str, float],
    tol: float = 1e-6,
) -> list[Violation]:
    violations: list[Violation] = []

    # INV-1: sum(grants) <= supply
    # Only sum finite values; NaN/inf will be caught by INV-2
    total_grants = sum(v for v in grants.values() if _is_finite(v))
    if _is_nan(supply) or total_grants > supply + tol:
        violations.append(
            Violation("INV-1", tick, f"sum(grants)={total_grants} > supply={supply}")
        )

    # INV-2: per-agent checks
    all_agents = set(max_draw.keys())
    grants_keys = set(grants.keys())

    # Unknown agents in grants
    for agent in sorted(grants_keys - all_agents):
        violations.append(
            Violation("INV-2", tick, f"unknown agent in grants: {agent}")
        )

    # Check each agent in max_draw (deterministic sorted order)
    for agent in sorted(all_agents):
        max_d = max_draw[agent]

        if agent not in grants:
            violations.append(
                Violation("INV-2", tick, f"missing grant for agent: {agent}")
            )
            continue

        grant = grants[agent]

        if _is_nan(grant) or not _is_finite(grant):
            violations.append(
                Violation("INV-2", tick, f"non-finite grant for {agent}: {grant}")
            )
            continue

        if grant < -tol:
            violations.append(
                Violation("INV-2", tick, f"grant < 0 for {agent}: {grant}")
            )

        if grant > max_d + tol:
            violations.append(
                Violation("INV-2", tick, f"grant > max_draw for {agent}: {grant} > {max_d}")
            )

    return violations


def check_atomic(
    tick: int,
    prev: dict[str, float],
    proposed: dict[str, float],
    after: dict[str, float],
) -> list[Violation]:
    violations: list[Violation] = []

    # Must equal exactly prev OR exactly proposed (same keys and values, exact ==)
    if after != prev and after != proposed:
        violations.append(
            Violation("INV-3", tick, "atomic commit violated: after state is neither prev nor proposed")
        )

    return violations


def check_event_order(events: list[dict]) -> list[Violation]:
    violations: list[Violation] = []

    # Sort by seq
    sorted_events = sorted(events, key=lambda e: e["seq"])

    # Track pending validations per tick
    pending: dict[int, bool] = {}

    for ev in sorted_events:
        tick = ev["tick"]
        etype = ev["type"]

        if etype == "PROPOSE":
            # New proposal resets pending
            pending[tick] = False
        elif etype == "VALIDATED":
            # Validated sets pending true
            pending[tick] = True
        elif etype == "REJECTED":
            # Rejected cancels pending
            pending[tick] = False
        elif etype == "FALLBACK":
            # FALLBACK with fallback=True sets pending
            if ev.get("payload", {}).get("fallback") is True:
                pending[tick] = True
            # FALLBACK without fallback=true does nothing
        elif etype == "COMMIT":
            if not pending.get(tick, False):
                violations.append(
                    Violation("INV-4", tick, "COMMIT without prior VALIDATED or FALLBACK(fallback=True)")
                )
            else:
                pending[tick] = False

    return violations