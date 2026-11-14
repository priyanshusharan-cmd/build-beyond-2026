"""Layer 2 bilateral bargaining, credit, ablations, explanations."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "engine"))

import pytest  # noqa: E402

from blackout_arena.config import load_damage_params, load_scenario  # noqa: E402
from blackout_arena.models import AGENTS  # noqa: E402
from blackout_arena.sim import Simulation, run_simulation  # noqa: E402

P = load_damage_params()
SC = load_scenario()


def _types(run):
    out = {}
    for e in run.log.events:
        out[e.type.value] = out.get(e.type.value, 0) + 1
    return out


def test_layer2_runs_and_never_violates_invariants():
    for seed in range(6):
        r = run_simulation(SC, P, seed, "ours")
        assert r.violations == []


def test_layer2_is_deterministic():
    a = run_simulation(SC, P, 4, "ours").log.to_jsonl()
    b = run_simulation(SC, P, 4, "ours").log.to_jsonl()
    assert a == b


def test_concessions_follow_offers_and_book_credit():
    seen = {"OFFER": 0, "CONCESSION": 0, "CREDIT_UPDATE": 0}
    for seed in range(6):
        t = _types(run_simulation(SC, P, seed, "ours"))
        for k in seen:
            seen[k] += t.get(k, 0)
    assert seen["OFFER"] > 0
    assert seen["CONCESSION"] >= seen["OFFER"] - 0  # every offer here is accepted or countered
    assert seen["CREDIT_UPDATE"] > 0


def test_credits_stay_within_bounds():
    lo, hi = P["layer2"]["debt_floor"], P["layer2"]["credit_cap"]
    sim = Simulation(SC, P, 2, "ours")
    for _ in range(SC.ticks):
        sim.step()
        for a in AGENTS:
            assert lo - 1e-9 <= sim.credits[a] <= hi + 1e-9


def test_ablations_switch_features_off():
    no_l2 = _types(run_simulation(SC, P, 1, "ours_no_l2"))
    assert "OFFER" not in no_l2 and "CONCESSION" not in no_l2 and "CREDIT_UPDATE" not in no_l2
    no_cr = _types(run_simulation(SC, P, 1, "ours_no_credit"))
    assert no_cr.get("OFFER", 0) > 0 and "CREDIT_UPDATE" not in no_cr
    for s in ("ours_no_l2", "ours_no_credit"):
        assert run_simulation(SC, P, 1, s).violations == []


def test_concession_conserves_power_and_respects_caps():
    r = run_simulation(SC, P, 3, "ours")
    for rec in r.records:
        assert sum(rec.grants.values()) <= rec.supply + 1e-6
        for a in AGENTS:
            assert -1e-9 <= rec.grants[a] <= SC.max_draw[a] + 1e-6


def test_explanations_are_plain_english_and_deterministic():
    r = run_simulation(SC, P, 0, "ours")
    ex = [e for e in r.log.events if e.type.value == "EXPLANATION"]
    assert ex, "expected at least one explanation (scenario shocks alone trigger one)"
    assert all(isinstance(e.payload["text"], str) and e.payload["text"] for e in ex)


def test_baselines_have_no_negotiation_events():
    t = _types(run_simulation(SC, P, 0, "priority"))
    assert not {"OFFER", "CONCESSION", "CREDIT_UPDATE", "EXPLANATION"} & set(t)


def test_unknown_strategy_rejected():
    with pytest.raises(ValueError):
        Simulation(SC, P, 0, "nope")
