from dataclasses import dataclass
from typing import Dict, List

from .base import Agent, clip
from .hospital import HospitalAgent
from .water import WaterAgent
from .telecom import TelecomAgent
from .emergency import EmergencyAgent

Q_STEP = 0.25
DMW = 0.05


@dataclass
class TickResult:
    damage: Dict[str, float]
    total: float
    cascades: List[str]
    status: Dict[str, str]
    reservoir: float
    battery: float


class AgentSystem:
    def __init__(self, params: dict, needs_cfg: dict, max_draw_cfg: dict):
        self._params = params
        self._agents: Dict[str, Agent] = {}
        self._max_draw = max_draw_cfg

        agent_configs = {
            "hospital": HospitalAgent,
            "water": WaterAgent,
            "telecom": TelecomAgent,
            "emergency": EmergencyAgent,
        }

        for name in params["priority_order"]:
            agent_class = agent_configs[name]
            base_need = needs_cfg[name]
            weight = params["weights"][name]
            cfg = params[name]
            self._agents[name] = agent_class(base_need, weight, cfg)

        for ag in self._agents.values():
            ag.foresight = int(params.get("foresight_ticks", 15))

        self._cascade_a_active = False
        self._cascade_b_active = False

    @property
    def names(self) -> List[str]:
        return list(self._params["priority_order"])

    @property
    def agents(self) -> Dict[str, Agent]:
        return self._agents

    def weights(self) -> Dict[str, float]:
        return dict(self._params["weights"])

    @property
    def max_draw(self) -> Dict[str, float]:
        return dict(self._max_draw)

    def needs(self) -> Dict[str, float]:
        return {name: agent.need() for name, agent in self._agents.items()}

    def step(self, grants: Dict[str, float]) -> TickResult:
        current_weighted_damages = {
            name: agent.weighted_damage(grants.get(name, 0.0))
            for name, agent in self._agents.items()
        }
        total_damage = sum(current_weighted_damages.values())

        for name in self.names:
            self._agents[name].step(grants.get(name, 0.0))

        newly_triggered_cascades = []

        water_agent = self._agents["water"]
        hospital_agent = self._agents["hospital"]

        is_a_now_active = water_agent.low_pressure
        if is_a_now_active and not self._cascade_a_active:
            newly_triggered_cascades.append("A")
        hospital_agent.need_mult = self._params["hospital"]["cooling_need_mult"] if is_a_now_active else 1.0
        self._cascade_a_active = is_a_now_active

        telecom_agent = self._agents["telecom"]
        emergency_agent = self._agents["emergency"]

        is_b_now_active = telecom_agent.battery_empty
        if is_b_now_active and not self._cascade_b_active:
            newly_triggered_cascades.append("B")
        emergency_agent.damage_mult = self._params["emergency"]["effectiveness_loss_mult"] if is_b_now_active else 1.0
        self._cascade_b_active = is_b_now_active

        status_map = {name: agent.status() for name, agent in self._agents.items()}
        reservoir_L = water_agent.L
        battery_B = telecom_agent.B

        return TickResult(
            damage=current_weighted_damages,
            total=total_damage,
            cascades=newly_triggered_cascades,
            status=status_map,
            reservoir=reservoir_L,
            battery=battery_B,
        )

    def marginal_reduction(self, agent_name: str, served_mw: float, w: float = None) -> float:
        agent = self._agents[agent_name]
        current_need = agent.need()

        if served_mw >= current_need:
            return 0.0

        weight_to_use = w if w is not None else agent.weight

        damage_at_served = agent.valuation(served_mw)
        served_mw_plus_dMW = min(served_mw + DMW, current_need)
        if served_mw_plus_dMW <= served_mw:
            return 0.0

        damage_at_served_plus_dMW = agent.valuation(served_mw_plus_dMW)

        reduction = weight_to_use * (damage_at_served - damage_at_served_plus_dMW) / (served_mw_plus_dMW - served_mw)

        return max(0.0, reduction)

    def bid(self, agent_name: str, price: float, w_eff: float = None) -> float:
        agent = self._agents[agent_name]
        current_need = agent.need()
        max_allowed_draw = self._max_draw[agent_name]

        if price <= 0:
            return min(current_need, max_allowed_draw)

        weight_to_use = agent.weight * w_eff if w_eff is not None else agent.weight

        if current_need <= 0:
            return 0.0

        points = set([0.0])
        q = 0.0
        while q <= current_need + 1e-9:
            points.add(round(q, 2))
            q += Q_STEP
        points.add(current_need)

        sorted_points = sorted(list(points))

        best_q = 0.0
        for i in range(len(sorted_points) - 1, 0, -1):
            q = sorted_points[i]
            q_lo = sorted_points[i - 1]

            if q == 0.0:
                continue

            if q - q_lo < 1e-9:
                continue

            damage_at_q_lo = agent.valuation(q_lo)
            damage_at_q = agent.valuation(q)

            chunk_marginal_reduction = weight_to_use * (damage_at_q_lo - damage_at_q) / (q - q_lo)

            if chunk_marginal_reduction >= price:
                best_q = q
                break

        return clip(best_q, 0, min(current_need, max_allowed_draw))

    def apply_chaos(self, kind: str, chaos_params: dict) -> None:
        if kind == "icu_surge":
            pct = chaos_params.get("pct", 0)
            self._agents["hospital"].chaos_mult = 1.0 + pct / 100.0
        elif kind == "burst_main":
            drain_mult = chaos_params.get("drain_mult", 1.0)
            self._agents["water"].drain_mult = drain_mult

    def critical_floor(self, agent_name: str) -> float:
        return self._params["critical_floor_frac"][agent_name] * self._agents[agent_name].need()

    def snapshot_state(self) -> Dict[str, any]:
        water_agent = self._agents["water"]
        telecom_agent = self._agents["telecom"]

        return {
            "reservoir": water_agent.L,
            "battery": telecom_agent.B,
            "status": {name: agent.status() for name, agent in self._agents.items()},
        }