"""Anthropic calls, routed per step from config/models.yaml.

The spec named LiteLLM, and this is a deliberate departure: all four text steps
go to Anthropic, so an abstraction over one provider costs a dependency and
buys nothing. Its value was ever cross-provider, and the only other provider in
the plan is OpenRouter for sketches — one call, at build step 6, with a shape
nothing else shares. Revisit then, not now.

Streaming is used throughout: max_tokens here is large enough that a
non-streaming request risks an HTTP timeout, and the SDK asks for streaming
above that threshold anyway.
"""

from __future__ import annotations

import os

from .config import load


class LLMError(RuntimeError):
    pass


def _client():
    try:
        import anthropic
    except ImportError as error:  # pragma: no cover
        raise LLMError("the `anthropic` package is not installed") from error

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise LLMError(
            "no Anthropic credential — set ANTHROPIC_API_KEY, or sign in with "
            "`ant auth login` so the SDK picks up the stored profile"
        )
    return anthropic.Anthropic()


def step_config(step: str) -> dict:
    steps = load("models.yaml")["steps"]
    if step not in steps:
        raise LLMError(f"no such step in models.yaml: {step}")
    return steps[step]


def complete(step: str, system: str, user: str, *, output_schema: dict | None = None) -> str:
    """Run one step and return its text.

    `output_schema` constrains the reply to valid JSON matching that schema.
    Used by state extraction, where an invalid shape would fail a guard later
    anyway — better to make it impossible than to catch it downstream.
    """
    cfg = step_config(step)
    client = _client()

    kwargs: dict = {
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }

    output_config: dict = {}
    if cfg.get("effort"):
        output_config["effort"] = cfg["effort"]
    if output_schema is not None:
        output_config["format"] = {"type": "json_schema", "schema": output_schema}
    if output_config:
        kwargs["output_config"] = output_config

    try:
        with client.messages.stream(**kwargs) as stream:
            message = stream.get_final_message()
    except TypeError as error:
        # An SDK too old to know output_config reports it this way. Say so
        # rather than letting it surface as an opaque argument error.
        raise LLMError(
            f"the installed anthropic SDK rejected a request field ({error}). "
            "This pipeline needs a version that supports output_config."
        ) from error

    if getattr(message, "stop_reason", None) == "refusal":
        raise LLMError(f"model declined the request: {getattr(message, 'stop_details', None)}")

    parts = [block.text for block in message.content if getattr(block, "type", "") == "text"]
    text = "".join(parts).strip()
    if not text:
        raise LLMError(f"step `{step}` returned no text (stop_reason={message.stop_reason})")
    return text
