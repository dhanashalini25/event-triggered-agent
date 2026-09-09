# 08 - Event-Triggered Automation Agent

> Webhooks in, idempotent work out, dead letters caught.

**What it demonstrates:** Running agents on real event streams without losing or duplicating work

**Status:** working implementation with passing tests. Built as a learning project to understand the pattern, not as a production service.

---

## Run it right now

No API key needed - every project ships with `MODEL=fake`, a deterministic
offline responder, so you can see the whole flow work before spending anything.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
python -m src.main
pytest -q
```

To use a real model, edit `.env`:

```
MODEL=gpt-4o-mini            # + OPENAI_API_KEY
MODEL=claude-3-5-haiku-latest  # + ANTHROPIC_API_KEY
MODEL=ollama/llama3.1        # free, runs locally
```

Run the webhook server:

```bash
uvicorn src.server:app --reload
```

## How it works

A FastAPI endpoint verifies an HMAC signature over the raw body, so a tampered payload or a forged delivery is rejected with a 401 before any work starts. It returns 200 immediately and processes in a background task, which is what keeps webhook providers from timing out and retrying.

Processing is idempotent by event id: the id is recorded before the handler runs, so five deliveries of the same event do the work once. Handlers register by event type and are wrapped in exponential backoff with jitter.

When retries are exhausted the event is written to `dead_letter.jsonl` with its payload and error, and its idempotency marker is cleared so `replay_dlq()` can genuinely retry it after a fix. Events that still fail on replay stay in the queue.

## What "done" means here

- HMAC signatures are verified against the raw body; tampering is rejected
- Five deliveries of one event do the work exactly once
- Transient failures retry with exponential backoff and jitter
- Exhausted events land in a dead-letter queue with payload and error
- Replay re-processes the queue and keeps what still fails
- The endpoint returns 200 immediately and works in the background

Every one of those lines has a test behind it in `tests/` - `pytest -q` is the
proof, not the README.

## Layout

```
src/llm.py             provider-agnostic completion, plus offline fake mode
src/fake.py            the canned responses that make MODEL=fake work
src/logging_setup.py   structured JSON logging
src/agent.py           the pattern itself
src/main.py            CLI entrypoint
src/server.py          FastAPI webhook endpoint + DLQ replay route
tests/                 11 tests, all passing
```

## Next steps

- Move idempotency from a JSON file to Redis `SETNX` with a TTL
- Add a `/dlq` view so failures can be inspected without reading a file
- Load-test the endpoint and record throughput here

## Reference

https://hookdeck.com/webhooks/guides/dead-letter-queues-webhook-reliability

---

Part of a 12-project agentic AI series - [github.com/dhanashalini25](https://github.com/dhanashalini25?tab=repositories)
