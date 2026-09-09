"""Canned triage line for MODEL=fake."""
from __future__ import annotations


def respond(messages: list[dict]) -> str:
    return "Checkout failure on mobile - severity high, route to payments team."
