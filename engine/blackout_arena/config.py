from pathlib import Path
from typing import Annotated
import yaml
from pydantic import BaseModel, Field, field_validator


# Damage config sub-models
class HospitalDamage(BaseModel):
    cliff_center: float
    cliff_steepness: float
    cooling_need_mult: float


class WaterDamage(BaseModel):
    reservoir_init: float
    drain_rate: float
    refill_rate: float
    damage_threshold: float
    low_pressure: float


class TelecomDamage(BaseModel):
    battery_init: float
    drain_rate: float
    recharge_rate: float
    down_damage_mult: float


class EmergencyDamage(BaseModel):
    linear_slope: float
    effectiveness_loss_mult: float


class FairnessConfig(BaseModel):
    lambda_credit: float
    credit_decay: float


class MarketConfig(BaseModel):
    p0: float
    eta: float
    damping: float
    eps: float
    max_rounds: int
    p_min: float


class Layer2Config(BaseModel):
    rounds: int = 3              # max bilateral bargaining rounds per tick
    chunks_mw: list[float] = [0.5, 1.0, 2.0, 4.0]  # concession sizes offered
    duration_ticks: int = 5      # T: how long an accepted concession is honoured
    min_gain: float = 0.05       # weighted damage reduction needed to bother offering
    credit_scale: float = 30.0   # credit = mw * T / credit_scale
    debt_floor: float = -1.0     # a debtor refuses (counters) concessions that push it below this
    credit_cap: float = 1.0      # banked credit is capped
    debt_penalizes: bool = False  # if False, only positive credit raises bid weight


class DamageConfig(BaseModel):
    layer2: Layer2Config = Layer2Config()
    weights: dict[str, float]
    critical_floor_frac: dict[str, float]
    priority_order: list[str]
    hospital: HospitalDamage
    water: WaterDamage
    telecom: TelecomDamage
    emergency: EmergencyDamage
    fairness: FairnessConfig
    market: MarketConfig


# Scenario config sub-models
class SupplyWalk(BaseModel):
    sigma: float
    min: float
    max: float
    mean_revert: float


class Shock(BaseModel):
    tick: int
    duration: int
    delta_mw: float
    label: str


class Scenario(BaseModel):
    name: str
    ticks: int = 480
    nominal_supply: float = 100.0
    needs: dict[str, float]
    max_draw: dict[str, float]
    supply_walk: SupplyWalk
    shocks: list[Shock]


def load_damage_params(path: str | Path | None = None) -> dict:
    """Load and validate damage configuration from YAML."""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "config" / "damage.yaml"
    else:
        path = Path(path)
    
    with open(path) as f:
        raw = yaml.safe_load(f)
    
    # Validate with pydantic model
    config = DamageConfig(**raw)
    return config.model_dump()


def load_scenario(path: str | Path | None = None) -> Scenario:
    """Load scenario configuration from YAML."""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "scenarios" / "default_8h.yaml"
    else:
        path = Path(path)
    
    with open(path) as f:
        raw = yaml.safe_load(f)
    
    return Scenario(**raw)