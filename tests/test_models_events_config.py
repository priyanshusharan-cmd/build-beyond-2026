from blackout_arena.config import load_damage_params, load_scenario
from blackout_arena.events import EventLog
from blackout_arena.models import EventType, tick_to_hhmm


def test_tick_to_hhmm():
    assert tick_to_hhmm(0) == "00:00"
    assert tick_to_hhmm(61) == "01:01"
    assert tick_to_hhmm(479) == "07:59"


def test_seq_increments_and_roundtrip(tmp_path):
    log = EventLog()
    a = log.append(0, EventType.SUPPLY_UPDATE, None, {"supply": 100.123456789})
    b = log.append(1, EventType.BID, "water", {"q": 1.0})
    assert (a.seq, b.seq) == (0, 1)
    p = tmp_path / "e.jsonl"
    log.write(p)
    back = EventLog.read(p)
    assert back.to_jsonl() == log.to_jsonl()
    assert a.payload["supply"] == 100.123457


def test_byte_determinism():
    def build():
        log = EventLog()
        for i in range(5):
            log.append(i, EventType.TICK_SUMMARY, None, {"b": 1.0, "a": {"z": 2, "y": 0.1 + 0.2}})
        return log.to_jsonl()

    assert build() == build()


def test_configs_load():
    d = load_damage_params()
    assert d["weights"]["hospital"] == 10.0
    assert d["priority_order"] == ["hospital", "emergency", "telecom", "water"]
    assert d["market"]["max_rounds"] == 8
    s = load_scenario()
    assert s.ticks == 480 and sum(s.needs.values()) == 92
    assert len(s.shocks) == 3
