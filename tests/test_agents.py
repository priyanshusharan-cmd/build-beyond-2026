import pytest
import math
from hypothesis import given, settings, strategies as st

from blackout_arena.agents.base import Agent, clip
from blackout_arena.agents.hospital import HospitalAgent
from blackout_arena.agents.water import WaterAgent
from blackout_arena.agents.telecom import TelecomAgent
from blackout_arena.agents.emergency import EmergencyAgent
from blackout_arena.agents.system import AgentSystem, TickResult


@pytest.fixture
def params():
    return {
        "weights": {"hospital": 10, "emergency": 5, "telecom": 3, "water": 2},
        "critical_floor_frac": {"hospital": 0.6, "emergency": 0.5, "telecom": 0.3, "water": 0.2},
        "priority_order": ["hospital", "emergency", "telecom", "water"],
        "hospital": {"cliff_center": 0.25, "cliff_steepness": 20, "cooling_need_mult": 1.2},
        "water": {"reservoir_init": 1, "drain_rate": 0.04, "refill_rate": 0.02, "damage_threshold": 0.5, "low_pressure": 0.2},
        "telecom": {"battery_init": 1, "drain_rate": 0.03, "recharge_rate": 0.02, "down_damage_mult": 4},
        "emergency": {"linear_slope": 1, "effectiveness_loss_mult": 1.5},
    }


@pytest.fixture
def needs_cfg():
    return {"hospital": 38, "water": 24, "telecom": 14, "emergency": 16}


@pytest.fixture
def max_draw_cfg():
    return {"hospital": 46, "water": 29, "telecom": 17, "emergency": 20}


@pytest.fixture
def agent_system(params, needs_cfg, max_draw_cfg):
    return AgentSystem(params, needs_cfg, max_draw_cfg)


# --- Strategies ---
st_positive_need = st.floats(min_value=1.0, max_value=100.0, allow_nan=False, allow_infinity=False)
st_non_negative_served = st.floats(min_value=0.0, max_value=200.0, allow_nan=False, allow_infinity=False)
st_small_positive_float = st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False)
st_float_0_to_1 = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


# --- base.py tests ---
def test_clip():
    assert clip(5, 0, 10) == 5
    assert clip(-1, 0, 10) == 0
    assert clip(11, 0, 10) == 10
    assert clip(5, 5, 5) == 5


def test_agent_initialization():
    agent = Agent("test_agent", 10.0, 1.0)
    assert agent.name == "test_agent"
    assert agent.base_need == 10.0
    assert agent.weight == 1.0
    assert agent.need() == 10.0
    assert agent.deficit(5.0) == 0.5
    assert agent.deficit(10.0) == 0.0
    assert agent.deficit(15.0) == 0.0
    assert agent.deficit(0.0) == 1.0
    with pytest.raises(NotImplementedError):
        agent.damage(0.0)
    with pytest.raises(NotImplementedError):
        agent.status()


def test_agent_step():
    agent = Agent("test_agent", 10.0, 1.0)
    agent.step(5.0)
    assert agent.last_u == 0.5
    agent.step(10.0)
    assert agent.last_u == 0.0


# --- HospitalAgent tests ---
@settings(deadline=None)
@given(
    base_need=st_positive_need,
    weight=st_small_positive_float,
    served_mw=st_non_negative_served,
    cliff_center=st_float_0_to_1.map(lambda x: clip(x, 0.01, 0.99)),
    cliff_steepness=st.floats(min_value=1.0, max_value=50.0)
)
def test_hospital_damage_properties(base_need, weight, served_mw, cliff_center, cliff_steepness):
    cfg = {"cliff_center": cliff_center, "cliff_steepness": cliff_steepness}
    hospital = HospitalAgent(base_need, weight, cfg)

    damage_val = hospital.damage(served_mw)
    assert 0.0 <= damage_val <= 1.0 + 1e-6

    # Monotonicity in u (deficit)
    u_vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    last_damage = -1.0
    current_need = hospital.need()
    if current_need <= 0:
        return
    for u in u_vals:
        effective_served_mw = current_need * (1 - u)
        current_damage = hospital.damage(effective_served_mw)
        assert current_damage >= last_damage - 1e-6
        last_damage = current_damage


def test_hospital_cliff_shape(params, needs_cfg):
    base_need = needs_cfg["hospital"]
    weight = params["weights"]["hospital"]
    cfg = params["hospital"]
    hospital = HospitalAgent(base_need, weight, cfg)
    current_need = hospital.need()

    assert hospital.damage(current_need) == pytest.approx(0.0, abs=1e-6)
    assert hospital.damage(0.0) == pytest.approx(1.0, abs=1e-6)

    hospital_specific = HospitalAgent(base_need, weight, params["hospital"])
    current_need_specific = hospital_specific.need()

    u_0_1_served = current_need_specific * (1 - 0.1)
    u_0_2_served = current_need_specific * (1 - 0.2)
    u_0_3_served = current_need_specific * (1 - 0.3)
    u_0_5_served = current_need_specific * (1 - 0.5)

    assert hospital_specific.damage(u_0_1_served) < 0.1
    assert hospital_specific.damage(u_0_2_served) < 0.5
    assert hospital_specific.damage(u_0_3_served) > 0.5
    assert hospital_specific.damage(u_0_5_served) > 0.9


def test_hospital_status(params, needs_cfg):
    base_need = needs_cfg["hospital"]
    weight = params["weights"]["hospital"]
    cfg = params["hospital"]
    hospital = HospitalAgent(base_need, weight, cfg)

    cliff_center = cfg["cliff_center"]
    hospital.last_u = cliff_center / 2 - 0.01
    assert hospital.status() == "ok"
    hospital.last_u = cliff_center / 2 + 0.01
    assert hospital.status() == "degraded"
    hospital.last_u = cliff_center - 0.01
    assert hospital.status() == "degraded"
    hospital.last_u = cliff_center + 0.01
    assert hospital.status() == "down"
    hospital.last_u = 1.0
    assert hospital.status() == "down"


# --- WaterAgent tests ---
@settings(deadline=None)
@given(
    base_need=st_positive_need,
    weight=st_small_positive_float,
    initial_L=st_float_0_to_1,
    drain_rate=st.floats(min_value=0.0, max_value=0.1, allow_nan=False, allow_infinity=False),
    refill_rate=st.floats(min_value=0.0, max_value=0.1, allow_nan=False, allow_infinity=False),
    damage_threshold=st.floats(min_value=0.1, max_value=0.9, allow_nan=False, allow_infinity=False),
    low_pressure_threshold=st.floats(min_value=0.05, max_value=0.5, allow_nan=False, allow_infinity=False),
)
def test_water_damage_properties(base_need, weight, initial_L, drain_rate, refill_rate, damage_threshold, low_pressure_threshold):
    cfg = {
        "reservoir_init": initial_L,
        "drain_rate": drain_rate,
        "refill_rate": refill_rate,
        "damage_threshold": damage_threshold,
        "low_pressure": low_pressure_threshold,
    }
    water = WaterAgent(base_need, weight, cfg)

    # Ensure L is clipped to [0,1] on init
    assert 0.0 <= water.L <= 1.0

    # Test damage bounds [0,1] and monotonicity in u
    u_vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    last_damage = -1.0
    current_need = water.need()
    if current_need <= 0:
        return

    for u in u_vals:
        effective_served_mw = current_need * (1 - u)
        current_damage = water.damage(effective_served_mw)
        assert 0.0 <= current_damage <= 1.0 + 1e-6
        assert current_damage >= last_damage - 1e-6
        last_damage = current_damage


def test_water_step_drain_and_refill(params, needs_cfg):
    base_need = needs_cfg["water"]
    weight = params["weights"]["water"]
    cfg = params["water"]
    water = WaterAgent(base_need, weight, cfg)

    # Start with L=1.0
    water.L = 1.0

    # Deficit u=0.5 (served = 0.5 * need)
    served_mw = water.need() * 0.5
    water.step(served_mw)
    # L should decrease by drain_rate * u * drain_mult (drain_mult=1.0)
    expected_L = 1.0 - cfg["drain_rate"] * 0.5
    assert water.L == pytest.approx(expected_L)

    # Now serve fully (u=0)
    water.step(water.need())
    # L should increase by refill_rate
    expected_L += cfg["refill_rate"]
    assert water.L == pytest.approx(expected_L)

    # Clip at 1.0
    water.L = 0.99
    water.step(water.need())
    assert water.L == 1.0


def test_water_cascade_A_edge_triggered(params, needs_cfg, max_draw_cfg):
    system = AgentSystem(params, needs_cfg, max_draw_cfg)
    water = system.agents["water"]
    hospital = system.agents["hospital"]

    # Initial state: reservoir=1.0, no cascades
    # Trigger low pressure by draining reservoir
    water.L = 0.15  # below low_pressure (0.2)
    
    # First tick with low pressure: cascade A should trigger
    grants = {name: 0.0 for name in system.names}
    result = system.step(grants)
    assert "A" in result.cascades
    assert hospital.need_mult == params["hospital"]["cooling_need_mult"]
    assert hospital.need() == pytest.approx(38 * 1.2)

    # Second tick with low pressure: cascade A should NOT trigger again
    result2 = system.step(grants)
    assert "A" not in result2.cascades
    assert hospital.need_mult == params["hospital"]["cooling_need_mult"]

    # Restore reservoir above low_pressure
    water.L = 0.25
    result3 = system.step(grants)
    assert "A" not in result3.cascades
    assert hospital.need_mult == 1.0

    # Trigger low pressure again: cascade A should trigger again
    water.L = 0.15
    result4 = system.step(grants)
    assert "A" in result4.cascades


def test_water_status(params, needs_cfg):
    base_need = needs_cfg["water"]
    weight = params["weights"]["water"]
    cfg = params["water"]
    water = WaterAgent(base_need, weight, cfg)

    water.L = 0.3  # above damage_threshold (0.5)? No, 0.3 < 0.5, above low_pressure (0.2)
    assert water.status() == "degraded"

    water.L = 0.6  # above damage_threshold
    assert water.status() == "ok"

    water.L = 0.1  # below low_pressure
    assert water.status() == "down"


# --- TelecomAgent tests ---
@settings(deadline=None)
@given(
    base_need=st_positive_need,
    weight=st_small_positive_float,
    initial_B=st_float_0_to_1,
    drain_rate=st.floats(min_value=0.0, max_value=0.1, allow_nan=False, allow_infinity=False),
    recharge_rate=st.floats(min_value=0.0, max_value=0.1, allow_nan=False, allow_infinity=False),
    down_damage_mult=st.floats(min_value=1.0, max_value=10.0, allow_nan=False, allow_infinity=False),
)
def test_telecom_damage_properties(base_need, weight, initial_B, drain_rate, recharge_rate, down_damage_mult):
    cfg = {
        "battery_init": initial_B,
        "drain_rate": drain_rate,
        "recharge_rate": recharge_rate,
        "down_damage_mult": down_damage_mult,
    }
    telecom = TelecomAgent(base_need, weight, cfg)

    assert 0.0 <= telecom.B <= 1.0

    # Test damage bounds [0,1] and monotonicity in u
    u_vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    last_damage = -1.0
    current_need = telecom.need()
    if current_need <= 0:
        return

    for u in u_vals:
        effective_served_mw = current_need * (1 - u)
        current_damage = telecom.damage(effective_served_mw)
        assert 0.0 <= current_damage <= 1.0 + 1e-6
        assert current_damage >= last_damage - 1e-6
        last_damage = current_damage


def test_telecom_battery_drain_and_cascade_B(params, needs_cfg, max_draw_cfg):
    system = AgentSystem(params, needs_cfg, max_draw_cfg)
    telecom = system.agents["telecom"]
    emergency = system.agents["emergency"]

    # Drain battery by sustained deficit
    # B starts at 1.0, drain_rate=0.03. Need ~34 ticks to empty.
    grants = {name: 0.0 for name in system.names}
    
    for _ in range(40):
        result = system.step(grants)
    
    # Battery should be empty
    assert telecom.B <= 0.0
    assert telecom.battery_empty

    # Cascade B should have triggered exactly once
    # We need to check across the sequence. Let's track it.
    pass  # We'll do a more detailed test below


def test_telecom_cascade_B_edge_triggered(params, needs_cfg, max_draw_cfg):
    system = AgentSystem(params, needs_cfg, max_draw_cfg)
    telecom = system.agents["telecom"]
    emergency = system.agents["emergency"]

    # Set battery to empty
    telecom.B = 0.0

    grants = {name: 0.0 for name in system.names}
    result = system.step(grants)
    assert "B" in result.cascades
    assert emergency.damage_mult == params["emergency"]["effectiveness_loss_mult"]
    assert emergency.damage_mult == 1.5

    result2 = system.step(grants)
    assert "B" not in result2.cascades
    assert emergency.damage_mult == 1.5

    # Recharge battery
    telecom.B = 0.6
    # Need to serve telecom fully to recharge (u=0)
    grants["telecom"] = telecom.need()
    result3 = system.step(grants)
    assert "B" not in result3.cascades
    assert emergency.damage_mult == 1.0

    # Drain again
    grants["telecom"] = 0.0
    telecom.B = 0.0  # Force empty for test
    result4 = system.step(grants)
    assert "B" in result4.cascades


def test_telecom_status(params, needs_cfg):
    base_need = needs_cfg["telecom"]
    weight = params["weights"]["telecom"]
    cfg = params["telecom"]
    telecom = TelecomAgent(base_need, weight, cfg)

    telecom.B = 0.6
    assert telecom.status() == "ok"

    telecom.B = 0.3
    assert telecom.status() == "degraded"

    telecom.B = 0.0
    assert telecom.status() == "down"


# --- EmergencyAgent tests ---
@settings(deadline=None)
@given(
    base_need=st_positive_need,
    weight=st_small_positive_float,
    linear_slope=st.floats(min_value=0.5, max_value=5.0, allow_nan=False, allow_infinity=False),
)
def test_emergency_damage_properties(base_need, weight, linear_slope):
    cfg = {"linear_slope": linear_slope, "effectiveness_loss_mult": 1.5}
    emergency = EmergencyAgent(base_need, weight, cfg)

    u_vals = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    last_damage = -1.0
    current_need = emergency.need()
    if current_need <= 0:
        return

    for u in u_vals:
        effective_served_mw = current_need * (1 - u)
        current_damage = emergency.damage(effective_served_mw)
        assert 0.0 <= current_damage <= 1.0 + 1e-6
        assert current_damage >= last_damage - 1e-6
        last_damage = current_damage


def test_emergency_status(params, needs_cfg):
    base_need = needs_cfg["emergency"]
    weight = params["weights"]["emergency"]
    cfg = params["emergency"]
    emergency = EmergencyAgent(base_need, weight, cfg)

    # ok if damage_mult <= 1 and last_u <= 0.1
    emergency.damage_mult = 1.0
    emergency.last_u = 0.05
    assert emergency.status() == "ok"

    # degraded if last_u > 0.1
    emergency.last_u = 0.15
    assert emergency.status() == "degraded"

    # down if damage_mult > 1
    emergency.damage_mult = 1.5
    emergency.last_u = 0.0
    assert emergency.status() == "down"

    # down if last_u >= 0.5
    emergency.damage_mult = 1.0
    emergency.last_u = 0.5
    assert emergency.status() == "down"


# --- AgentSystem tests ---
def test_system_names_and_priority_order(params, needs_cfg, max_draw_cfg, agent_system):
    assert agent_system.names == params["priority_order"]
    assert list(agent_system.agents.keys()) == params["priority_order"]


def test_system_weights(agent_system, params):
    assert agent_system.weights() == params["weights"]


def test_system_needs(agent_system, needs_cfg):
    needs = agent_system.needs()
    for name, need_val in needs_cfg.items():
        assert needs[name] == need_val


def test_system_max_draw(agent_system, max_draw_cfg):
    # Test that max_draw property returns the correct values
    assert agent_system.max_draw == max_draw_cfg
    # Test that max_draw returns a copy, not the original dict
    assert agent_system.max_draw is not max_draw_cfg
    # Verify the exact fixture values
    expected = {"hospital": 46, "water": 29, "telecom": 17, "emergency": 20}
    assert agent_system.max_draw == expected
    # Test that modifications to the returned dict don't affect internal state
    returned = agent_system.max_draw
    returned["hospital"] = 999
    assert agent_system.max_draw["hospital"] == 46


def test_system_step_basic(agent_system):
    grants = {name: 0.0 for name in agent_system.names}
    result = agent_system.step(grants)

    assert isinstance(result, TickResult)
    assert set(result.damage.keys()) == set(agent_system.names)
    assert result.total == sum(result.damage.values())
    assert isinstance(result.cascades, list)
    assert set(result.status.keys()) == set(agent_system.names)
    assert isinstance(result.reservoir, float)
    assert isinstance(result.battery, float)


def test_system_marginal_reduction(agent_system):
    # Test 0 at served >= need
    for name in agent_system.names:
        need = agent_system.agents[name].need()
        mr = agent_system.marginal_reduction(name, need)
        assert mr == 0.0
        mr = agent_system.marginal_reduction(name, need + 10)
        assert mr == 0.0

    # Test non-negative
    for name in agent_system.names:
        need = agent_system.agents[name].need()
        mr = agent_system.marginal_reduction(name, need * 0.5)
        assert mr >= 0.0


def test_system_bid_basic(agent_system):
    # bid(price=0) == min(need, max_draw)
    for name in agent_system.names:
        need = agent_system.agents[name].need()
        max_d = agent_system._max_draw[name]
        bid_val = agent_system.bid(name, 0.0)
        assert bid_val == min(need, max_d)

    # bid returns value in [0, need]
    for name in agent_system.names:
        need = agent_system.agents[name].need()
        for price in [0.1, 1.0, 10.0, 100.0]:
            bid_val = agent_system.bid(name, price)
            assert 0.0 <= bid_val <= need + 1e-6


def test_system_bid_monotone_non_increasing(agent_system):
    # bid should be monotone non-increasing in price
    for name in agent_system.names:
        prices = [0.0, 0.01, 0.1, 0.5, 1.0, 5.0, 10.0, 100.0]
        prev_bid = float('inf')
        for price in prices:
            bid_val = agent_system.bid(name, price)
            assert bid_val <= prev_bid + 1e-6
            prev_bid = bid_val


def test_system_bid_respects_max_draw(agent_system):
    for name in agent_system.names:
        need = agent_system.agents[name].need()
        max_d = agent_system._max_draw[name]
        # If max_draw < need, bid should never exceed max_draw
        if max_d < need:
            for price in [0.0, 0.1, 1.0]:
                bid_val = agent_system.bid(name, price)
                assert bid_val <= max_d + 1e-6


def test_system_determinism(params, needs_cfg, max_draw_cfg):
    # Two identical runs of a scripted grant sequence give identical TickResults and snapshots
    system1 = AgentSystem(params, needs_cfg, max_draw_cfg)
    system2 = AgentSystem(params, needs_cfg, max_draw_cfg)

    # Scripted grant sequence (varying over time)
    grant_sequence = [
        {"hospital": 38, "water": 24, "telecom": 14, "emergency": 16},
        {"hospital": 20, "water": 12, "telecom": 7, "emergency": 8},
        {"hospital": 0, "water": 0, "telecom": 0, "emergency": 0},
        {"hospital": 38, "water": 24, "telecom": 14, "emergency": 16},
        {"hospital": 10, "water": 10, "telecom": 5, "emergency": 5},
    ]

    for grants in grant_sequence:
        r1 = system1.step(grants)
        r2 = system2.step(grants)

        assert r1.damage == r2.damage
        assert r1.total == r2.total
        assert r1.cascades == r2.cascades
        assert r1.status == r2.status
        assert r1.reservoir == pytest.approx(r2.reservoir)
        assert r1.battery == pytest.approx(r2.battery)

        s1 = system1.snapshot_state()
        s2 = system2.snapshot_state()
        assert s1 == s2


def test_system_critical_floor(agent_system, params):
    for name in agent_system.names:
        need = agent_system.agents[name].need()
        expected = params["critical_floor_frac"][name] * need
        assert agent_system.critical_floor(name) == pytest.approx(expected)


def test_system_apply_chaos_icu_surge(agent_system):
    # icu_surge with pct=20 raises hospital.chaos_mult to 1.2
    agent_system.apply_chaos("icu_surge", {"pct": 20})
    hospital = agent_system.agents["hospital"]
    assert hospital.chaos_mult == 1.2
    assert hospital.need() == pytest.approx(38 * 1.2)


def test_system_apply_chaos_burst_main(agent_system):
    # burst_main with drain_mult=2.0 raises water.drain_mult to 2.0
    agent_system.apply_chaos("burst_main", {"drain_mult": 2.0})
    water = agent_system.agents["water"]
    assert water.drain_mult == 2.0


def test_system_apply_chaos_unknown_kinds_noop(agent_system):
    # kill_substation and unknown kinds: no-op
    agent_system.apply_chaos("kill_substation", {})
    agent_system.apply_chaos("unknown_kind", {})
    # No exceptions, state unchanged (except potentially by other logic)
    # Just verify no crash


def test_system_snapshot_state(agent_system):
    snap = agent_system.snapshot_state()
    assert "reservoir" in snap
    assert "battery" in snap
    assert "status" in snap
    assert set(snap["status"].keys()) == set(agent_system.names)
    assert snap["reservoir"] == agent_system.agents["water"].L
    assert snap["battery"] == agent_system.agents["telecom"].B