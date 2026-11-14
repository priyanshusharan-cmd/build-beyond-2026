from .base import Agent, clip


class TelecomAgent(Agent):
    def __init__(self, base_need: float, weight: float, cfg: dict):
        super().__init__("telecom", base_need, weight)
        self.B = cfg["battery_init"]
        self.drain_rate = cfg["drain_rate"]
        self.recharge_rate = cfg["recharge_rate"]
        self.down_damage_mult = cfg["down_damage_mult"]

    def step(self, served_mw: float) -> None:
        u = self.deficit(served_mw)
        if u > 0:
            self.B -= self.drain_rate
        else:
            self.B += self.recharge_rate
        self.B = clip(self.B, 0, 1)
        self.last_u = u

    def damage(self, served_mw: float) -> float:
        u = self.deficit(served_mw)
        if self.B > 0:
            damage_val = 0.05 * u
        else:
            damage_val = min(1.0, 0.05 * u + 0.25 * self.down_damage_mult * u)

        return damage_val * self.damage_mult

    def valuation(self, served_mw: float) -> float:
        """Anticipate battery level `foresight` ticks ahead if the deficit persisted."""
        u = self.deficit(served_mw)
        if u == 0:
            return 0.0
        b_eff = self.B - self.drain_rate * self.foresight
        if b_eff > 0:
            damage_val = 0.05 * u
        else:
            damage_val = min(1.0, 0.05 * u + 0.25 * self.down_damage_mult * u)
        return damage_val * self.damage_mult

    @property
    def battery_empty(self) -> bool:
        return self.B <= 0

    def status(self) -> str:
        if self.battery_empty:
            return "down"
        elif self.B < 0.5:
            return "degraded"
        else:
            return "ok"