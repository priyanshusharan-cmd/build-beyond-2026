from __future__ import annotations
import math
import pytest
from hypothesis import given, settings
from hypothesis.strategies import floats, lists, dictionaries, text

# Adjust hypothesis settings for faster feedback during development
settings.register_profile("ci", deadline=None)
settings.load_profile("ci")

from blackout_arena.market import MarketClock, PriceResult
from blackout_arena.fairness import (
    jain_index,
    satisfaction,
    time_averaged_satisfaction,
    jain_from_runs,
    effective_weight,
    decay_credit,
    apply_concession
)

# Jain's Index Tests

def test_jain_index_empty():
    assert jain_index([]) == 1.0

def test_jain_index_all_zeros():
    assert jain_index([0.0, 0.0, 0.0]) == 1.0

def test_jain_index_equal_values():
    assert jain_index([1.0, 1.0, 1.0]) == 1.0
    assert jain_index([5.0, 5.0]) == 1.0

def test_jain_index_one_hot():
    # For one-hot, should be 1/n
    assert jain_index([1.0, 0.0, 0.0]) == pytest.approx(1/3)
    assert jain_index([0.0, 2.0, 0.0, 0.0]) == pytest.approx(1/4)

@given(values=lists(floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False), min_size=1))
def test_jain_index_bounds(values):
    # Filter out cases where sum_of_squares is zero for meaningful bounds check
    # (jain_index returns 1.0 for all zeros, which is within bounds but edge case for the lower bound 1/n)
    sum_of_squares = sum(v*v for v in values)
    if sum_of_squares > 0:
        n = len(values)
        result = jain_index(values)
        assert (1/n - 1e-9) <= result <= (1.0 + 1e-9) # Allow small epsilon for float precision


# Satisfaction Tests

def test_satisfaction_clipping():
    assert satisfaction(0.5, 1.0) == 0.5
    assert satisfaction(1.5, 1.0) == 1.0
    assert satisfaction(-0.5, 1.0) == 0.0
    assert satisfaction(0.0, 1.0) == 0.0
    assert satisfaction(1.0, 1.0) == 1.0

def test_satisfaction_need_zero_or_negative():
    assert satisfaction(1.0, 0.0) == 1.0
    assert satisfaction(1.0, -1.0) == 1.0
    assert satisfaction(0.0, 0.0) == 1.0


# Time-averaged satisfaction tests

def test_time_averaged_satisfaction_small_example():
    served = {
        "agentA": [0.5, 1.0],
        "agentB": [0.2, 0.8]
    }
    need = {
        "agentA": [1.0, 1.0],
        "agentB": [1.0, 1.0]
    }
    expected = {
        "agentA": (0.5/1.0 + 1.0/1.0)/2,
        "agentB": (0.2/1.0 + 0.8/1.0)/2
    }
    assert time_averaged_satisfaction(served, need) == pytest.approx(expected)

def test_time_averaged_satisfaction_zero_ticks():
    served = {"agentA": [], "agentB": []}
    need = {"agentA": [], "agentB": []}
    expected = {"agentA": 1.0, "agentB": 1.0}
    assert time_averaged_satisfaction(served, need) == expected

def test_time_averaged_satisfaction_mixed_ticks_and_need_zero():
    served = {"agentA": [1.0, 0.5], "agentB": [0.0]}
    need = {"agentA": [1.0, 0.0], "agentB": [0.0]}
    # AgentA: (sat(1.0,1.0) + sat(0.5,0.0))/2 = (1.0 + 1.0)/2 = 1.0
    # AgentB: (sat(0.0,0.0))/1 = 1.0
    expected = {"agentA": 1.0, "agentB": 1.0}
    assert time_averaged_satisfaction(served, need) == pytest.approx(expected)


# Jain from runs tests

def test_jain_from_runs_small_example():
    served = {
        "agentA": [0.5, 1.0],
        "agentB": [0.2, 0.8]
    }
    need = {
        "agentA": [1.0, 1.0],
        "agentB": [1.0, 1.0]
    }
    # time_avg_sats: {"agentA": 0.75, "agentB": 0.5}
    # Jain of [0.75, 0.5] = (0.75+0.5)^2 / (2 * (0.75^2 + 0.5^2)) = 1.25^2 / (2 * (0.5625 + 0.25)) = 1.5625 / (2 * 0.8125) = 1.5625 / 1.625 = 0.961538...
    expected_time_avg = {"agentA": 0.75, "agentB": 0.5}
    expected_jain = jain_index(list(expected_time_avg.values())) # Need to convert to list for jain_index
    assert jain_from_runs(served, need) == pytest.approx(expected_jain)

def test_jain_from_runs_empty_data():
    served = {"agentA": [], "agentB": []}
    need = {"agentA": [], "agentB": []}
    assert jain_from_runs(served, need) == 1.0


# Market Clock Tests

class LinearBidder:
    def __init__(self, agent_params: dict[str, dict[str, float]]):
        self.agent_params = agent_params

    def bid_fn(self, agent_name: str, price: float) -> float:
        params = self.agent_params.get(agent_name, {"a": 0.0, "b": 0.0})
        a = params.get("a", 0.0)
        b = params.get("b", 0.0)
        return max(0.0, a - b * price)

def test_market_converges_with_linear_demand():
    agent_params = {
        "agent1": {"a": 100.0, "b": 10.0},
        "agent2": {"a": 80.0, "b": 8.0},
    }
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())
    supply = 10.0

    # Use parameters that converge: smaller eta, higher damping
    clock = MarketClock(p0=1.0, eta=0.1, damping=0.9, eps=0.5, max_rounds=50, p_min=0.01)
    result = clock.discover(supply, agent_names, bidder.bid_fn)

    assert result.converged is True
    assert abs(result.total_demand - supply) <= clock.eps
    assert result.rounds_used <= 50
    assert result.price >= clock.p_min

def test_market_price_rises_when_demand_exceeds_supply():
    agent_params = {"agent1": {"a": 100.0, "b": 1.0}}
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())
    supply = 10.0
    
    # At p0=1.0, demand = 100 - 1 = 99, which is much higher than supply=10. Price should rise.
    clock = MarketClock(p0=1.0, eta=0.5, damping=0.6, eps=0.1, max_rounds=5, p_min=0.01)
    initial_price = clock.price
    result = clock.discover(supply, agent_names, bidder.bid_fn)

    assert result.price > initial_price

def test_market_price_falls_when_supply_exceeds_demand():
    agent_params = {"agent1": {"a": 10.0, "b": 1.0}}
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())
    supply = 100.0

    # At p0=1.0, demand = 10 - 1 = 9, which is much lower than supply=100. Price should fall.
    clock = MarketClock(p0=1.0, eta=0.5, damping=0.6, eps=0.1, max_rounds=5, p_min=0.01)
    initial_price = clock.price
    result = clock.discover(supply, agent_names, bidder.bid_fn)

    assert result.price < initial_price

def test_market_respects_max_rounds():
    # Create a bid_fn that never converges (e.g., constant demand different from supply)
    def constant_bid_fn(agent_name: str, price: float) -> float:
        return 50.0 # Constant demand

    agent_names = ["agent1"]
    supply = 10.0 # Supply is different

    clock = MarketClock(p0=1.0, eta=0.5, damping=0.6, eps=0.1, max_rounds=8, p_min=0.01)
    result = clock.discover(supply, agent_names, constant_bid_fn)

    assert result.converged is False
    assert result.rounds_used == clock.max_rounds

def test_market_trace_length_and_keys():
    agent_params = {"agent1": {"a": 10.0, "b": 1.0}}
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())
    supply = 10.0

    clock = MarketClock(p0=1.0, max_rounds=3)
    result = clock.discover(supply, agent_names, bidder.bid_fn)

    assert len(result.trace) == result.rounds_used
    if result.rounds_used > 0:
        for entry in result.trace:
            assert "round" in entry
            assert "price" in entry
            assert "total_demand" in entry
            assert "demands" in entry
            assert isinstance(entry["round"], int)
            assert isinstance(entry["price"], float)
            assert isinstance(entry["total_demand"], float)
            assert isinstance(entry["demands"], dict)


def test_market_result_price_gte_p_min():
    agent_params = {"agent1": {"a": 0.0, "b": 0.0}}
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())
    supply = 100.0 # Very oversupplied, demand is always 0

    clock = MarketClock(p0=1.0, eta=0.5, damping=0.6, eps=0.1, max_rounds=5, p_min=0.05)
    result = clock.discover(supply, agent_names, bidder.bid_fn)

    assert result.price >= clock.p_min

def test_market_price_carry_over():
    agent_params = {"agent1": {"a": 100.0, "b": 10.0}}
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())
    supply = 10.0

    clock = MarketClock(p0=1.0, eta=0.5, damping=0.6, eps=0.1, max_rounds=20, p_min=0.01)
    
    # First discover
    result1 = clock.discover(supply, agent_names, bidder.bid_fn)
    assert clock.price == pytest.approx(result1.price)

    # Second discover
    # The bid_fn for the first round of the second discover should receive result1.price
    bid_prices_in_second_discover = []
    def bid_fn_tracking_price(agent_name: str, price: float) -> float:
        if not bid_prices_in_second_discover: # Only capture the first price seen
            bid_prices_in_second_discover.append(price)
        return bidder.bid_fn(agent_name, price)
    
    result2 = clock.discover(supply, agent_names, bid_fn_tracking_price)
    
    assert bid_prices_in_second_discover[0] == pytest.approx(result1.price)
    assert clock.price == pytest.approx(result2.price)

def test_market_no_grants_attribute():
    agent_params = {"agent1": {"a": 10.0, "b": 1.0}}
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())
    supply = 10.0

    clock = MarketClock()
    result = clock.discover(supply, agent_names, bidder.bid_fn)

    assert not hasattr(result, 'grants')
    assert not hasattr(clock, 'grants')
    assert not hasattr(result, 'grant')
    assert not hasattr(clock, 'grant')
    assert result.demands == {name: bidder.bid_fn(name, result.price) for name in agent_names}
    assert result.total_demand == sum(result.demands.values())

def test_market_supply_zero_or_negative():
    agent_params = {"agent1": {"a": 100.0, "b": 1.0}}
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())

    # Test with supply = 0
    clock1 = MarketClock(p0=1.0, max_rounds=5, p_min=0.01)
    result1 = clock1.discover(0.0, agent_names, bidder.bid_fn)
    assert result1.price >= clock1.p_min
    assert math.isfinite(result1.price)

    # Test with supply = -10.0
    clock2 = MarketClock(p0=1.0, max_rounds=5, p_min=0.01)
    result2 = clock2.discover(-10.0, agent_names, bidder.bid_fn)
    assert result2.price >= clock2.p_min
    assert math.isfinite(result2.price)

def test_market_determinism():
    agent_params = {
        "agent1": {"a": 100.0, "b": 10.0},
        "agent2": {"a": 80.0, "b": 8.0},
    }
    bidder = LinearBidder(agent_params)
    agent_names = list(agent_params.keys())
    supply = 10.0

    clock1 = MarketClock(p0=1.0, eta=0.5, damping=0.6, eps=0.1, max_rounds=20, p_min=0.01)
    result1 = clock1.discover(supply, agent_names, bidder.bid_fn)

    clock2 = MarketClock(p0=1.0, eta=0.5, damping=0.6, eps=0.1, max_rounds=20, p_min=0.01)
    result2 = clock2.discover(supply, agent_names, bidder.bid_fn)

    assert result1.price == pytest.approx(result2.price)
    assert result1.demands == pytest.approx(result2.demands)
    assert result1.total_demand == pytest.approx(result2.total_demand)
    assert result1.rounds_used == result2.rounds_used
    assert result1.converged == result2.converged
    # Compare trace manually since pytest.approx doesn't support nested structures
    assert len(result1.trace) == len(result2.trace)
    for t1, t2 in zip(result1.trace, result2.trace):
        assert t1["round"] == t2["round"]
        assert t1["price"] == pytest.approx(t2["price"])
        assert t1["total_demand"] == pytest.approx(t2["total_demand"])
        # Compare demands dict
        assert set(t1["demands"].keys()) == set(t2["demands"].keys())
        for k in t1["demands"]:
            assert t1["demands"][k] == pytest.approx(t2["demands"][k])

def test_market_empty_agent_names():
    clock = MarketClock()
    result = clock.discover(10.0, [], lambda n,p: 1.0)
    assert result.total_demand == 0.0
    assert result.demands == {}

# Effective Weight Tests

@given(w=floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False),
       credit=floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
       lam=floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False))
def test_effective_weight_non_negative_and_zero_credit_or_lam(w, credit, lam):
    ew = effective_weight(w, credit, lam)
    assert ew >= 0.0

    if credit == 0.0 or lam == 0.0:
        assert effective_weight(w, 0.0, lam) == pytest.approx(w)
        assert effective_weight(w, credit, 0.0) == pytest.approx(w)

@given(w=floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False),
       credit1=floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
       credit_diff=floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False),
       lam=floats(min_value=0.0, max_value=1e3, allow_nan=False, allow_infinity=False))
def test_effective_weight_monotone_non_decreasing_in_credit(w, credit1, credit_diff, lam):
    credit2 = credit1 + credit_diff # credit2 >= credit1
    ew1 = effective_weight(w, credit1, lam)
    ew2 = effective_weight(w, credit2, lam)
    # For lam >= 0 and w >= 0, effective_weight should be non-decreasing with credit
    assert ew2 >= ew1 - 1e-9 # Allow for floating point inaccuracies


# Decay Credit Tests

@given(credit=floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False),
       decay=floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_decay_credit_shrinks_magnitude_and_keeps_sign(credit, decay):
    decayed_credit = decay_credit(credit, decay)
    
    if credit == 0.0:
        assert decayed_credit == pytest.approx(0.0)
    elif credit > 0.0:
        assert decayed_credit <= credit + 1e-9 # Shrinks or stays same
        assert decayed_credit >= -1e-9 # Keeps sign if decay is 0-1 (allows small negative due to FP)
    else: # credit < 0.0
        assert decayed_credit >= credit - 1e-9 # Magnitude shrinks, so value increases (less negative)
        assert decayed_credit <= 1e-9 # Keeps sign if decay is 0-1 (allows small positive due to FP)
    
    # More directly checking magnitude shrinking
    assert abs(decayed_credit) <= abs(credit) + 1e-9 # Allow small epsilon for float precision


# Apply Concession Tests

@given(credits=dictionaries(text(min_size=1, max_size=10), floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False), max_size=5),
       yielder=text(min_size=1, max_size=10),
       beneficiary=text(min_size=1, max_size=10),
       amount=floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False))
def test_apply_concession_conserves_total_and_does_not_mutate_input(credits, yielder, beneficiary, amount):
    original_credits_sum = sum(credits.values())
    
    new_credits = apply_concession(credits, yielder, beneficiary, amount)

    # Check if input is not mutated
    assert credits != new_credits or (yielder == beneficiary and new_credits == credits) # If yielder==beneficiary, it returns a copy, which might be same value but different object (depending on implementation)
    
    # Check sum conservation
    # Need to consider potential new keys added with 0.0 initial value if they were missing
    all_keys = set(credits.keys()) | {yielder, beneficiary}
    total_after_concession = sum(new_credits.get(k, 0.0) for k in all_keys)

    # Calculate expected sum considering initial missing keys for yielder/beneficiary
    expected_sum = original_credits_sum
    if yielder not in credits:
        expected_sum += 0.0 # No change if it was 0 initially and then added
    if beneficiary not in credits:
        expected_sum += 0.0 # No change if it was 0 initially and then added

    # For the case where yielder == beneficiary, amount effectively adds to both and cancels out.
    # The implementation returns a copy of credits, so the sum remains the same as original_credits_sum.
    if yielder == beneficiary:
        assert total_after_concession == pytest.approx(original_credits_sum)
    else:
        assert total_after_concession == pytest.approx(original_credits_sum) # Sum should be conserved

def test_apply_concession_yielder_beneficiary_update():
    credits = {"A": 10.0, "B": 5.0}
    new_credits = apply_concession(credits, "A", "B", 2.0)
    assert new_credits["A"] == pytest.approx(12.0)
    assert new_credits["B"] == pytest.approx(3.0)
    assert "A" in credits and credits["A"] == 10.0 # Ensure input not mutated

    # Test with missing keys
    credits_missing = {"A": 10.0}
    new_credits_missing = apply_concession(credits_missing, "A", "C", 3.0)
    assert new_credits_missing["A"] == pytest.approx(13.0)
    assert new_credits_missing["C"] == pytest.approx(-3.0)

    # Test yielder == beneficiary
    credits_same = {"A": 10.0}
    new_credits_same = apply_concession(credits_same, "A", "A", 5.0)
    assert new_credits_same["A"] == pytest.approx(10.0) # No change in value
    assert new_credits_same is not credits_same # Still a new dict

    # Test amount is negative
    credits_neg_amount = {"A": 10.0, "B": 5.0}
    new_credits_neg_amount = apply_concession(credits_neg_amount, "A", "B", -2.0)
    assert new_credits_neg_amount["A"] == pytest.approx(8.0)
    assert new_credits_neg_amount["B"] == pytest.approx(7.0)

    # Test zero amount
    credits_zero_amount = {"A": 10.0, "B": 5.0}
    new_credits_zero_amount = apply_concession(credits_zero_amount, "A", "B", 0.0)
    assert new_credits_zero_amount["A"] == pytest.approx(10.0)
    assert new_credits_zero_amount["B"] == pytest.approx(5.0)
    assert new_credits_zero_amount == credits_zero_amount # Should be identical if amount is 0 and no new keys are added
