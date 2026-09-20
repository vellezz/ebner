"""Assembling what the writer is told about the world.

Reads D1 and renders the Polish blocks the prompt expects. Two rules shape
everything here:

  A fact absent from this context has stopped being true. Only facts with
  valid_to IS NULL are surfaced, so the writer cannot cite something the world
  has moved past.

  Threads carry their reference policy with them. A fragment labelled
  `[nie dotykać]` must never reach the prompt at all; the rest are labelled so
  the writer knows what it may do with them.
"""

from __future__ import annotations

from .d1 import query

POLICY_LABEL = {
    "develop": "rozwijaj",
    "mention": "tylko wzmianka",
    "may_return": "może wrócić",
    "do_not_touch": "nie dotykać",
}

# How long a place goes unvisited before the context offers it back. Mirrors
# rhythm.yaml world_growth.revisit_pressure.stale_after_days.
STALE_AFTER_DAYS = 60


def _summary(remote: bool) -> dict:
    rows = query(
        "SELECT "
        "(SELECT COALESCE(MAX(day), 0) FROM entries) AS last_day, "
        "(SELECT COUNT(*) FROM entries) AS entry_count, "
        "(SELECT COUNT(*) FROM threads WHERE status = 'active') AS threads_active, "
        "(SELECT COUNT(*) FROM threads WHERE status = 'active' AND type = 'recurring') "
        "AS threads_recurring, "
        "(SELECT COUNT(*) FROM entries WHERE day > COALESCE("
        "(SELECT MAX(first_entry) FROM entities WHERE kind = 'place'), 0)) "
        "AS entries_since_new_place",
        remote=remote,
    )
    return rows[0]


def _location(remote: bool) -> list[dict]:
    """Where the last entry ended, with everything that contains it."""
    return query(
        "WITH RECURSIVE chain(id, kind, name, parent, summary, depth) AS ("
        "  SELECT e.id, e.kind, e.name, e.parent, e.summary, 0 FROM entities e"
        "  WHERE e.id = (SELECT location FROM entries ORDER BY day DESC LIMIT 1)"
        "  UNION ALL"
        "  SELECT p.id, p.kind, p.name, p.parent, p.summary, chain.depth + 1"
        "  FROM entities p JOIN chain ON p.id = chain.parent"
        ") SELECT * FROM chain ORDER BY depth",
        remote=remote,
    )


def _threads(remote: bool) -> list[dict]:
    return query(
        "SELECT id, type, status, reference_policy, summary, opened_day, "
        "last_used_day, planned_entries, cooldown_days, reference_count "
        "FROM threads WHERE status = 'active' ORDER BY opened_day",
        remote=remote,
    )


def _facts(remote: bool) -> list[dict]:
    return query(
        "SELECT f.id, f.kind, f.content, f.subject, e.name AS subject_name "
        "FROM facts f LEFT JOIN entities e ON e.id = f.subject "
        "WHERE f.valid_to IS NULL ORDER BY f.kind, f.valid_from",
        remote=remote,
    )


def _places(remote: bool, last_day: int) -> dict[str, list[dict]]:
    rows = query(
        "SELECT id, name, summary, last_entry, reference_count FROM entities "
        "WHERE kind = 'place' ORDER BY COALESCE(last_entry, 0) DESC",
        remote=remote,
    )
    recent, stale = [], []
    for row in rows:
        seen = row.get("last_entry")
        if seen is None:
            stale.append(row)
        elif last_day - seen > STALE_AFTER_DAYS:
            stale.append(row)
        else:
            recent.append(row)
    return {"recent": recent[:8], "stale": stale[:6]}


def load_world(*, remote: bool = True) -> dict:
    """Everything the randomiser and the prompt need, in one shape."""
    summary = _summary(remote)
    last_day = summary["last_day"]
    threads = _threads(remote)

    for thread in threads:
        planned = thread.get("planned_entries")
        used = thread.get("reference_count") or 0
        idle = last_day - (thread.get("last_used_day") or thread["opened_day"])
        cooldown = thread.get("cooldown_days") or 0
        # Past its planned length, or quiet for several times its cooldown:
        # either way the next prompt should be told to close or abandon it.
        thread["due_for_closure"] = bool(
            (planned is not None and used >= planned) or (cooldown and idle > cooldown * 4)
        )
        thread["idle_days"] = idle

    return {
        **summary,
        "threads": threads,
        "threads_due_for_closure": [t for t in threads if t["due_for_closure"]],
        "facts": _facts(remote),
        "location": _location(remote),
        "places": _places(remote, last_day),
    }


# --- rendering -----------------------------------------------------------
# The prompt is Polish, so these blocks are too. Keys stay English everywhere
# else; this is the one place the two meet.


def render_state(world: dict) -> str:
    lines: list[str] = []

    rules = [f for f in world["facts"] if f.get("kind") == "world_rule"]
    if rules:
        lines.append("### Reguły światów")
        for fact in rules:
            where = fact.get("subject_name") or fact.get("subject") or "?"
            lines.append(f"- `{fact['id']}` **{where}**: {fact['content']}")
        lines.append("")

    general = [f for f in world["facts"] if f.get("kind") != "world_rule"]
    if general:
        lines.append("### Co obowiązuje")
        # Ids are shown because closing a fact needs one. Without them the
        # extractor has no way to name an existing fact and invents an id
        # instead — the UPDATE then matches nothing, in silence, and the world
        # goes on believing something the entry just ended.
        for fact in general:
            who = fact.get("subject_name") or fact.get("subject")
            lines.append(f"- `{fact['id']}` {'**' + who + '** — ' if who else ''}{fact['content']}")
        lines.append("")

    if world["threads"]:
        lines.append("### Sprawy w toku")
        for thread in world["threads"]:
            policy = POLICY_LABEL.get(thread["reference_policy"], thread["reference_policy"])
            pressure = " — **domknij albo porzuć wkrótce**" if thread["due_for_closure"] else ""
            lines.append(
                f"- `{thread['id']}` [{policy}] od dnia {thread['opened_day']}"
                f", użyta {thread['reference_count']}×{pressure}"
            )
            if thread.get("summary"):
                lines.append(f"  {thread['summary']}")
        lines.append("")
    else:
        lines.append("### Sprawy w toku\n\nŻadna. Jest miejsce, żeby coś zacząć.\n")

    return "\n".join(lines).strip()


def render_location(world: dict) -> str:
    chain = world["location"]
    if not chain:
        return "Nigdzie jeszcze — to pierwszy wpis."
    here = chain[0]
    where = " ← ".join(part["name"] for part in chain)
    summary = f"\n{here['summary']}" if here.get("summary") else ""
    return f"**{here['name']}** (`{here['id']}`)\n{where}{summary}"


def render_places(world: dict) -> str:
    stale = world["places"]["stale"]
    if not stale:
        return "Brak — wszędzie był niedawno."
    return "\n".join(
        f"- `{p['id']}` {p['name']}"
        + (f" — ostatnio w dniu {p['last_entry']}" if p.get("last_entry") else " — nigdy")
        for p in stale
    )
