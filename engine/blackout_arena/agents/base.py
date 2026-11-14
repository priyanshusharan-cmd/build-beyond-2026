def clip(value, min_val, max_val):
    return max(min_val, min(value, max_val))


class Agent:
    def __init__(self, name: str, base_need: float, weight: float):
        self.name = name
        self.base_need = base_need
        self.weight = weight
        self.credit = 0.0
        self.need_mult = 1.0
        self.damage_mult = 1.0
        self.chaos_mult = 1.0
        self.last_u = 0.0

    def need(self) -> float:
        return self.base_need * self.need_mult * self.chaos_mult

    def deficit(self, served_mw: float) -> float:
        current_need = self.need()
        if current_need <= 0:
            return 0.0
        u = 1 - served_mw / current_need
        return clip(u, 0, 1)

    def damage(self, served_mw: float) -> float:
        raise NotImplementedError

    foresight = 0  # ticks of look-ahead used ONLY for bidding valuation, never for scoring

    def valuation(self, served_mw: float) -> float:
        """Damage as the agent anticipates it when bidding. Scoring always uses damage()."""
        return self.damage(served_mw)

    def weighted_damage(self, served_mw: float) -> float:
        return self.weight * self.damage(served_mw)

    def step(self, served_mw: float) -> None:
        self.last_u = self.deficit(served_mw)

    def status(self) -> str:
        raise NotImplementedError