"""Structured JSON logging - identical shape in all 12 projects."""
from __future__ import annotations

import json
import logging
import os
import sys

RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime"}


def safe_extra(fields: dict) -> dict:
    """Rename keys that would collide with LogRecord's own attributes.

    Passing extra={"args": ...} to the logging module raises KeyError, which is
    a miserable way to lose a log line. Anything colliding gets an f_ prefix.
    """
    return {(f"f_{k}" if k in RESERVED else k): v for k, v in fields.items()}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        payload.update({k: v for k, v in record.__dict__.items() if k not in RESERVED})
        return json.dumps(payload, default=str)


handler = logging.StreamHandler(sys.stderr)
handler.setFormatter(JsonFormatter())

log = logging.getLogger("agent")
log.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
log.handlers = [handler]
log.propagate = False
