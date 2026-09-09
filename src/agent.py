"""Event-Triggered Automation Agent - webhooks that behave in production.

Signatures are verified, duplicate deliveries do the work once, transient
failures retry with backoff, and anything that exhausts its retries lands in a
dead-letter queue that can be replayed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tenacity import RetryError, retry, stop_after_attempt, wait_exponential_jitter

from .llm import complete
from .logging_setup import log

DLQ = Path("dead_letter.jsonl")
SEEN = Path("processed.json")
MAX_ATTEMPTS = 3
SECRET = os.getenv("WEBHOOK_SECRET", "dev-secret")
DEMO = "ticket.created: checkout is failing for mobile users"


@dataclass
class Event:
    id: str
    type: str
    payload: dict = field(default_factory=dict)


# ------------------------------------------------------------- security
def sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify(body: bytes, signature: str, secret: str = SECRET) -> bool:
    return hmac.compare_digest(sign(body, secret), signature or "")


# ---------------------------------------------------------- idempotency
def _seen() -> set[str]:
    if not SEEN.exists():
        return set()
    return set(json.loads(SEEN.read_text(encoding="utf-8")))


def mark_seen(event_id: str) -> None:
    ids = _seen() | {event_id}
    SEEN.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def forget(event_id: str) -> None:
    ids = _seen() - {event_id}
    SEEN.write_text(json.dumps(sorted(ids)), encoding="utf-8")


def already_processed(event_id: str) -> bool:
    if event_id in _seen():
        log.info("duplicate_event", extra={"id": event_id})
        return True
    mark_seen(event_id)
    return False


# ------------------------------------------------------------ handlers
HANDLERS: dict[str, Callable[[Event], str]] = {}


def handler(event_type: str):
    def deco(fn):
        HANDLERS[event_type] = fn
        return fn

    return deco


@handler("ticket.created")
def triage(ev: Event) -> str:
    summary = complete([{
        "role": "user",
        "content": "Triage this ticket in one line:\n" + json.dumps(ev.payload),
    }])
    return f"triaged: {summary.strip()}"


@handler("build.failed")
def notify(ev: Event) -> str:
    return f"notified #eng about build {ev.payload.get('build', '?')}"


@retry(stop=stop_after_attempt(MAX_ATTEMPTS),
       wait=wait_exponential_jitter(initial=0.1, max=2), reraise=True)
def _dispatch(ev: Event) -> str:
    fn = HANDLERS.get(ev.type)
    if not fn:
        raise ValueError(f"no handler for {ev.type}")
    return fn(ev)


# ------------------------------------------------------------ dead letter
def dead_letter(ev: Event, error: str) -> None:
    with DLQ.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(
            {"id": ev.id, "type": ev.type, "payload": ev.payload, "error": error}
        ) + "\n")
    log.error("dead_lettered", extra={"id": ev.id, "error": error[:200]})


def process(ev: Event) -> str | None:
    """Returns None for a duplicate or a failure; the result otherwise."""
    if already_processed(ev.id):
        return None
    try:
        result = _dispatch(ev)
        log.info("processed", extra={"id": ev.id, "type": ev.type})
        return result
    except (RetryError, Exception) as err:  # noqa: BLE001
        forget(ev.id)  # so a replay can try again
        dead_letter(ev, repr(err))
        return None


def replay_dlq() -> dict:
    """Re-run everything in the dead-letter queue; keep what still fails."""
    if not DLQ.exists():
        return {"replayed": 0, "recovered": 0, "still_failing": 0}

    rows = [json.loads(line) for line in DLQ.read_text(encoding="utf-8").splitlines() if line]
    DLQ.unlink()
    recovered = 0
    for row in rows:
        ev = Event(id=row["id"], type=row["type"], payload=row["payload"])
        if process(ev) is not None:
            recovered += 1

    still = len(rows) - recovered
    log.info("dlq_replayed", extra={"total": len(rows), "recovered": recovered})
    return {"replayed": len(rows), "recovered": recovered, "still_failing": still}


def run(prompt: str) -> str:
    kind, _, text = prompt.partition(":")
    ev = Event(
        id=f"manual-{abs(hash(prompt)) % 10**8}",
        type=kind.strip() if kind.strip() in HANDLERS else "ticket.created",
        payload={"text": text.strip() or prompt},
    )
    result = process(ev)
    return result or "duplicate or dead-lettered - see dead_letter.jsonl"
