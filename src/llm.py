"""Provider-agnostic LLM call, with an offline fake mode.

Set MODEL in .env:
  MODEL=fake                     -> no network, no key, deterministic canned replies
  MODEL=gpt-4o-mini              -> OpenAI      (needs OPENAI_API_KEY)
  MODEL=claude-3-5-haiku-latest  -> Anthropic   (needs ANTHROPIC_API_KEY)
  MODEL=ollama/llama3.1          -> local Ollama, free
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = os.getenv("MODEL", "fake")


FAKE_NAMES = {"fake", "offline", "none"}


def is_fake(model: str | None = None) -> bool:
    """Fake mode is global: MODEL=fake wins even when a caller names a real model.

    That matters for the cost router, which passes a concrete model per tier -
    without this, offline mode would try to reach OpenAI.
    """
    if DEFAULT_MODEL.lower() in FAKE_NAMES:
        return True
    return (model or DEFAULT_MODEL).lower() in FAKE_NAMES


def complete(messages: list[dict], model: str | None = None, **kwargs) -> str:
    """Return the assistant's text for `messages`."""
    if is_fake(model):
        from .fake import respond

        return respond(messages)

    from litellm import completion

    resp = completion(model=model or DEFAULT_MODEL, messages=messages, **kwargs)
    return resp.choices[0].message.content or ""


def complete_raw(messages: list[dict], model: str | None = None, **kwargs):
    """Full response object, for token and cost accounting."""
    if is_fake(model):
        raise RuntimeError("complete_raw needs a real model; set MODEL in .env")

    from litellm import completion

    return completion(model=model or DEFAULT_MODEL, messages=messages, **kwargs)
