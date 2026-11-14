import math
from .base import Agent, clip


class HospitalAgent(Agent):
    def __init__(self, base_need: float, weight: float, cfg: dict):
        super().__init__("hospital", base_need, weight)
        self.cliff_center = cfg["cliff_center"]
        self.cliff_steepness = cfg["cliff_steepness"]

    def damage(self, served_mw: float) -> float:
        u = self.deficit(served_mw)

        def s(x):
            return 1 / (1 + math.exp(-self.cliff_steepness * (x - self.cliff_center)))

        s0 = s(0)
        s1 = s(1)

        if abs(s1 - s0) < 1e-9:
            d = 0.0
        else:
            d = (s(u) - s0) / (s1 - s0)

        return clip(d, 0, 1) * self.damage_mult

    def status(self) -> str:
        if self.last_u < self.cliff_center / 2:
            return "ok"
        elif self.last_u < self.cliff_center:
            return "degraded"
        else:
            return "down"