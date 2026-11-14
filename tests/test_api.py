from fastapi.testclient import TestClient

from api.app import app

client = TestClient(app)


def test_health_and_scenarios():
    assert client.get("/health").json()["ok"] is True
    names = [s["name"] for s in client.get("/scenarios").json()]
    assert "default_8h" in names


def test_unknown_scenario_and_path_escape():
    assert client.post("/runs", json={"scenario": "nope"}).status_code == 404
    assert client.post("/runs", json={"scenario": "../config/damage"}).status_code == 404


def test_stream_runs_to_completion_with_chaos():
    run = client.post("/runs", json={"seed": 3, "strategy": "ours", "speed": 480}).json()
    rid = run["run_id"]
    assert client.post(f"/runs/{rid}/chaos", json={"kind": "kill_substation",
                                                   "params": {"mw": 20, "duration": 10}}).status_code == 200
    seen, final = 0, None
    with client.websocket_connect(f"/runs/{rid}/stream") as ws:
        while True:
            msg = ws.receive_json()
            seen += len(msg["events"])
            if msg["done"]:
                final = msg
                break
    assert final["snapshot"]["tick"] == 479
    assert final["metrics"]["violations"] == 0
    evs = client.get(f"/runs/{rid}/events", params={"from": 0, "limit": 50000}).json()
    assert len(evs["events"]) == seen
    assert any(e["type"] == "CHAOS_INJECTED" and e["payload"].get("source") == "live" for e in evs["events"])
    tail = client.get(f"/runs/{rid}/events", params={"from": seen - 5}).json()
    assert [e["seq"] for e in tail["events"]] == list(range(seen - 5, seen))
    assert client.post(f"/runs/{rid}/chaos", json={"kind": "icu_surge"}).status_code == 409


def test_compare_same_seed_all_strategies():
    body = client.get("/compare", params={"seed": 0}).json()
    assert set(body["strategies"]) == {"ours", "blind", "proportional", "priority"}
    assert body["strategies"]["ours"]["violations"] == 0
    assert body["strategies"]["blind"]["violations"] > 0


def test_compare_series_matches_totals():
    body = client.get("/compare", params={"seed": 0}).json()["strategies"]
    for m in body.values():
        assert m["series"][-1]["tick"] == 479
        assert abs(m["series"][-1]["damage_cum"] - m["total_damage"]) < 1e-6
