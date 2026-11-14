from .base import Agent, clip


class WaterAgent(Agent):
    def __init__(self, base_need: float, weight: float, cfg: dict):
        super().__init__("water", base_need, weight)
        self.L = cfg["reservoir_init"]
        self.drain_rate = cfg["drain_rate"]
        self.refill_rate = cfg["refill_rate"]
        self.damage_threshold = cfg["damage_threshold"]
        self.low_pressure_threshold = cfg["low_pressure"]
        self.drain_mult = 1.0

    def step(self, served_mw: float) -> None:
        u = self.deficit(served_mw)
        if u > 0:
            self.L -= self.drain_rate * u * self.drain_mult
        elif served_mw >= self.need():
            self.L += self.refill_rate
        self.L = clip(self.L, 0, 1)
        self.last_u = u

    def damage(self, served_mw: float) -> float:
        u = self.deficit(served_mw)
        if self.L >= self.damage_threshold or u == 0:
            damage_val = 0.0
        else:
            ramp = (self.damage_threshold - self.L) / self.damage_threshold
            damage_val = clip(ramp * max(u, 0.3), 0, 1)

        return damage_val * self.damage_mult

    def valuation(self, served_mw: float) -> float:
        """Anticipate the reservoir level `foresight` ticks ahead if the deficit persisted."""
        u = self.deficit(served_mw)
        if u == 0:
            return 0.0
        l_eff = clip(self.L - self.drain_rate * self.drain_mult * u * self.foresight, 0, 1)
        if l_eff >= self.damage_threshold:
            return 0.0
        ramp = (self.damage_threshold - l_eff) / self.damage_threshold
        return clip(ramp * max(u, 0.3), 0, 1) * self.damage_mult

    @property
    def low_pressure(self) -> bool:
        return self.L < self.low_pressure_threshold

    def status(self) -> str:
        if self.low_pressure:
            return "down"
        elif self.L < self.damage_threshold:
            return "degraded"
        else:
            return "ok"