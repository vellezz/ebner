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

# After this many in-world days untouched, a thread is due for closure whatever
# else is recorded about it. Without this a thread with no planned length and
# no cooldown can never come due — both terms of the test need a number to work
# with, and the extractor supplies neither for most threads. One sat active and
# untouched for twelve days with nothing ever raising it.
IDLE_CEILING_DAYS = 20


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
    """Every fact still in force.

    All of them, deliberately: the pipeline needs the complete set of ids to
    resolve what extraction refers to. Which of them the *prompt* sees is a
    separate decision, made in `select_facts`.
    """
    return query(
        "SELECT f.id, f.kind, f.content, f.subject, f.valid_from, "
        "e.name AS subject_name, e.reference_count AS subject_refs "
        "FROM facts f LEFT JOIN entities e ON e.id = f.subject "
        "WHERE f.valid_to IS NULL ORDER BY f.kind, f.valid_from",
        remote=remote,
    )


def _opinions(remote: bool) -> list[dict]:
    """How recent entries landed with readers, by the day they belong to.

    Counts only: the buttons carry no text, and that is deliberate, because
    this reaches the prompt that writes the canon and anything a stranger
    could type would be untrusted input arriving at a model.
    """
    return query(
        "SELECT e.day, e.kind, "
        "SUM(CASE WHEN o.verdict = 'ok' THEN 1 ELSE 0 END) AS ok, "
        "SUM(CASE WHEN o.verdict = 'nok' THEN 1 ELSE 0 END) AS nok "
        "FROM opinions o JOIN entries e ON e.day = o.entry_day "
        "GROUP BY e.day ORDER BY e.day DESC LIMIT 12",
        remote=remote,
    )


def _previous(remote: bool) -> list[dict]:
    """The last few entries, most recent first, the newest one in full.

    Retrieval returns fragments, which are snippets chosen for similarity. They
    are not a substitute for having read yesterday: an entry asked to continue
    something it has never seen will invent the part it is missing.

    Eight rather than four, because four was not enough to see a habit. Both
    prompts forbid repeating an ending and eight of the first thirteen entries
    closed on a bill or a debt anyway — four of them on the same sentence about
    paying next week. A writer shown one previous ending cannot know that.
    """
    return query(
        "SELECT day, title, kind, body FROM entries ORDER BY day DESC LIMIT 8",
        remote=remote,
    )


def _closing_line(body: str) -> str:
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _entities(remote: bool) -> list[dict]:
    return query(
        "SELECT id, kind, name, parent, last_entry FROM entities ORDER BY kind, id",
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
        # Past its planned length, quiet for several times its cooldown, or
        # simply gone cold: any of the three and the next prompt should be told
        # to close or abandon it. The third is not a refinement of the other
        # two — it is the only one that fires for a thread that records neither
        # a planned length nor a cooldown, which is most of them.
        thread["due_for_closure"] = bool(
            (planned is not None and used >= planned)
            or (cooldown and idle > cooldown * 4)
            or idle > IDLE_CEILING_DAYS
        )
        thread["idle_days"] = idle

    return {
        **summary,
        "threads": threads,
        "threads_due_for_closure": [t for t in threads if t["due_for_closure"]],
        "facts": _facts(remote),
        "entities": _entities(remote),
        "previous": _previous(remote),
        "opinions": _opinions(remote),
        "location": _location(remote),
        "places": _places(remote, last_day),
    }


# --- rendering -----------------------------------------------------------
# The prompt is Polish, so these blocks are too. Keys stay English everywhere
# else; this is the one place the two meet.


# How recently a fact must have been opened, or its subject touched, to still
# belong in front of the writer.
FACT_WINDOW_DAYS = 12
# A backstop, not a budget. The window above is what bounds growth; this only
# stops a pathological world from filling the prompt on its own. Set high
# enough that it does nothing at the sizes seen so far — the first value tried
# was 30, which cut the voting rule out from under a thread that was still
# running, and a fact removed from the prompt is a fact the entry can
# contradict.
FACT_LIMIT = 60


def select_facts(world: dict) -> tuple[list[dict], int]:
    """The facts the prompt should carry, and how many were left out.

    Every fact used to go in. That is fine at ten entries and ruinous at a
    thousand: they accumulate at about four an entry against half a closure,
    so the prompt grows without bound and the bill with it.

    What survives:

      * **the seed.** Facts from `0000.json` are the world's premise — who
        Ebner is, what Hanna is, what Holdmark Serwis is, where the debt on
        Varnu comes from. They are six rows and they never expire, and the
        first version of this function dropped every one of them, which would
        have quietly deleted the whole backstory from the writer's view.
      * facts about where he is, and about everything containing it;
      * facts about anything the diary has touched recently, by the entity's
        own `last_entry`;
      * facts opened recently enough to still be news.

    A fact about a moon he left forty days ago goes, and retrieval brings that
    moon back when he returns to it. `reference_count` looked like the way to
    find the standing cast and is not: it counts appearances as an entry's
    location, so Ebner himself scores zero.
    """
    facts = world.get("facts") or []
    chain = {row["id"] for row in world.get("location") or []}
    last_day = world.get("last_day") or 0
    recent_subjects = {
        entity["id"]
        for entity in world.get("entities") or []
        if entity.get("last_entry") is not None
        and last_day - entity["last_entry"] <= FACT_WINDOW_DAYS
    }

    def keep(fact: dict) -> bool:
        # valid_from 0 with no source entry is the seed's signature.
        if (fact.get("valid_from") or 0) <= 0:
            return True
        if fact.get("subject") in chain or fact.get("subject") in recent_subjects:
            return True
        return last_day - (fact.get("valid_from") or 0) <= FACT_WINDOW_DAYS

    kept = [fact for fact in facts if keep(fact)]
    if len(kept) > FACT_LIMIT:
        # Recency alone is the wrong order to cut in: it drops the rule of the
        # place he is standing on before it drops last week's invoice. Rank by
        # what the entry can touch, and only break ties by age.
        def rank(fact: dict) -> tuple[int, int]:
            if (fact.get("valid_from") or 0) <= 0:
                tier = 0  # the premise
            elif fact.get("subject") in chain:
                tier = 1  # where he is
            elif fact.get("subject") in recent_subjects:
                tier = 2  # who and what is currently in play
            else:
                tier = 3
            return (tier, -(fact.get("valid_from") or 0))

        kept = sorted(kept, key=rank)[:FACT_LIMIT]
        kept.sort(key=lambda f: (f.get("kind") or "", f.get("valid_from") or 0))

    return kept, len(facts) - len(kept)


def render_state(world: dict) -> str:
    lines: list[str] = []
    selected, omitted = select_facts(world)
    world = {**world, "facts": selected}

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

    if omitted:
        # Said out loud so the writer knows the world is larger than the page,
        # rather than concluding these places have no history.
        lines.append(
            f"_Pominięto {omitted} faktów o miejscach i sprawach, przy których"
            " Ebnera teraz nie ma. Świat ich nie zapomniał._\n"
        )

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


KIND_LABEL = {
    "person": "Postacie",
    "place": "Miejsca",
    "organisation": "Organizacje",
    "ship": "Statki",
}


def render_entities(world: dict) -> str:
    """Everything that already has an identity.

    Extraction needs this or it cannot obey its own instruction not to
    re-introduce an entity: it would have to guess which ids exist, and
    guessing wrong reads as a brand new place that happens to share a name.
    """
    entities = world.get("entities") or []
    if not entities:
        return "Brak — świat jest pusty."
    lines: list[str] = []
    for kind in ("person", "ship", "organisation", "place"):
        group = [e for e in entities if e["kind"] == kind]
        if not group:
            continue
        lines.append(f"**{KIND_LABEL[kind]}**")
        for entity in group:
            inside = f" (w `{entity['parent']}`)" if entity.get("parent") else ""
            lines.append(f"- `{entity['id']}` {entity['name']}{inside}")
        lines.append("")
    return "\n".join(lines).strip()


def render_location(world: dict) -> str:
    chain = world["location"]
    if not chain:
        return "Nigdzie jeszcze — to pierwszy wpis."
    here = chain[0]
    where = " ← ".join(part["name"] for part in chain)
    summary = f"\n{here['summary']}" if here.get("summary") else ""
    return f"**{here['name']}** (`{here['id']}`)\n{where}{summary}"


def render_previous(world: dict) -> str:
    entries = world.get("previous") or []
    if not entries:
        return "Brak — to pierwszy wpis."

    latest, earlier = entries[0], entries[1:]
    lines = [
        f"### Poprzedni wpis — dzień {latest['day']}: {latest['title']}",
        "",
        latest["body"].strip(),
        "",
    ]
    if earlier:
        lines.append("### Wcześniej — i czym się skończyło")
        lines.append("")
        lines.append(
            "Ostatnie zdania poprzednich wpisów. **Nie kończ dzisiejszego tak samo"
            " ani podobnie.** Rachunek, faktura, dług i kwota z Varnu były już"
            " zamknięciem wielu wpisów — jeśli widzisz je poniżej, dziś potrzebny"
            " jest inny rodzaj końcówki."
        )
        lines.append("")
        for entry in earlier:
            lines.append(f"- dzień {entry['day']}: {entry['title']} ({entry['kind']})")
            closing = _closing_line(entry.get("body", ""))
            if closing:
                lines.append(f"  koniec: {closing}")
    return "\n".join(lines).strip()


KIND_LABEL_PL = {
    "travel": "podróż",
    "new_job": "nowe zlecenie",
    "continuation": "ciąg dalszy",
    "resolution": "rozstrzygnięcie",
    "adventure": "przygoda",
    "quiet": "cisza",
    "note": "notatka",
    "documents": "dokumenty",
    "stopover": "postój",
}


def render_opinions(world: dict) -> str:
    """What readers made of recent entries — as information, not as a target.

    The framing in the prompt matters more than the numbers. A signal like
    this is read by something very good at finding what scores well, and this
    diary has already demonstrated the failure mode without any signal at all:
    it found an ending that worked and closed eight entries of thirteen with
    it. So the block says what did not land and says explicitly that a quiet
    entry scoring low is expected.
    """
    rows = world.get("opinions") or []
    if not rows:
        return "Brak ocen — jeszcze nikt nie głosował."

    lines = [
        "Oceny czytelników. **To nie jest cel.** Niska ocena mówi, że coś nie",
        "zagrało, i tyle — nie mówi, co powtórzyć. Wpis typu `cisza` z niską",
        "oceną jest oczekiwany: ciche dni są tkanką tego dziennika i to one",
        "sprawiają, że przygody trafiają. Nie pisz pod ocenę.",
        "",
    ]
    for row in rows:
        kind = KIND_LABEL_PL.get(row.get("kind"), row.get("kind") or "?")
        lines.append(
            f"- dzień {row['day']} ({kind}): {row.get('ok') or 0} na tak,"
            f" {row.get('nok') or 0} na nie"
        )
    return "\n".join(lines)


def render_places(world: dict) -> str:
    stale = world["places"]["stale"]
    if not stale:
        return "Brak — wszędzie był niedawno."
    return "\n".join(
        f"- `{p['id']}` {p['name']}"
        + (f" — ostatnio w dniu {p['last_entry']}" if p.get("last_entry") else " — nigdy")
        for p in stale
    )
