"""FastAPI layer. Streaming pace lives only here; the engine stays pure and deterministic.

A run owns one engine Simulation. A per-run driver task advances it tick by tick at the run's
pace; WebSocket clients tail the append-only event log from their own cursor.
"""
from __future__ import annotations

import asyncio
import sys
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from blackout_arena.config import load_damage_params, load_scenario  # noqa: E402
from blackout_arena.events import EventLog  # noqa: E402
from blackout_arena.invariants import check_event_order  # noqa: E402
from blackout_arena.metrics import compute_metrics  # noqa: E402
from blackout_arena.baselines import STRATEGIES  # noqa: E402
from blackout_arena.sim import Simulation, run_simulation  # noqa: E402

SCENARIO_DIR = ROOT / "scenarios"
Strategy = Literal["ours", "blind", "proportional", "priority"]
ChaosKind = Literal["kill_substation", "icu_surge", "burst_main"]


def scenario_path(name: str) -> Path:
    p = (SCENARIO_DIR / f"{name}.yaml").resolve()
    if p.parent != SCENARIO_DIR.resolve() or not p.is_file():
        raise HTTPException(404, f"unknown scenario '{name}'")
    return p


class RunRequest(BaseModel):
    scenario: str = "default_8h"
    seed: int = 0
    strategy: Strategy = "ours"
    speed: float = Field(8.0, gt=0, le=480, description="ticks per second when streaming")


class ChaosRequest(BaseModel):
    kind: ChaosKind
    params: dict = {}


class ControlRequest(BaseModel):
    speed: float | None = Field(None, gt=0, le=480)
    paused: bool | None = None


class Run:
    def __init__(self, req: RunRequest):
        self.id = uuid.uuid4().hex[:10]
        self.req = req
        self.scenario = load_scenario(scenario_path(req.scenario))
        self.sim = Simulation(self.scenario, load_damage_params(), req.seed, req.strategy)
        self.speed = req.speed
        self.paused = False
        self.task: asyncio.Task | None = None
        self.changed = asyncio.Event()
        self.chaos_log: list[dict] = []

    @property
    def done(self) -> bool:
        return self.sim.tick >= self.scenario.ticks

    def info(self) -> dict:
        return {
            "run_id": self.id, **self.req.model_dump(), "speed": self.speed, "tick": self.sim.tick,
            "ticks": self.scenario.ticks, "done": self.done, "paused": self.paused,
            "needs": self.scenario.needs, "max_draw": self.scenario.max_draw,
            "nominal_supply": self.scenario.nominal_supply,
            "shocks": [s.model_dump() for s in self.scenario.shocks],
        }

    def snapshot(self) -> dict | None:
        return self.sim.snapshot() if self.sim.result.records else None

    def step(self) -> None:
        self.sim.step()
        if self.done and self.sim.strategy == "ours":
            evs = [EventLog.event_dict(e) for e in self.sim.log.events]
            self.sim.result.violations += check_event_order(evs)

    def _notify(self) -> None:
        old, self.changed = self.changed, asyncio.Event()
        old.set()

    async def drive(self) -> None:
        while not self.done:
            if self.paused:
                await asyncio.sleep(0.05)
                continue
            self.step()
            self._notify()
            await asyncio.sleep(1.0 / self.speed)
        self._notify()

    def ensure_driver(self) -> None:
        if self.task is None and not self.done:
            self.task = asyncio.create_task(self.drive())


RUNS: dict[str, Run] = {}

app = FastAPI(title="Blackout Arena API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_run(run_id: str) -> Run:
    if run_id not in RUNS:
        raise HTTPException(404, f"unknown run '{run_id}'")
    return RUNS[run_id]


@app.get("/health")
def health() -> dict:
    return {"ok": True, "runs": len(RUNS)}


@app.get("/scenarios")
def scenarios() -> list[dict]:
    out = []
    for p in sorted(SCENARIO_DIR.glob("*.yaml")):
        sc = load_scenario(p)
        out.append({"name": p.stem, "ticks": sc.ticks, "nominal_supply": sc.nominal_supply,
                    "needs": sc.needs, "shocks": [s.model_dump() for s in sc.shocks]})
    return out


@app.post("/runs")
def create_run(req: RunRequest) -> dict:
    run = Run(req)
    RUNS[run.id] = run
    return run.info()


@app.get("/runs/{run_id}")
def run_info(run_id: str) -> dict:
    run = get_run(run_id)
    out = run.info()
    out["snapshot"] = run.snapshot()
    out["chaos"] = run.chaos_log
    if run.done:
        out["metrics"] = compute_metrics(run.sim.result)
    return out


@app.get("/runs/{run_id}/events")
def run_events(run_id: str, from_: int = Query(0, alias="from", ge=0),
               limit: int = Query(5000, ge=1, le=50000)) -> dict:
    run = get_run(run_id)
    evs = run.sim.log.from_seq(from_)[:limit]
    return {"events": [EventLog.event_dict(e) for e in evs], "next": from_ + len(evs), "done": run.done}


@app.post("/runs/{run_id}/chaos")
def inject_chaos(run_id: str, req: ChaosRequest) -> dict:
    run = get_run(run_id)
    if run.done:
        raise HTTPException(409, "run already finished; start a new run to inject chaos")
    run.sim.inject_chaos(req.kind, req.params)
    entry = {"tick": run.sim.tick, "kind": req.kind, "params": req.params}
    run.chaos_log.append(entry)
    return {"queued": entry}


@app.post("/runs/{run_id}/control")
def control(run_id: str, req: ControlRequest) -> dict:
    run = get_run(run_id)
    if req.speed is not None:
        run.speed = req.speed
    if req.paused is not None:
        run.paused = req.paused
    return run.info()


@app.websocket("/runs/{run_id}/stream")
async def stream(ws: WebSocket, run_id: str) -> None:
    if run_id not in RUNS:
        await ws.close(code=4404)
        return
    run = RUNS[run_id]
    await ws.accept()
    cursor = int(ws.query_params.get("from", 0))
    run.ensure_driver()
    try:
        while True:
            waiter = run.changed
            evs = run.sim.log.from_seq(cursor)
            if evs:
                cursor += len(evs)
                await ws.send_json({"events": [EventLog.event_dict(e) for e in evs],
                                    "snapshot": run.snapshot(), "done": False})
            if run.done:
                await ws.send_json({"events": [], "snapshot": run.snapshot(), "done": True,
                                    "metrics": compute_metrics(run.sim.result)})
                break
            await waiter.wait()
    except WebSocketDisconnect:
        return
    await ws.close()


@lru_cache(maxsize=64)
def _compare_cached(scenario: str, seed: int) -> dict:
    sc, params = load_scenario(scenario_path(scenario)), load_damage_params()
    out = {}
    for strat in STRATEGIES:
        run = run_simulation(sc, params, seed, strat)
        m = compute_metrics(run)
        # every 5th minute: cumulative damage and mean share of need met (for over-time charts)
        m["series"] = [
            {"tick": r.tick, "damage_cum": r.damage_cum,
             "served_avg": sum(r.served_pct.values()) / len(r.served_pct), "supply": r.supply}
            for r in run.records if r.tick % 5 == 0 or r.tick == len(run.records) - 1
        ]
        out[strat] = m
    return out


@app.get("/compare")
async def compare(scenario: str = "default_8h", seed: int = 0) -> dict:
    scenario_path(scenario)
    metrics = await run_in_threadpool(_compare_cached, scenario, seed)
    return {"scenario": scenario, "seed": seed, "damage_note": "modeled proxy", "strategies": metrics}


# --- production (e.g. Render): one service serves the built dashboard and the API under /api ---
from fastapi.staticfiles import StaticFiles  # noqa: E402
from starlette.types import Receive, Scope, Send  # noqa: E402

_DIST = ROOT / "web" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="web")

_api = app


async def app(scope: Scope, receive: Receive, send: Send) -> None:  # noqa: F811
    """Strip a leading /api so the dashboard's /api/... calls (HTTP and WebSocket) reach the routes."""
    if scope["type"] in ("http", "websocket") and scope["path"].startswith("/api/"):
        scope = dict(scope, path=scope["path"][4:], raw_path=scope["path"][4:].encode())
    await _api(scope, receive, send)
