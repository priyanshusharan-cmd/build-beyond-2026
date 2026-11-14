"""Deterministic simulation loop. Pure engine: no wall-clock, no global RNG, no LLM.

One `Simulation` runs one strategy on one seeded scenario. All strategies share the same
supply walk (RNG drawn identically every tick), damage model and independent checker.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.random import Generator, PCG64

from . import baselines
from .agents.system import AgentSystem
from .config import Scenario
from .events import EventLog
from .fairness import apply_concession, decay_credit, effective_weight, jain_from_runs
from .invariants import Violation, check_event_order, check_tick
from .ledger import Ledger, fallback_split
from .market import MarketClock
from .models import AGENTS, EventType

TRIP_DURATION = 5  # blind-grab overload trip: -20% supply for 5 ticks
TRIP_FACTOR = 0.8


@dataclass
class TickRecord:
    tick: int
    supply: float
    grants: dict
    need: dict
    served_pct: dict
    damage_tick: float
    damage_cum: float
    cascades: list
    status: dict
    price: float
    rounds_used: int
    used_fallback: bool
    reservoir: float
    battery: float
    violations: int


@dataclass
class RunResult:
    strategy: str
    seed: int
    scenario: str
    log: EventLog
    records: list[TickRecord] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    cascade_count: int = 0
    fallback_ticks: int = 0


class Simulation:
    def __init__(
        self,
        scenario: Scenario,
        params: dict,
        seed: int = 0,
        strategy: str = "ours",
        chaos_schedule: list[tuple[int, str, dict]] | None = None,
    ):
        if strategy not in baselines.STRATEGIES and strategy not in baselines.ABLATIONS:
            raise ValueError(f"unknown strategy {strategy}")
        self.sc = scenario
        self.params = params
        self.seed = seed
        self.strategy = strategy
        self.rng = Generator(PCG64(seed))
        self.system = AgentSystem(params, scenario.needs, scenario.max_draw)
        self.log = EventLog()
        self.ledger = Ledger(scenario.max_draw)
        m = params["market"]
        self.market = MarketClock(m["p0"], m["eta"], m["damping"], m["eps"], int(m["max_rounds"]), m["p_min"])
        self.credits = {a: 0.0 for a in AGENTS}
        self.is_ours = strategy in baselines.OURS_FAMILY
        self.use_l2 = strategy in ("ours", "ours_no_credit")   # Layer 2 bilateral bargaining
        self.use_credit = strategy == "ours"                    # credit banking + credit-weighted bids
        self.l2cfg = params.get("layer2", {})
        self._concessions: list[dict] = []   # accepted, still-honoured concessions
        self._notes: list[tuple[str, str]] = []  # (kind, plain-English text) for this tick
        self._prev_status: dict = {}
        self.tick = 0
        self.base_supply = float(scenario.nominal_supply)
        self.damage_cum = 0.0
        self.trip_until = -1
        self._chaos_queue: list[tuple[int, str, dict]] = sorted(
            chaos_schedule or [], key=lambda c: c[0]
        )
        self._active_supply_shocks: list[tuple[int, float]] = []  # (until_tick, delta)
        self._revert: list[tuple[int, str, dict]] = []  # (at_tick, kind, params)
        self.result = RunResult(strategy, seed, scenario.name, self.log)
        self._served_series = {a: [] for a in AGENTS}
        self._need_series = {a: [] for a in AGENTS}

    # ------------------------------------------------------------------ chaos
    def inject_chaos(self, kind: str, params: dict | None = None) -> None:
        """Live chaos: applied at the start of the next tick."""
        self._chaos_queue.append((self.tick, kind, dict(params or {})))
        self._chaos_queue.sort(key=lambda c: c[0])

    def _apply_chaos(self, kind: str, p: dict) -> None:
        t = self.tick
        dur = int(p.get("duration", 30))
        if kind == "kill_substation":
            mw = float(p.get("mw", 30.0))
            self._active_supply_shocks.append((t + dur, -mw))
        elif kind == "icu_surge":
            self.system.apply_chaos("icu_surge", {"pct": float(p.get("pct", 30.0))})
            self._revert.append((t + dur, "icu_surge", {"pct": 0.0}))
        elif kind == "burst_main":
            self.system.apply_chaos("burst_main", {"drain_mult": float(p.get("drain_mult", 3.0))})
            self._revert.append((t + dur, "burst_main", {"drain_mult": 1.0}))
        else:
            raise ValueError(f"unknown chaos kind {kind}")
        self.log.append(t, EventType.CHAOS_INJECTED, None, {"kind": kind, "params": p, "source": "live"})
        self._notes.append(("chaos", f"Chaos injected: {kind.replace('_', ' ')} for {dur} min."))

    # ----------------------------------------------------------------- supply
    def _supply(self) -> tuple[float, dict]:
        w = self.sc.supply_walk
        noise = float(self.rng.standard_normal())  # always drawn: same walk for all strategies
        self.base_supply += w.mean_revert * (self.sc.nominal_supply - self.base_supply) + w.sigma * noise
        self.base_supply = min(w.max, max(w.min, self.base_supply))
        shock = 0.0
        t = self.tick
        for s in self.sc.shocks:
            if s.tick <= t < s.tick + s.duration:
                shock += s.delta_mw
        self._active_supply_shocks = [(u, d) for (u, d) in self._active_supply_shocks if t < u]
        chaos = sum(d for _, d in self._active_supply_shocks)
        raw = max(0.0, self.base_supply + shock + chaos)
        trip = TRIP_FACTOR if t <= self.trip_until else 1.0
        return raw * trip, {"base": self.base_supply, "shock": shock, "chaos": chaos, "trip": trip != 1.0}

    # ------------------------------------------------------------------- step
    def step(self) -> TickRecord:
        t = self.tick
        # revert expired chaos, apply scheduled / queued chaos
        for r in [r for r in self._revert if r[0] <= t]:
            self.system.apply_chaos(r[1], r[2])
            self._revert.remove(r)
        for s in self.sc.shocks:
            if s.tick == t:
                self.log.append(t, EventType.CHAOS_INJECTED, None,
                                {"kind": "scenario_shock", "label": s.label, "delta_mw": s.delta_mw,
                                 "duration": s.duration, "source": "scenario"})
                self._notes.append(("chaos", f"Scenario event: {s.label} ({s.delta_mw:+.0f} MW for {s.duration} min)."))
        while self._chaos_queue and self._chaos_queue[0][0] <= t:
            _, kind, p = self._chaos_queue.pop(0)
            self._apply_chaos(kind, p)

        supply, sinfo = self._supply()
        self.log.append(t, EventType.SUPPLY_UPDATE, None, {"supply": supply, **sinfo})

        needs = self.system.needs()
        caps = {a: min(needs[a], self.sc.max_draw[a]) for a in AGENTS}

        price, rounds, used_fb, nviol = self.market.price, 0, False, 0
        if self.is_ours:
            grants, price, rounds, used_fb = self._negotiate(t, supply, caps)
        else:
            grants, nviol = self._baseline(t, supply, caps)

        # independent checker on what was actually granted (ours + baselines alike)
        committed = grants
        v = check_tick(t, supply, committed, self.sc.max_draw)
        if self.strategy != "blind":  # blind breach is recorded at request time
            self.result.violations += v
            nviol += len(v)

        served_pct = {a: (min(1.0, committed[a] / needs[a]) if needs[a] > 0 else 1.0) for a in AGENTS}
        res = self.system.step(committed)
        self.damage_cum += res.total
        for a in AGENTS:
            self._served_series[a].append(committed[a])
            self._need_series[a].append(needs[a])
            self.credits[a] = decay_credit(self.credits[a], self.params["fairness"]["credit_decay"])

        self.log.append(t, EventType.DAMAGE_TICK, None,
                        {"damage": res.damage, "total": res.total, "cumulative": self.damage_cum})
        for c in res.cascades:
            self.result.cascade_count += 1
            self.log.append(t, EventType.CASCADE_TRIGGERED, None, {"cascade": c})
        if used_fb:
            self.result.fallback_ticks += 1
        if self.is_ours:
            self._explain(t, supply, used_fb, res)
        self._notes = []
        self.log.append(t, EventType.TICK_SUMMARY, None, {
            "supply": supply, "grants": committed, "served_pct": served_pct,
            "damage_tick": res.total, "damage_cum": self.damage_cum,
            "reservoir": res.reservoir, "battery": res.battery, "price": price,
            "rounds_used": rounds, "used_fallback": used_fb,
        })
        rec = TickRecord(t, supply, dict(committed), dict(needs), served_pct, res.total, self.damage_cum,
                         list(res.cascades), dict(res.status), price, rounds, used_fb,
                         res.reservoir, res.battery, nviol)
        self.result.records.append(rec)
        self.tick += 1
        return rec

    # ------------------------------------------------------------------- ours
    def _negotiate(self, t: int, supply: float, caps: dict):
        lam = self.params["fairness"]["lambda_credit"]

        def bid_fn(name: str, p: float) -> float:
            c = self.credits[name]
            if not self.l2cfg.get("debt_penalizes", False):
                c = max(0.0, c)  # debts are tracked and reported, but never starve a critical load
            mult = effective_weight(1.0, c, lam) if self.use_credit else 1.0
            return self.system.bid(name, p, mult)

        pr = self.market.discover(supply, list(AGENTS), bid_fn)
        for tr in pr.trace:
            self.log.append(t, EventType.PRICE_BROADCAST, None,
                            {"round": tr["round"], "price": tr["price"],
                             "total_demand": tr["total_demand"], "supply": supply})
            for a in AGENTS:
                self.log.append(t, EventType.BID, a, {"round": tr["round"], "price": tr["price"],
                                                      "demand_mw": tr["demands"][a]})
        # settle on the feasible round with the highest total demand (agents' own bids)
        feasible = [tr for tr in pr.trace if tr["total_demand"] <= supply + 1e-9]
        best = max(feasible, key=lambda tr: (tr["total_demand"], -tr["round"])) if feasible else None
        rounds_used = pr.rounds_used
        # price clearing: bisect for the lowest price at which total bids fit supply.
        # Still only the market publishing a price; agents decide their own demands.
        if best is None or best["total_demand"] < supply - self.market.eps:
            best, extra = self._clear_price(t, supply, bid_fn, best, pr)
            rounds_used += extra
        proposal = None
        if best is not None:
            proposal = {a: min(best["demands"][a], caps[a]) for a in AGENTS}
        used_fb = False
        accepted: list[dict] = []
        if proposal is not None:
            if self.use_l2:
                proposal, accepted = self._layer2(t, supply, proposal, caps)
            res = self.ledger.submit(t, supply, proposal)
            self._emit(t, res.events)
            if res.committed:
                self._book_credits(t, accepted)
                return self.ledger.grants, self.market.price, rounds_used, False
        # negotiation failed to settle or ledger rejected: deterministic fallback.
        # Concessions struck this tick were never committed, so they are void (no credit booked).
        self._concessions = [c for c in self._concessions if c not in accepted]
        used_fb = True
        floors = {a: self.system.critical_floor(a) for a in AGENTS}
        fb = fallback_split(supply, self.system.weights(), floors, caps, self.system.names)
        res = self.ledger.commit_fallback(t, supply, fb)
        self._emit(t, res.events)
        grants = self.ledger.grants if res.committed else {a: 0.0 for a in AGENTS}
        return grants, self.market.price, rounds_used, used_fb

    # ------------------------------------------------------- layer 2 bargaining
    def _layer2(self, t: int, supply: float, proposal: dict, caps: dict):
        """Fine bilateral bargaining on top of the Layer 1 settlement.

        Each agent values MW with its own damage function. A low-marginal-damage agent (the
        yielder) offers x MW for T minutes to a high-marginal-damage agent; the counterparty
        accepts, counters (smaller x when the credit it would owe breaches its debt floor) or
        rejects. Transfers conserve total power and respect each agent's cap, and the result
        still goes through ledger propose -> validate -> commit. Returns (proposal, accepted).
        """
        cfg = self.l2cfg
        ag = self.system.agents
        names = self.system.names
        prop = dict(proposal)
        accepted: list[dict] = []

        def gain(a: str, q: float, x: float) -> float:
            return ag[a].weight * (ag[a].valuation(q) - ag[a].valuation(q + x))

        def loss(a: str, q: float, x: float) -> float:
            return ag[a].weight * (ag[a].valuation(q - x) - ag[a].valuation(q))

        # honour still-running concessions while they remain worthwhile
        keep = []
        for c in self._concessions:
            if c["until"] <= t:
                continue
            y, b = c["y"], c["b"]
            x = min(c["mw"], prop[y], caps[b] - prop[b])
            if x > 1e-9 and gain(b, prop[b], x) - loss(y, prop[y], x) > 0:
                prop[y] -= x
                prop[b] += x
                self.log.append(t, EventType.CONCESSION, y, {"to": b, "mw": x, "until": c["until"], "replay": True})
                keep.append(c)
        self._concessions = keep

        T = int(cfg.get("duration_ticks", 5))
        chunks = list(cfg.get("chunks_mw", [0.5, 1.0, 2.0, 4.0]))
        min_gain = float(cfg.get("min_gain", 0.05))
        scale = float(cfg.get("credit_scale", 30.0))
        floor = float(cfg.get("debt_floor", -1.0))
        for rnd in range(1, int(cfg.get("rounds", 3)) + 1):
            best = None
            for y in names:
                for b in names:
                    if y == b:
                        continue
                    for x in chunks:
                        if x > prop[y] + 1e-9 or prop[b] + x > caps[b] + 1e-9:
                            continue
                        net = gain(b, prop[b], x) - loss(y, prop[y], x)
                        if best is None or net > best[0] + 1e-12:
                            best = (net, y, b, x)
            if best is None or best[0] < min_gain:
                break
            net, y, b, x = best
            award = x * T / scale
            self.log.append(t, EventType.OFFER, y, {"to": b, "mw": x, "minutes": T, "credit": award,
                                                    "net_gain": net, "round": rnd})
            if self.use_credit and cfg.get("debt_penalizes", False) and self.credits[b] - award < floor:
                x2 = x / 2.0
                net2 = gain(b, prop[b], x2) - loss(y, prop[y], x2) if x2 <= prop[y] else -1.0
                if net2 < min_gain:
                    self.log.append(t, EventType.COUNTER, b, {"to": y, "action": "reject",
                                                              "reason": "debt_floor", "round": rnd})
                    break
                self.log.append(t, EventType.COUNTER, b, {"to": y, "action": "counter", "mw": x2,
                                                          "reason": "debt_floor", "round": rnd})
                x, net, award = x2, net2, x2 * T / scale
            prop[y] -= x
            prop[b] += x
            c = {"y": y, "b": b, "mw": x, "until": t + T, "credit": award}
            self._concessions.append(c)
            accepted.append(c)
            self.log.append(t, EventType.CONCESSION, y, {"to": b, "mw": x, "minutes": T, "credit": award,
                                                         "net_gain": net, "round": rnd})
            self._notes.append(("concession", f"{y.capitalize()} yields {x:g} MW to {b.capitalize()} "
                                f"for {T} min: {b.capitalize()} gains more from it than {y.capitalize()} loses."))
        return prop, accepted

    def _book_credits(self, t: int, accepted: list[dict]) -> None:
        """After a successful commit, the yielder banks credit and the beneficiary owes it."""
        if not self.use_credit or not accepted:
            return
        cfg = self.l2cfg
        lo, hi = float(cfg.get("debt_floor", -1.0)), float(cfg.get("credit_cap", 3.0))
        for c in accepted:
            new = apply_concession(self.credits, c["y"], c["b"], c["credit"])
            for a in (c["y"], c["b"]):
                new[a] = min(hi, max(lo, new[a]))
            self.credits = new
            for a in (c["y"], c["b"]):
                self.log.append(t, EventType.CREDIT_UPDATE, a,
                                {"credit": self.credits[a], "delta": c["credit"] if a == c["y"] else -c["credit"],
                                 "with": c["b"] if a == c["y"] else c["y"]})

    # ----------------------------------------------------------- explanations
    def _explain(self, t: int, supply: float, used_fb: bool, res) -> None:
        """Deterministic plain-English explanation events (templates, no LLM, never read by agents)."""
        notes = list(self._notes)
        if used_fb:
            notes.append(("fallback", "Negotiation did not settle safely, so the deterministic fallback split was applied."))
        for c in res.cascades:
            what = ("Water pressure is low: hospital cooling load rises 20%." if c == "A"
                    else "Telecom battery is empty: emergency response is less effective.")
            notes.append(("cascade", what))
        for a, s in res.status.items():
            prev = self._prev_status.get(a)
            if prev is not None and prev != s:
                notes.append(("status", f"{a.capitalize()} went from {prev} to {s}."))
        self._prev_status = dict(res.status)
        for kind, text in notes:
            self.log.append(t, EventType.EXPLANATION, None, {"kind": kind, "text": text})

    def _clear_price(self, t: int, supply: float, bid_fn, best, pr):
        """Bisection price clearing (max 20 extra rounds). Returns (best_round, rounds_used)."""
        pmin = self.market.p_min
        extra = 0

        def probe(p: float):
            nonlocal extra
            extra += 1
            d = {a: bid_fn(a, p) for a in AGENTS}
            tot = sum(d.values())
            self.log.append(t, EventType.PRICE_BROADCAST, None,
                            {"round": pr.rounds_used + extra, "price": p, "total_demand": tot,
                             "supply": supply, "phase": "clearing"})
            for a in AGENTS:
                self.log.append(t, EventType.BID, a, {"round": pr.rounds_used + extra, "price": p,
                                                      "demand_mw": d[a]})
            return {"price": p, "total_demand": tot, "demands": d, "round": pr.rounds_used + extra}

        lo = pmin
        r = probe(lo)
        if r["total_demand"] <= supply + 1e-9:
            self.market.price = lo
            return r, extra
        hi = max(pr.price, self.market.price, 2 * pmin)
        r_hi = probe(hi)
        for _ in range(8):
            if r_hi["total_demand"] <= supply + 1e-9:
                break
            hi *= 2.0
            r_hi = probe(hi)
        if r_hi["total_demand"] > supply + 1e-9:
            return best, extra
        cand = r_hi
        r_lo = r
        for _ in range(9):
            mid = 0.5 * (lo + hi)
            r = probe(mid)
            if r["total_demand"] <= supply + 1e-9:
                hi, cand = mid, r
            else:
                lo, r_lo = mid, r
        # Agents indifferent at the clearing price (demand jumps between the two bracketing
        # prices) take the residual supply, in public priority order. Their own declared
        # willingness bounds the amount: nobody receives more than they bid at the lower price.
        slack = supply - cand["total_demand"]
        if slack > 1e-9:
            dem = dict(cand["demands"])
            for a in self.system.names:
                add = min(max(0.0, r_lo["demands"][a] - dem[a]), slack)
                dem[a] += add
                slack -= add
            cand = {**cand, "demands": dem, "total_demand": sum(dem.values())}
        if best is None or cand["total_demand"] >= best["total_demand"]:
            best = cand
            self.market.price = cand["price"]
        return best, extra

    def _emit(self, t: int, events: list) -> None:
        for typ, agent, payload in events:
            self.log.append(t, EventType(typ), agent, payload)

    # -------------------------------------------------------------- baselines
    def _baseline(self, t: int, supply: float, caps: dict):
        nviol = 0
        if self.strategy == "blind":
            req = baselines.blind_request(caps)
            v = check_tick(t, supply, req, self.sc.max_draw)
            if v:  # capacity breach: grid overload + trip
                self.result.violations += v
                nviol = len(v)
                self.trip_until = t + TRIP_DURATION
                self.result.cascade_count += 1
                self.log.append(t, EventType.CASCADE_TRIGGERED, None,
                                {"cascade": "OVERLOAD_TRIP", "requested": sum(req.values()), "supply": supply})
            grants = baselines.curtail_proportional(req, supply)
        elif self.strategy == "proportional":
            grants = baselines.proportional_allocate(caps, supply)
        else:
            grants = baselines.priority_allocate(caps, supply, self.params["priority_order"])
        self.log.append(t, EventType.COMMIT, None, {"grants": grants, "baseline": self.strategy})
        return grants, nviol

    # -------------------------------------------------------------- reporting
    def snapshot(self) -> dict:
        rec = self.result.records[-1]
        return {
            "tick": rec.tick, "supply": rec.supply, "grants": rec.grants, "need": rec.need,
            "served_pct": rec.served_pct, "damage_cum": rec.damage_cum,
            "jain": jain_from_runs(self._served_series, self._need_series),
            "cascades": self.result.cascade_count, "credits": dict(self.credits),
            "status": rec.status,
        }

    def run(self) -> RunResult:
        while self.tick < self.sc.ticks:
            self.step()
        if self.is_ours:
            evs = [self.log.event_dict(e) for e in self.log.events]
            self.result.violations += check_event_order(evs)
        return self.result


def run_simulation(scenario: Scenario, params: dict, seed: int, strategy: str,
                   chaos_schedule=None) -> RunResult:
    return Simulation(scenario, params, seed, strategy, chaos_schedule).run()
