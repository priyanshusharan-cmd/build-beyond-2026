from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import math
from blackout_arena.invariants import check_tick


# Constant agents defined locally
AGENTS = ("hospital", "water", "telecom", "emergency")


def _to_finite(x: float) -> float:
    """Convert NaN/inf/negative to 0.0"""
    if not isinstance(x, float) or not math.isfinite(x) or x < 0:
        return 0.0
    return x


def _sum_finite(d: dict[str, float]) -> float:
    """Sum only finite values in dict"""
    return sum(v for v in d.values() if isinstance(v, float) and math.isfinite(v))


def fallback_split(
    supply: float,
    weights: dict[str, float],
    floors: dict[str, float],
    caps: dict[str, float],
    priority: list[str],
) -> dict[str, float]:
    """Deterministic water-filling fallback allocation."""
    # Build output keys: priority order first (filtered to caps keys), then remaining caps keys sorted
    caps_keys = set(caps.keys())
    priority_filtered = [a for a in priority if a in caps_keys]
    remaining_keys = sorted(caps_keys - set(priority_filtered))
    output_keys = priority_filtered + remaining_keys

    # Sanitize inputs
    supply = _to_finite(supply)
    if supply <= 0:
        return {k: 0.0 for k in output_keys}

    # Prepare sanitized dicts for all output keys
    eff_weights = {k: _to_finite(weights.get(k, 0.0)) for k in output_keys}
    eff_floors = {k: _to_finite(floors.get(k, 0.0)) for k in output_keys}
    eff_caps = {k: _to_finite(caps.get(k, 0.0)) for k in output_keys}

    # Effective floors = min(max(floor, 0), cap)
    eff_floors = {k: min(max(f, 0.0), eff_caps[k]) for k, f in eff_floors.items()}

    total_floors = sum(eff_floors.values())

    grants: dict[str, float] = {}

    if total_floors <= supply:
        # Grant floors first
        for k in output_keys:
            grants[k] = eff_floors[k]

        remaining = supply - total_floors

        # Water-filling on agents with weight > 0 and grant < cap
        active = {k for k in output_keys if eff_weights[k] > 0 and grants[k] < eff_caps[k]}

        # At most n+1 iterations
        for _ in range(len(output_keys) + 1):
            if not active:
                break

            total_weight = sum(eff_weights[k] for k in active)
            if total_weight <= 0:
                break

            # Compute shares
            shares = {k: remaining * eff_weights[k] / total_weight for k in active}

            # Check if any agent hits cap
            hit_cap = {k for k in active if shares[k] >= eff_caps[k] - grants[k] - 1e-12}

            if hit_cap:
                # Those agents get exactly their cap
                for k in hit_cap:
                    grants[k] = eff_caps[k]
                remaining = supply - sum(grants.values())
                active = {k for k in active if k not in hit_cap}
            else:
                # No one hits cap, assign shares and stop
                for k in active:
                    grants[k] += shares[k]
                remaining = 0.0
                break

        # Remainder left unallocated (do not invent allocation)
    else:
        # Truncate: iterate priority order then remaining sorted
        remaining_supply = supply
        for k in output_keys:
            grant = min(eff_floors[k], remaining_supply)
            grants[k] = grant
            remaining_supply -= grant

    # Final safety: clamp to [0, cap]
    for k in output_keys:
        grants[k] = max(0.0, min(grants[k], eff_caps[k]))

    # If sum still exceeds supply, scale down
    total_grants = sum(grants.values())
    if total_grants > supply + 1e-12:
        scale = supply / total_grants
        for k in output_keys:
            grants[k] *= scale

    # If still exceeds due to float, subtract excess from reverse priority
    total_grants = sum(grants.values())
    if total_grants > supply:
        excess = total_grants - supply
        # Reverse priority: remaining_keys reversed, then priority_filtered reversed
        reverse_order = list(reversed(remaining_keys)) + list(reversed(priority_filtered))
        for k in reverse_order:
            if excess <= 0:
                break
            reduction = min(grants[k], excess)
            grants[k] -= reduction
            excess -= reduction

    return {k: float(grants[k]) for k in output_keys}


@dataclass
class ProposalResult:
    ok: bool
    reasons: list[str]
    events: list[tuple[str, str | None, dict]]
    proposal_id: int | None = None
    committed: bool = False


class Ledger:
    def __init__(self, max_draw: dict[str, float]):
        self._max_draw = dict(max_draw)
        self._grants = {agent: 0.0 for agent in max_draw}
        self._history: list[dict] = []
        self._proposal_counter = 0
        # Track validated proposals: proposal_id -> (tick, grants, supply)
        self._validated: dict[int, tuple[int, dict[str, float], float]] = {}
        # Track committed proposals
        self._committed: set[int] = set()

    @property
    def grants(self) -> dict[str, float]:
        return dict(self._grants)

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    @property
    def max_draw(self) -> dict[str, float]:
        return dict(self._max_draw)

    def propose(
        self, tick: int, supply: float, grants: dict[str, float]
    ) -> ProposalResult:
        self._proposal_counter += 1
        proposal_id = self._proposal_counter

        # Copy grants to never mutate caller's dict
        grants_copy = dict(grants)

        # Start events with PROPOSE
        events: list[tuple[str, str | None, dict]] = [
            ("PROPOSE", None, {"supply": supply, "grants": grants_copy, "proposal_id": proposal_id})
        ]

        reasons: list[str] = []

        # Check partial proposal
        if set(grants_copy.keys()) != set(self._max_draw.keys()):
            reasons.append("partial_proposal")

        # Run invariant checks
        violations = check_tick(tick, supply, grants_copy, self._max_draw)
        for v in violations:
            reasons.append(f"{v.code}:{v.message}")

        if not reasons:
            # Validated
            events.append(
                ("VALIDATED", None, {"supply": supply, "grants": grants_copy, "proposal_id": proposal_id})
            )
            self._validated[proposal_id] = (tick, grants_copy, supply)
            self._history.append({
                "kind": "propose",
                "tick": tick,
                "proposal_id": proposal_id,
                "supply": supply,
                "grants": grants_copy,
            })
            self._history.append({
                "kind": "validated",
                "tick": tick,
                "proposal_id": proposal_id,
            })
            return ProposalResult(ok=True, reasons=[], events=events, proposal_id=proposal_id)
        else:
            # Rejected
            events.append(
                ("REJECTED", None, {"reasons": reasons, "proposal_id": proposal_id})
            )
            self._history.append({
                "kind": "propose",
                "tick": tick,
                "proposal_id": proposal_id,
                "supply": supply,
                "grants": grants_copy,
            })
            self._history.append({
                "kind": "reject",
                "tick": tick,
                "proposal_id": proposal_id,
                "reasons": reasons,
            })
            return ProposalResult(ok=False, reasons=reasons, events=events, proposal_id=proposal_id)

    def commit(self, tick: int, proposal_id: int) -> tuple[bool, list[tuple[str, str | None, dict]]]:
        # Check if proposal exists and is validated
        if proposal_id not in self._validated:
            return False, []

        prop_tick, prop_grants, prop_supply = self._validated[proposal_id]

        # Check tick match
        if prop_tick != tick:
            return False, []

        # Check not already committed
        if proposal_id in self._committed:
            return False, []

        # Apply grants atomically
        self._grants = dict(prop_grants)
        self._committed.add(proposal_id)

        # Record commit event
        event = ("COMMIT", None, {"supply": prop_supply, "grants": dict(prop_grants), "proposal_id": proposal_id})
        self._history.append({
            "kind": "commit",
            "tick": tick,
            "proposal_id": proposal_id,
            "supply": prop_supply,
            "grants": dict(prop_grants),
        })

        return True, [event]

    def submit(self, tick: int, supply: float, grants: dict[str, float]) -> ProposalResult:
        result = self.propose(tick, supply, grants)
        if result.ok and result.proposal_id is not None:
            success, commit_events = self.commit(tick, result.proposal_id)
            if success:
                result.events.extend(commit_events)
                result.committed = True
            else:
                result.ok = False
                result.committed = False
        return result

    def commit_fallback(
        self, tick: int, supply: float, grants: dict[str, float]
    ) -> ProposalResult:
        # Validate same as propose
        result = self.propose(tick, supply, grants)

        if result.ok and result.proposal_id is not None:
            # Add FALLBACK event with fallback=True
            fallback_event = (
                "FALLBACK",
                None,
                {"supply": supply, "grants": dict(grants), "fallback": True, "proposal_id": result.proposal_id},
            )
            result.events.append(fallback_event)
            self._history.append({
                "kind": "fallback",
                "tick": tick,
                "proposal_id": result.proposal_id,
                "supply": supply,
                "grants": dict(grants),
            })

            # Then COMMIT
            success, commit_events = self.commit(tick, result.proposal_id)
            if success:
                result.events.extend(commit_events)
                result.committed = True
            else:
                result.ok = False
                result.committed = False
        # If not ok, events already have PROPOSE, REJECTED from propose

        return result