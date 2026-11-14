import pytest
from hypothesis import given, settings, strategies as st

from blackout_arena.config import Scenario, SupplyWalk, Shock, load_damage_params, load_scenario
from blackout_arena.metrics import compare
from blackout_arena.sim import Simulation, run_simulation

PARAMS = load_damage_params()
SC = load_scenario()


def short(ticks=120, **kw):
    d = SC.model_dump()
    d["ticks"] = ticks
    d.update(kw)
    return Scenario(**d)


def test_determinism_byte_identical():
    a = run_simulation(short(), PARAMS, 7, "ours").log.to_jsonl()
    b = run_simulation(short(), PARAMS, 7, "ours").log.to_jsonl()
    assert a == b and len(a) > 1000


def test_different_seed_differs():
    a = run_simulation(short(), PARAMS, 1, "ours").log.to_jsonl()
    b = run_simulation(short(), PARAMS, 2, "ours").log.to_jsonl()
    assert a != b


def test_ours_zero_violations_default_scenario():
    r = run_simulation(SC, PARAMS, 0, "ours")
    assert r.violations == []


def test_blind_has_capacity_breach_on_default():
    r = run_simulation(SC, PARAMS, 0, "blind")
    assert any(v.code == "INV-1" for v in r.violations)
    assert r.cascade_count >= 1


@pytest.mark.parametrize("s", ["proportional", "priority"])
def test_other_baselines_feasible(s):
    assert run_simulation(SC, PARAMS, 0, s).violations == []


def test_same_supply_across_strategies():
    sup = {s: [r.supply for r in run_simulation(short(60), PARAMS, 3, s).records[:5]]
           for s in ["ours", "proportional", "priority"]}
    assert sup["ours"] == sup["proportional"] == sup["priority"]


def test_live_chaos_changes_run_and_is_logged():
    base = Simulation(short(60), PARAMS, 4, "ours")
    for _ in range(10):
        base.step()
    base.inject_chaos("kill_substation", {"mw": 40, "duration": 20})
    base.inject_chaos("icu_surge", {"pct": 30, "duration": 20})
    base.inject_chaos("burst_main", {"drain_mult": 4, "duration": 20})
    while base.tick < 60:
        base.step()
    kinds = [e.payload.get("kind") for e in base.log.events if e.type.value == "CHAOS_INJECTED"]
    assert {"kill_substation", "icu_surge", "burst_main"} <= set(kinds)
    assert base.result.violations == []


def test_snapshot_shape():
    s = Simulation(short(5), PARAMS, 0, "ours")
    s.step()
    snap = s.snapshot()
    assert set(snap) == {"tick", "supply", "grants", "need", "served_pct", "damage_cum", "jain",
                         "cascades", "credits", "status"}


def test_compare_runs_all_strategies():
    m = compare(short(60), PARAMS, 0)
    assert set(m) == {"ours", "blind", "proportional", "priority"}


@settings(max_examples=60, deadline=None)
@given(seed=st.integers(0, 10**6),
       sigma=st.floats(0.0, 15.0),
       shock=st.floats(-90.0, 20.0),
       at=st.integers(0, 40))
def test_fuzz_ours_never_violates(seed, sigma, shock, at):
    sc = short(60, supply_walk=SupplyWalk(sigma=sigma, min=0, max=130, mean_revert=0.05).model_dump(),
               shocks=[Shock(tick=at, duration=30, delta_mw=shock, label="fuzz").model_dump()])
    r = run_simulation(sc, PARAMS, seed, "ours")
    assert r.violations == []
