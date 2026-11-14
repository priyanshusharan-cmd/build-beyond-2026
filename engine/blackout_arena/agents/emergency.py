from .base import Agent, clip


class EmergencyAgent(Agent):
    def __init__(self, base_need: float, weight: float, cfg: dict):
        super().__init__("emergency", base_need, weight)
        self.linear_slope = cfg["linear_slope"]
        self.effectiveness_loss_mult = cfg["effectiveness_loss_mult"]

    def damage(self, served_mw: float) -> float:
        u = self.deficit(served_mw)
        return clip(self.linear_slope * u, 0, 1) * self.damage_mult

    def status(self) -> str:
        if self.damage_mult > 1 or self.last_u >= 0.5:
            return "down"
        elif self.last_u > 0.1:
            return "degraded"
        else:
            return "ok"