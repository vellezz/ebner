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


# Keywords structured outputs is known to accept. Everything else is dropped
# from the copy sent to the API.
#
# The API rejects the schema outright for an unsupported keyword — `minimum` on
# an integer was the first one found, and finding the rest by trial would cost
# a full write, check and edit per attempt. So the model gets shape only:
# what fields exist, what types they are, which are required, what the allowed
# values are. Ranges, patterns and lengths are dropped, and nothing is lost by
# it, because check-state.mjs validates the result against the complete schema
# before anything is kept.
_STRUCTURAL = {
    "type", "properties", "required", "items", "enum", "const",
    "description", "additionalProperties", "oneOf", "anyOf", "allOf",
}


def schema_for_api(schema: dict) -> dict:
    """Reduce a JSON Schema to what structured outputs accepts.

    $refs are inlined rather than passed through: our only one resolves to a
    constrained string that reduces to a plain string anyway, and an unresolved
    $ref would be one more way for the request to be rejected.
    """
    defs = schema.get("$defs", {})

    def walk(node):
        if isinstance(node, list):
            return [walk(item) for item in node]
        if not isinstance(node, dict):
            return node

        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            return walk(defs.get(ref.split("/")[-1], {}))

        out = {}
        for key, value in node.items():
            if key == "properties":
                out[key] = {name: walk(sub) for name, sub in value.items()}
            elif key == "type" and isinstance(value, list):
                # Union types are another plausible rejection and not worth a
                # paid round trip to confirm. A nullable field is simply an
                # optional one here: none of them are in `required`, so the
                # model omits it instead of sending null.
                concrete = [t for t in value if t != "null"]
                out[key] = concrete[0] if concrete else "string"
            elif key in _STRUCTURAL:
                out[key] = walk(value)
        return out

    return walk({k: v for k, v in schema.items() if k != "$defs"})


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
        output_config["format"] = {
            "type": "json_schema",
            "schema": schema_for_api(output_schema),
        }
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
