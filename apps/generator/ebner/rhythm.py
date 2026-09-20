"""The randomiser: what kind of entry, how long, how far the date moves.

Order matters here. The kind is drawn first because the day step depends on it
— only entries that are about being on the move may carry the longer hops —
and because the bias toward continuing an open thread is a property of the
kind, not of the length.

Nothing in here talks to a model. It is deterministic given a seed, which is
what makes it testable without spending anything.
"""

from __future__ import annotations

import random
from typing import Any


def _weighted(rng: random.Random, options: list[dict], weights: dict[str, float] | None = None) -> dict:
    """Pick one option, optionally scaling weights by id."""
    scaled = []
    for option in options:
        weight = float(option["weight"])
        if weights:
            weight *= float(weights.get(option["id"], 1.0))
        scaled.append(weight)
    if sum(scaled) <= 0:
        raise ValueError("every weight is zero")
    return rng.choices(options, weights=scaled, k=1)[0]


def pick_kind(cfg: dict, world: dict, rng: random.Random) -> dict:
    """Lean into what is already running rather than starting again."""
    bias = cfg.get("kind_bias", {})
    if world.get("threads_due_for_closure"):
        weights = bias.get("when_open_thread_due")
    elif not world.get("threads_active"):
        weights = bias.get("when_no_open_threads")
    else:
        weights = None
    return _weighted(rng, cfg["kind"], weights)


def pick_day_step(cfg: dict, kind_id: str, rng: random.Random) -> int:
    """How far the in-world date advances.

    The mean matters more than the cap: at one entry per real day it decides
    how fast the world ages. Steps above three are reserved for entries that
    are about being on the move, so a quiet day at the home dock cannot
    silently swallow a week.
    """
    day_step = cfg["day_step"]
    allowed_long = set(day_step.get("allow_above_3_only_for", []))
    cap = int(day_step["cap"])

    candidates: list[dict] = []
    for step_str, weight in day_step["weights"].items():
        step = int(step_str)
        if step > cap:
            continue
        if step > 3 and kind_id not in allowed_long:
            continue
        candidates.append({"id": str(step), "weight": weight, "step": step})
    return int(_weighted(rng, candidates)["step"])


def pick_length(cfg: dict, rng: random.Random) -> dict:
    return _weighted(rng, cfg["length"], None)


def pick_hint(cfg: dict, rng: random.Random) -> tuple[str | None, str | None]:
    """A hint the writer may ignore if it does not fit the world state."""
    probabilities = cfg["hint_probability"]
    pools = list(probabilities.keys())
    pool = rng.choices(pools, weights=[probabilities[p] for p in pools], k=1)[0]
    if pool == "none":
        return None, None
    return pool, rng.choice(cfg["hints"][pool])


def wants_new_destination(cfg: dict, world: dict, rng: random.Random) -> bool:
    """Whether today should reach somewhere new.

    Scheduled rather than left to emerge: growth by accident either stalls or
    floods, and both only become visible a hundred entries later.
    """
    low, high = cfg["world_growth"]["new_destination_every"]
    since = world.get("entries_since_new_place")
    if since is None:
        return True
    return since >= rng.randint(int(low), int(high))


def plan_entry(cfg: dict, world: dict, *, seed: int | None = None) -> dict[str, Any]:
    """Draw every parameter for one entry."""
    rng = random.Random(seed)

    kind = pick_kind(cfg, world, rng)
    step = pick_day_step(cfg, kind["id"], rng)
    length = pick_length(cfg, rng)
    hint_pool, hint = pick_hint(cfg, rng)

    prefer_known = kind["id"] in cfg["world_growth"]["revisit_pressure"]["prefer_known_for"]
    new_destination = (not prefer_known) and wants_new_destination(cfg, world, rng)

    return {
        "day": world["last_day"] + step,
        "day_step": step,
        "kind": kind["id"],
        "kind_label": kind["label"],
        "length": length["id"],
        "length_words": length["words"],
        "length_label": length["label"],
        "hint_pool": hint_pool,
        "hint": hint,
        "new_destination": new_destination,
        "seed": seed,
    }
