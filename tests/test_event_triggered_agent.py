import json

import pytest

from src import agent
from src.agent import (
    Event, already_processed, dead_letter, handler, process, replay_dlq, sign, verify,
)


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "DLQ", tmp_path / "dlq.jsonl")
    monkeypatch.setattr(agent, "SEEN", tmp_path / "seen.json")
    monkeypatch.setattr(agent, "complete", lambda m, **k: "triage line")


def test_signature_round_trip():
    body = b'{"id":"1"}'
    assert verify(body, sign(body))


def test_bad_signature_rejected():
    assert not verify(b'{"id":"1"}', "deadbeef")


def test_tampered_body_rejected():
    sig = sign(b'{"amount": 10}')
    assert not verify(b'{"amount": 10000}', sig)


def test_idempotency_marker():
    assert not already_processed("evt_1")
    assert already_processed("evt_1")


def test_five_deliveries_do_the_work_once():
    calls = []

    @handler("counted.event")
    def count(ev):
        calls.append(ev.id)
        return "ok"

    ev = Event(id="evt_dup", type="counted.event")
    for _ in range(5):
        process(ev)
    assert len(calls) == 1


def test_failure_lands_in_dlq():
    @handler("always.fails")
    def boom(ev):
        raise RuntimeError("upstream down")

    assert process(Event(id="evt_bad", type="always.fails")) is None
    rows = agent.DLQ.read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(rows[0])["id"] == "evt_bad"


def test_retries_before_dead_lettering():
    attempts = []

    @handler("flaky.always")
    def flaky(ev):
        attempts.append(1)
        raise RuntimeError("nope")

    process(Event(id="evt_flaky", type="flaky.always"))
    assert len(attempts) == agent.MAX_ATTEMPTS


def test_transient_failure_recovers_within_retries():
    attempts = []

    @handler("flaky.once")
    def flaky(ev):
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("transient")
        return "recovered"

    assert process(Event(id="evt_transient", type="flaky.once")) == "recovered"


def test_unknown_event_type_dead_letters():
    assert process(Event(id="evt_unknown", type="nobody.handles.this")) is None
    assert agent.DLQ.exists()


def test_replay_recovers_fixed_handler():
    state = {"broken": True}

    @handler("fixable.event")
    def fixable(ev):
        if state["broken"]:
            raise RuntimeError("still broken")
        return "fixed"

    process(Event(id="evt_fix", type="fixable.event"))
    state["broken"] = False
    result = replay_dlq()
    assert result["recovered"] == 1 and result["still_failing"] == 0


def test_replay_keeps_still_failing_events():
    @handler("never.works")
    def never(ev):
        raise RuntimeError("permanent")

    process(Event(id="evt_never", type="never.works"))
    assert replay_dlq()["still_failing"] == 1
    assert agent.DLQ.exists()
