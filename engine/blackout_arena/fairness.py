from __future__ import annotations
import math

def jain_index(values: list[float]) -> float:
    """Calculates Jain's fairness index."""
    if not values:
        return 1.0

    n = len(values)
    sum_values = sum(values)
    sum_of_squares = sum(v * v for v in values)

    if sum_of_squares == 0:
        return 1.0

    return (sum_values * sum_values) / (n * sum_of_squares)


def satisfaction(served: float, need: float) -> float:
    """Calculates satisfaction, clipped between 0 and 1."""
    if need <= 0:
        return 1.0
    return max(0.0, min(1.0, served / need))


def time_averaged_satisfaction(served: dict[str, list[float]], need: dict[str, list[float]]) -> dict[str, float]:
    """Calculates mean over ticks of per-tick satisfaction per agent."""
    time_avg_sats = {}
    agent_names = served.keys() # Assume served and need have the same keys

    for agent_name in agent_names:
        agent_served_ticks = served.get(agent_name, [])
        agent_need_ticks = need.get(agent_name, [])
        
        if not agent_served_ticks and not agent_need_ticks: # No ticks for this agent
            time_avg_sats[agent_name] = 1.0
            continue

        per_tick_satisfactions = []
        for s, n in zip(agent_served_ticks, agent_need_ticks):
            per_tick_satisfactions.append(satisfaction(s, n))
        
        if not per_tick_satisfactions: # If zip resulted in empty list (e.g., served had items, need didn't)
            time_avg_sats[agent_name] = 1.0
        else:
            time_avg_sats[agent_name] = sum(per_tick_satisfactions) / len(per_tick_satisfactions)

    return time_avg_sats


def jain_from_runs(served: dict[str, list[float]], need: dict[str, list[float]]) -> float:
    """Calculates Jain's index from time-averaged satisfaction values."""
    time_avg_sats = time_averaged_satisfaction(served, need)
    # Get satisfaction values in a consistent order (e.g., sorted by agent name)
    # The requirement is 'in served key order', so we should respect that.
    satisfaction_values = [time_avg_sats[name] for name in served.keys()]
    return jain_index(satisfaction_values)


def effective_weight(w: float, credit: float, lam: float) -> float:
    """Calculates effective weight with credit and lambda."""
    return max(0.0, w * (1 + lam * credit))


def decay_credit(credit: float, decay: float) -> float:
    """Decays credit by a given factor."""
    return credit * (1 - decay)


def apply_concession(credits: dict[str, float], yielder: str, beneficiary: str, amount: float) -> dict[str, float]:
    """Applies a concession, updating yielder and beneficiary credits."""
    new_credits = credits.copy()

    if yielder == beneficiary:
        return new_credits

    new_credits[yielder] = new_credits.get(yielder, 0.0) + amount
    new_credits[beneficiary] = new_credits.get(beneficiary, 0.0) - amount

    return new_credits