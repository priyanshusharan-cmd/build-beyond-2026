from __future__ import annotations
import math
import pytest
from hypothesis import given, settings, strategies as st, assume, example
from typing import Iterable

from blackout_arena.invariants import (
    Violation,
    check_tick,
    check_atomic,
    check_event_order,
)
from blackout_arena.ledger import (
    fallback_split,
    Ledger,
    ProposalResult,
    AGENTS,
)


# Test max_draw fixture
MAX_DRAW = {"hospital": 38, "water": 24, "telecom": 14, "emergency": 16}


# ============================================================
# Basic invariant checker tests
# ============================================================

def test_check_tick_basic():
    supply = 100.0
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert violations == []


def test_check_tick_inv1_overshoot():
    supply = 50.0
    grants = {"hospital": 30.0, "water": 30.0, "telecom": 10.0, "emergency": 10.0}
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert any(v.code == "INV-1" for v in violations)


def test_check_tick_inv2_negative():
    supply = 100.0
    grants = {"hospital": -5.0, "water": 20.0, "telecom": 20.0, "emergency": 20.0}
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert any(v.code == "INV-2" and "grant < 0" in v.message for v in violations)


def test_check_tick_inv2_over_max():
    supply = 100.0
    grants = {"hospital": 50.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert any(v.code == "INV-2" and "grant > max_draw" in v.message for v in violations)


def test_check_tick_inv2_nan():
    supply = 100.0
    grants = {"hospital": float("nan"), "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert any(v.code == "INV-2" and "non-finite" in v.message for v in violations)


def test_check_tick_inv2_missing():
    supply = 100.0
    grants = {"water": 20.0, "telecom": 14.0, "emergency": 16.0}
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert any(v.code == "INV-2" and "missing grant" in v.message for v in violations)


def test_check_tick_inv2_unknown_agent():
    supply = 100.0
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 20.0, "emergency": 20.0, "unknown": 10.0}
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert any(v.code == "INV-2" and "unknown agent" in v.message for v in violations)


def test_check_tick_nan_supply():
    supply = float("nan")
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 20.0, "emergency": 20.0}
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert any(v.code == "INV-1" for v in violations)


def test_check_atomic_accept():
    prev = {"hospital": 10.0, "water": 10.0}
    proposed = {"hospital": 20.0, "water": 20.0}
    after = {"hospital": 20.0, "water": 20.0}
    violations = check_atomic(1, prev, proposed, after)
    assert violations == []


def test_check_atomic_reject():
    prev = {"hospital": 10.0, "water": 10.0}
    proposed = {"hospital": 20.0, "water": 20.0}
    after = {"hospital": 10.0, "water": 10.0}
    violations = check_atomic(1, prev, proposed, after)
    assert violations == []


def test_check_atomic_partial():
    prev = {"hospital": 10.0, "water": 10.0}
    proposed = {"hospital": 20.0, "water": 20.0}
    after = {"hospital": 20.0, "water": 10.0}
    violations = check_atomic(1, prev, proposed, after)
    assert any(v.code == "INV-3" for v in violations)


def test_check_atomic_extra_keys():
    prev = {"hospital": 10.0}
    proposed = {"hospital": 20.0}
    after = {"hospital": 20.0, "water": 5.0}
    violations = check_atomic(1, prev, proposed, after)
    assert any(v.code == "INV-3" for v in violations)


def test_check_event_order_valid():
    events = [
        {"seq": 1, "tick": 1, "t": "00:00", "type": "PROPOSE", "agent": None, "payload": {}},
        {"seq": 2, "tick": 1, "t": "00:00", "type": "VALIDATED", "agent": None, "payload": {}},
        {"seq": 3, "tick": 1, "t": "00:00", "type": "COMMIT", "agent": None, "payload": {}},
    ]
    violations = check_event_order(events)
    assert violations == []


def test_check_event_order_commit_without_validated():
    events = [
        {"seq": 1, "tick": 1, "t": "00:00", "type": "PROPOSE", "agent": None, "payload": {}},
        {"seq": 2, "tick": 1, "t": "00:00", "type": "COMMIT", "agent": None, "payload": {}},
    ]
    violations = check_event_order(events)
    assert any(v.code == "INV-4" for v in violations)


def test_check_event_order_rejected_cancels():
    events = [
        {"seq": 1, "tick": 1, "t": "00:00", "type": "PROPOSE", "agent": None, "payload": {}},
        {"seq": 2, "tick": 1, "t": "00:00", "type": "VALIDATED", "agent": None, "payload": {}},
        {"seq": 3, "tick": 1, "t": "00:00", "type": "REJECTED", "agent": None, "payload": {}},
        {"seq": 4, "tick": 1, "t": "00:00", "type": "COMMIT", "agent": None, "payload": {}},
    ]
    violations = check_event_order(events)
    assert any(v.code == "INV-4" for v in violations)


def test_check_event_order_fallback_true():
    events = [
        {"seq": 1, "tick": 1, "t": "00:00", "type": "PROPOSE", "agent": None, "payload": {}},
        {"seq": 2, "tick": 1, "t": "00:00", "type": "VALIDATED", "agent": None, "payload": {}},
        {"seq": 3, "tick": 1, "t": "00:00", "type": "FALLBACK", "agent": None, "payload": {"fallback": True}},
        {"seq": 4, "tick": 1, "t": "00:00", "type": "COMMIT", "agent": None, "payload": {}},
    ]
    violations = check_event_order(events)
    assert violations == []


def test_check_event_order_fallback_false_does_nothing():
    # FALLBACK with fallback=False does nothing - VALIDATED still active, COMMIT valid
    events = [
        {"seq": 1, "tick": 1, "t": "00:00", "type": "PROPOSE", "agent": None, "payload": {}},
        {"seq": 2, "tick": 1, "t": "00:00", "type": "VALIDATED", "agent": None, "payload": {}},
        {"seq": 3, "tick": 1, "t": "00:00", "type": "FALLBACK", "agent": None, "payload": {"fallback": False}},
        {"seq": 4, "tick": 1, "t": "00:00", "type": "COMMIT", "agent": None, "payload": {}},
    ]
    violations = check_event_order(events)
    assert violations == []


def test_check_event_order_propose_resets():
    events = [
        {"seq": 1, "tick": 1, "t": "00:00", "type": "PROPOSE", "agent": None, "payload": {}},
        {"seq": 2, "tick": 1, "t": "00:00", "type": "VALIDATED", "agent": None, "payload": {}},
        {"seq": 3, "tick": 1, "t": "00:00", "type": "PROPOSE", "agent": None, "payload": {}},
        {"seq": 4, "tick": 1, "t": "00:00", "type": "COMMIT", "agent": None, "payload": {}},
    ]
    violations = check_event_order(events)
    assert any(v.code == "INV-4" for v in violations)


# ============================================================
# Ledger tests
# ============================================================

def test_over_capacity_rejected():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 38, "water": 24, "telecom": 14, "emergency": 16}  # sum = 92
    # supply 90, grants sum 92 -> over capacity
    result = ledger.propose(1, 90.0, grants)
    assert result.ok is False
    assert any(e[0] == "REJECTED" for e in result.events)
    assert ledger.grants == {a: 0.0 for a in MAX_DRAW}


def test_negative_grant_rejected():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": -1.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.propose(1, 100.0, grants)
    assert result.ok is False
    assert any(e[0] == "REJECTED" for e in result.events)
    assert ledger.grants == {a: 0.0 for a in MAX_DRAW}


def test_over_max_draw_rejected():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 50.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.propose(1, 100.0, grants)
    assert result.ok is False
    assert any(e[0] == "REJECTED" for e in result.events)
    assert ledger.grants == {a: 0.0 for a in MAX_DRAW}


def test_nan_grant_rejected():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": float("nan"), "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.propose(1, 100.0, grants)
    assert result.ok is False
    assert any(e[0] == "REJECTED" for e in result.events)
    assert ledger.grants == {a: 0.0 for a in MAX_DRAW}


def test_partial_proposal_rejected():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0}  # missing telecom, emergency
    result = ledger.propose(1, 100.0, grants)
    assert result.ok is False
    assert any("partial_proposal" in r for r in result.reasons)
    assert any(e[0] == "REJECTED" for e in result.events)
    assert ledger.grants == {a: 0.0 for a in MAX_DRAW}


def test_atomic_commit_all_or_none():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.propose(1, 100.0, grants)
    assert result.ok

    # Check before commit
    prev = ledger.grants
    success, events = ledger.commit(1, result.proposal_id)
    assert success
    after = ledger.grants

    # Use check_atomic
    violations = check_atomic(1, prev, grants, after)
    assert violations == []


def test_atomic_commit_rejected_unchanged():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 50.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}  # over max_draw
    result = ledger.propose(1, 100.0, grants)
    assert not result.ok

    prev = ledger.grants
    success, events = ledger.commit(1, result.proposal_id)
    assert not success
    after = ledger.grants

    # Should still be unchanged (prev == after)
    violations = check_atomic(1, prev, grants, after)
    assert violations == []


def test_commit_unvalidated_fails():
    ledger = Ledger(MAX_DRAW)
    success, events = ledger.commit(1, 999)  # unknown id
    assert not success
    assert events == []


def test_commit_unknown_id_fails():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.propose(1, 100.0, grants)
    # commit with wrong tick
    success, events = ledger.commit(2, result.proposal_id)
    assert not success


def test_commit_tick_mismatch_fails():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.propose(1, 100.0, grants)
    success, events = ledger.commit(2, result.proposal_id)
    assert not success
    assert ledger.grants == {a: 0.0 for a in MAX_DRAW}


def test_commit_double_commit_fails():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.propose(1, 100.0, grants)
    success1, events1 = ledger.commit(1, result.proposal_id)
    assert success1
    success2, events2 = ledger.commit(1, result.proposal_id)
    assert not success2


def test_submit_valid_proposal():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.submit(1, 100.0, grants)
    assert result.ok
    assert result.committed
    event_types = [e[0] for e in result.events]
    assert event_types == ["PROPOSE", "VALIDATED", "COMMIT"]


def test_submit_invalid_proposal():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 50.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.submit(1, 100.0, grants)
    assert not result.ok
    assert not result.committed
    event_types = [e[0] for e in result.events]
    assert event_types == ["PROPOSE", "REJECTED"]


def test_commit_fallback_emits_fallback():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.commit_fallback(1, 100.0, grants)
    assert result.ok
    assert result.committed
    event_types = [e[0] for e in result.events]
    assert event_types == ["PROPOSE", "VALIDATED", "FALLBACK", "COMMIT"]
    # Check FALLBACK has fallback=True
    fallback_event = [e for e in result.events if e[0] == "FALLBACK"][0]
    assert fallback_event[2].get("fallback") is True


def test_commit_fallback_invalid():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 50.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    result = ledger.commit_fallback(1, 100.0, grants)
    assert not result.ok
    event_types = [e[0] for e in result.events]
    assert event_types == ["PROPOSE", "REJECTED"]


def test_ledger_grants_is_copy():
    ledger = Ledger(MAX_DRAW)
    g = ledger.grants
    g["hospital"] = 999
    assert ledger.grants["hospital"] == 0.0


def test_ledger_max_draw_is_copy():
    ledger = Ledger(MAX_DRAW)
    m = ledger.max_draw
    m["hospital"] = 999
    assert ledger.max_draw["hospital"] == 38


def test_ledger_history_records():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    ledger.propose(1, 100.0, grants)
    assert any(h["kind"] == "propose" for h in ledger.history)
    assert any(h["kind"] == "validated" for h in ledger.history)


def test_ledger_never_modifies_input_grants():
    ledger = Ledger(MAX_DRAW)
    grants = {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0}
    original = dict(grants)
    ledger.propose(1, 100.0, grants)
    assert grants == original


# ============================================================
# fallback_split property tests (Hypothesis)
# ============================================================

# Strategies
st_supply = st.floats(min_value=-5.0, max_value=200.0, allow_nan=False, allow_infinity=False)
st_weight = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)
st_floor = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)
st_cap = st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False)
st_priority = st.permutations(list(AGENTS))


@settings(max_examples=1500, deadline=None)
@given(
    supply=st_supply,
    weights=st.fixed_dictionaries({a: st_weight for a in AGENTS}),
    floors=st.fixed_dictionaries({a: st_floor for a in AGENTS}),
    caps=st.fixed_dictionaries({a: st_cap for a in AGENTS}),
    priority=st_priority,
)
def test_fallback_split_properties(supply, weights, floors, caps, priority):
    grants = fallback_split(supply, weights, floors, caps, priority)

    # Keys == caps keys
    assert set(grants.keys()) == set(caps.keys())

    # All zero when supply <= 0
    if supply <= 0:
        for v in grants.values():
            assert v == 0.0
        return

    # 0 <= grant <= cap
    for a in AGENTS:
        assert 0.0 <= grants[a] <= caps[a] + 1e-9

    # sum <= supply (with exact float <=)
    total = sum(grants.values())
    assert total <= supply + 1e-9

    # Deterministic
    grants2 = fallback_split(supply, weights, floors, caps, priority)
    assert grants == grants2

    # Floors met when feasible
    eff_floors = {a: min(max(floors.get(a, 0.0), 0.0), caps[a]) for a in AGENTS}
    total_floors = sum(eff_floors.values())
    if total_floors <= supply:
        for a in AGENTS:
            assert grants[a] >= eff_floors[a] - 1e-9


@settings(max_examples=100, deadline=None)
@given(
    supply=st.floats(min_value=0.1, max_value=200.0, allow_nan=False, allow_infinity=False),
    weights=st.fixed_dictionaries({a: st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
    floors=st.fixed_dictionaries({a: st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
    caps=st.fixed_dictionaries({a: st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
    priority=st_priority,
)
def test_fallback_priority_truncation(supply, weights, floors, caps, priority):
    eff_floors = {a: min(max(floors.get(a, 0.0), 0.0), caps[a]) for a in AGENTS}
    total_floors = sum(eff_floors.values())
    
    assume(total_floors > supply)  # infeasible case
    
    grants = fallback_split(supply, weights, floors, caps, priority)
    
    # Should match sequential min(floor, remaining) in priority order
    remaining = supply
    expected = {}
    for a in priority:
        expected[a] = min(eff_floors[a], remaining)
        remaining -= expected[a]
    
    for a in AGENTS:
        assert grants[a] == pytest.approx(expected[a])


@settings(max_examples=10, deadline=None)
@given(
    supply=st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    weights=st.fixed_dictionaries({a: st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
    floors=st.fixed_dictionaries({a: st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
    caps=st.fixed_dictionaries({a: st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
    priority=st_priority,
)
@example(
    supply=100.0,
    weights={"hospital": 1.0, "water": 1.0, "telecom": 1.0, "emergency": 1.0},
    floors={"hospital": 10.0, "water": 10.0, "telecom": 10.0, "emergency": 10.0},
    caps={"hospital": 30.0, "water": 100.0, "telecom": 100.0, "emergency": 100.0},
    priority=["hospital", "water", "telecom", "emergency"],
)
def test_fallback_split_handwritten(supply, weights, floors, caps, priority):
    """Hand-written example: equal weights, one agent capped low -> leftover redistributed"""
    grants = fallback_split(supply, weights, floors, caps, priority)
    total = sum(grants.values())
    # Total should be <= supply
    assert total <= supply + 1e-9


# ============================================================
# check_tick property tests (Hypothesis)
# ============================================================

@settings(max_examples=500, deadline=None)
@given(
    supply=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    grants=st.fixed_dictionaries({a: st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
)
def test_check_tick_feasible_no_violations(supply, grants):
    # Scale grants so sum <= supply AND each grant <= max_draw
    clamped = {a: min(grants[a], MAX_DRAW[a]) for a in AGENTS}
    total = sum(clamped.values())
    if total > 0:
        scale = min(1.0, supply / total)
        clamped = {a: v * scale for a, v in clamped.items()}
    
    violations = check_tick(1, supply, clamped, MAX_DRAW)
    assert violations == []


@settings(max_examples=500, deadline=None)
@given(
    supply=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    grants=st.fixed_dictionaries({a: st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
)
def test_check_tick_overshoot_inv1(supply, grants):
    # Make grants sum > supply - ensure finite values and positive total
    total = sum(v for v in grants.values() if math.isfinite(v))
    assume(total > 1e-10)  # avoid subnormal issues
    # Scale up significantly to guarantee overshoot
    scale = (supply * 2 + 10.0) / total
    grants = {a: v * scale for a, v in grants.items()}
    
    violations = check_tick(1, supply, grants, MAX_DRAW)
    assert any(v.code == "INV-1" for v in violations)


# ============================================================
# Ledger fuzz test (Hypothesis)
# ============================================================

@settings(max_examples=1000, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.floats(min_value=-50.0, max_value=200.0, allow_nan=False, allow_infinity=False),
            st.fixed_dictionaries({a: st.floats(min_value=-50.0, max_value=100.0, allow_nan=False, allow_infinity=False) for a in AGENTS}),
        ),
        min_size=1,
        max_size=20,
    )
)
def test_ledger_fuzz(sequence):
    ledger = Ledger(MAX_DRAW)
    prev_grants = {a: 0.0 for a in MAX_DRAW}
    
    for tick, (supply, grants) in enumerate(sequence, 1):
        result = ledger.submit(tick, supply, grants)
        
        # Ledger grants is either previous state or exactly the submitted grants
        current = ledger.grants
        assert current == prev_grants or current == grants
        
        # If committed, check_tick passes for that submission
        if result.committed:
            violations = check_tick(tick, supply, grants, MAX_DRAW)
            assert violations == [], f"Committed but violations: {violations}"
        
        if result.committed:
            prev_grants = dict(current)


# ============================================================
# End-to-end event order test
# ============================================================

def test_end_to_end_event_order():
    """Turn ledger event tuples into event dicts with seq/tick/t and verify check_event_order"""
    ledger = Ledger(MAX_DRAW)
    all_events = []
    seq = 0
    
    def to_dict_events(tick: int, events: list[tuple], t: str = "00:00") -> list[dict]:
        nonlocal seq
        out = []
        for etype, agent, payload in events:
            seq += 1
            out.append({"seq": seq, "tick": tick, "t": t, "type": etype, "agent": agent, "payload": payload})
        return out
    
    # Mix of good, bad, fallback over many ticks
    # Tick 1: valid submit
    result = ledger.submit(1, 100.0, {"hospital": 20.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0})
    all_events.extend(to_dict_events(1, result.events))
    
    # Tick 2: invalid proposal (over max_draw)
    result = ledger.propose(2, 100.0, {"hospital": 50.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0})
    all_events.extend(to_dict_events(2, result.events))
    
    # Tick 3: fallback
    result = ledger.commit_fallback(3, 100.0, {"hospital": 30.0, "water": 25.0, "telecom": 15.0, "emergency": 20.0})
    all_events.extend(to_dict_events(3, result.events))
    
    # Tick 4: valid submit again
    result = ledger.submit(4, 100.0, {"hospital": 10.0, "water": 10.0, "telecom": 10.0, "emergency": 10.0})
    all_events.extend(to_dict_events(4, result.events))
    
    # Tick 5: another bad proposal
    result = ledger.propose(5, 100.0, {"hospital": -5.0, "water": 20.0, "telecom": 14.0, "emergency": 16.0})
    all_events.extend(to_dict_events(5, result.events))
    
    violations = check_event_order(all_events)
    assert violations == [], f"Event order violations: {violations}"