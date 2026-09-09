"""Webhook endpoint. Returns 200 immediately and works in the background.

    uvicorn src.server:app --reload
    # then, from PowerShell:
    #   $body = '{"id":"evt_1","type":"ticket.created","payload":{"text":"checkout down"}}'
    #   $sig  = python -c "from src.agent import sign; import sys; print(sign(sys.argv[1].encode()))" $body
    #   Invoke-RestMethod -Uri http://127.0.0.1:8000/webhook -Method Post -Body $body `
    #       -ContentType application/json -Headers @{ 'X-Signature' = $sig }
"""
from __future__ import annotations

import json

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from .agent import Event, process, replay_dlq, verify

app = FastAPI(title="Event-Triggered Agent")


@app.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks,
                  x_signature: str = Header(default="")):
    body = await request.body()
    if not verify(body, x_signature):
        raise HTTPException(status_code=401, detail="bad signature")

    data = json.loads(body)
    ev = Event(id=data["id"], type=data["type"], payload=data.get("payload", {}))
    background.add_task(process, ev)
    return {"accepted": ev.id}


@app.post("/dlq/replay")
def replay():
    return replay_dlq()


@app.get("/health")
def health():
    return {"ok": True}
