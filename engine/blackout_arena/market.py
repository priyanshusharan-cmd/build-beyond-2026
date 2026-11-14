from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

@dataclass
class PriceResult:
    price: float
    demands: dict[str, float]
    total_demand: float
    rounds_used: int
    converged: bool
    trace: list[dict]


class MarketClock:
    def __init__(self, p0: float = 1.0, eta: float = 0.5, damping: float = 0.6, eps: float = 0.5, max_rounds: int = 8, p_min: float = 0.01):
        self.price: float = p0
        self.eta: float = eta
        self.damping: float = damping
        self.eps: float = eps
        self.max_rounds: int = max_rounds
        self.p_min: float = p_min

    def discover(self, supply: float, agent_names: list[str], bid_fn: Callable[[str, float], float]) -> PriceResult:
        p = self.price
        trace = []
        converged = False
        rounds_used = 0

        for r in range(1, self.max_rounds + 1):
            rounds_used = r
            demands = {name: bid_fn(name, p) for name in agent_names}
            total_demand = sum(demands.values())

            trace.append({
                "round": r,
                "price": p,
                "total_demand": total_demand,
                "demands": demands.copy()
            })

            if abs(total_demand - supply) <= self.eps:
                converged = True
                break

            S_eff = supply if supply > 0 else 1e-9
            
            # Calculate multiplicative step factor and clamp it
            step_factor = 1 + self.eta * (total_demand - S_eff) / S_eff
            step_factor = max(0.25, min(4.0, step_factor))

            p_candidate = p * step_factor
            p_new = p + self.damping * (p_candidate - p)
            p = max(p_new, self.p_min)
        
        # Use the price and demands from the last evaluated round (trace entry)
        # The last trace entry has the price at which demands were computed
        last_trace = trace[-1] if trace else {"round": 0, "price": p, "total_demand": 0.0, "demands": {}}
        final_price = last_trace["price"]
        final_demands = last_trace["demands"]
        final_total_demand = last_trace["total_demand"]

        final_price_result = PriceResult(
            price=final_price,
            demands=final_demands,
            total_demand=final_total_demand,
            rounds_used=rounds_used,
            converged=converged,
            trace=trace
        )

        self.price = max(final_price, self.p_min) # Update self.price for carry-over
        return final_price_result