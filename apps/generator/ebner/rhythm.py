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


# A thread can only be continued or resolved if its policy allows developing
# it. `mention` and `do_not_touch` threads are not material for a continuation.
DEVELOPABLE = {"develop", "may_return"}

# Kinds that need something developable to exist.
NEEDS_THREAD = {"continuation", "resolution"}


def pick_kind(cfg: dict, world: dict, rng: random.Random) -> dict:
    """Lean into what is already running — but only what may actually be run.

    Drawing `continuation` when every open thread is `mention` sets the writer
    an impossible task: develop this, but you may not develop it. It obeys the
    kind, the consistency check blocks the result, and the day costs the price
    of the prose for nothing. That happened before this existed.
    """
    developable = [
        t for t in world.get("threads", []) if t.get("reference_policy") in DEVELOPABLE
    ]
    options = cfg["kind"]
    if not developable:
        options = [k for k in options if k["id"] not in NEEDS_THREAD]

    bias = cfg.get("kind_bias", {})
    if developable and world.get("threads_due_for_closure"):
        weights = bias.get("when_open_thread_due")
    elif not world.get("threads_active"):
        weights = bias.get("when_no_open_threads")
    else:
        weights = None
    return _weighted(rng, options, weights)


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


def pick_length(cfg: dict, rng: random.Random, kind_id: str | None = None) -> dict:
    """How long the entry runs.

    Some kinds cannot be told in a note. Day 22 drew `travel` at note length
    and produced a hundred and forty-five words in which nothing travelled —
    a journey needs room for a departure, a way and an arrival, and given two
    hundred words the writer drops all three and describes a lift. The bands a
    kind may not draw are listed in rhythm.yaml, next to the kinds themselves.
    """
    options = cfg["length"]
    forbidden = (cfg.get("length_floor") or {}).get(kind_id or "", [])
    if forbidden:
        allowed = [o for o in options if o["id"] not in forbidden]
        if allowed:
            options = allowed
    return _weighted(rng, options, None)


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
    length = pick_length(cfg, rng, kind["id"])
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
