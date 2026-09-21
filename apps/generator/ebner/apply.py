"""Apply a state file to D1.

Idempotent by construction: re-running the same file changes nothing, and
replaying every file from 0000 upward rebuilds the database from scratch. That
property is what makes unpublishing an entry a complete operation rather than a
partial one, so it is not optional.

Order matters because of foreign keys: entities, then the entry row, then
everything that points at either.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .d1 import REPO, execute, sql_str

ENTRIES_DIR = REPO / "content" / "entries"
STATE_DIR = REPO / "content" / "state"

FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n(.*)\Z", re.DOTALL)


def parse_entry(path: Path) -> tuple[dict, str]:
    """Split an entry file into frontmatter and body."""
    raw = path.read_text(encoding="utf-8").lstrip("﻿")
    match = FRONTMATTER.match(raw)
    if not match:
        raise ValueError(f"{path.name}: no frontmatter block")

    data: dict = {}
    for line in match.group(1).splitlines():
        pair = re.match(r"^(\w+):\s*(.*)$", line)
        if not pair:
            continue
        key, value = pair.group(1), pair.group(2).strip()
        if value == "null":
            data[key] = None
        elif value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            data[key] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
        elif re.fullmatch(r"-?\d+", value):
            data[key] = int(value)
        else:
            data[key] = value.strip("\"'")
    return data, match.group(2).strip()


def _statements(state: dict, entry: dict | None, body: str | None) -> list[str]:
    day = state["day"]
    out: list[str] = []
    is_seed = day == 0
    entry_day = None if is_seed else day

    # --- entities --------------------------------------------------------
    for e in state.get("entities", []):
        out.append(
            "INSERT INTO entities (id, kind, name, parent, summary, first_entry) "
            f"VALUES ({sql_str(e['id'])}, {sql_str(e['kind'])}, {sql_str(e['name'])}, "
            f"{sql_str(e.get('parent'))}, {sql_str(e.get('summary'))}, {sql_str(entry_day)}) "
            "ON CONFLICT(id) DO UPDATE SET "
            "kind = excluded.kind, name = excluded.name, "
            "parent = excluded.parent, summary = excluded.summary"
        )

    # --- the entry row ----------------------------------------------------
    # Derived from the Markdown file, never from the state file: one fact, one
    # home. The seed has no entry beside it, and neither do thread reviews.
    if entry is not None:
        out.append(
            "INSERT INTO entries (day, title, location, kind, body, published_at) "
            f"VALUES ({sql_str(entry['day'])}, {sql_str(entry['title'])}, "
            f"{sql_str(entry['location'])}, {sql_str(entry['kind'])}, {sql_str(body)}, "
            "datetime('now')) "
            "ON CONFLICT(day) DO UPDATE SET "
            "title = excluded.title, location = excluded.location, "
            "kind = excluded.kind, body = excluded.body"
        )

    # --- threads ----------------------------------------------------------
    for t in state.get("threads", []):
        if t["op"] == "open":
            out.append(
                "INSERT INTO threads (id, type, status, reference_policy, opened_day, "
                "planned_entries, cooldown_days, summary) VALUES ("
                f"{sql_str(t['id'])}, {sql_str(t.get('type', 'medium'))}, "
                f"{sql_str(t.get('status', 'active'))}, "
                f"{sql_str(t.get('reference_policy', 'develop'))}, {sql_str(day)}, "
                f"{sql_str(t.get('planned_entries'))}, {sql_str(t.get('cooldown_days', 0))}, "
                f"{sql_str(t.get('summary'))}) "
                "ON CONFLICT(id) DO UPDATE SET "
                "type = excluded.type, status = excluded.status, "
                "reference_policy = excluded.reference_policy, "
                "planned_entries = excluded.planned_entries, "
                "cooldown_days = excluded.cooldown_days, summary = excluded.summary"
            )
        else:
            sets = []
            for column in ("status", "reference_policy", "summary", "closure",
                           "planned_entries", "cooldown_days"):
                if column in t:
                    sets.append(f"{column} = {sql_str(t[column])}")
            if t["op"] == "close":
                sets.append(f"closed_day = {sql_str(day)}")
                if "status" not in t:
                    sets.append("status = 'closed'")
            if sets:
                out.append(
                    f"UPDATE threads SET {', '.join(sets)} WHERE id = {sql_str(t['id'])}"
                )

    if entry is not None:
        out.append(f"DELETE FROM entry_threads WHERE entry_day = {sql_str(day)}")
        for thread_id in entry.get("threads") or []:
            out.append(
                "INSERT OR IGNORE INTO entry_threads (entry_day, thread_id) "
                f"VALUES ({sql_str(day)}, {sql_str(thread_id)})"
            )

    # --- travel -----------------------------------------------------------
    # Replaced wholesale so a corrected state file cannot leave orphan hops.
    if state.get("travel") is not None and entry_day is not None:
        out.append(f"DELETE FROM travel WHERE entry_day = {sql_str(day)}")
        for hop in sorted(state.get("travel", []), key=lambda h: h["seq"]):
            out.append(
                "INSERT INTO travel (entry_day, seq, from_entity, to_entity) VALUES ("
                f"{sql_str(day)}, {sql_str(hop['seq'])}, "
                f"{sql_str(hop.get('from'))}, {sql_str(hop['to'])})"
            )

    # --- facts ------------------------------------------------------------
    for fact in state.get("facts_opened", []):
        out.append(
            "INSERT INTO facts (id, kind, content, subject, valid_from, source_entry) "
            f"VALUES ({sql_str(fact['id'])}, {sql_str(fact.get('kind', 'general'))}, "
            f"{sql_str(fact['content'])}, {sql_str(fact.get('subject'))}, "
            f"{sql_str(fact.get('valid_from', day))}, {sql_str(entry_day)}) "
            "ON CONFLICT(id) DO UPDATE SET "
            "kind = excluded.kind, content = excluded.content, "
            "subject = excluded.subject, valid_from = excluded.valid_from"
        )
    for fact in state.get("facts_closed", []):
        out.append(
            f"UPDATE facts SET valid_to = {sql_str(fact.get('valid_to', day))} "
            f"WHERE id = {sql_str(fact['id'])}"
        )

    # --- fragments --------------------------------------------------------
    if entry_day is not None:
        out.append(f"DELETE FROM fragments WHERE entry_day = {sql_str(day)}")
    for fragment in state.get("fragments", []):
        out.append(
            "INSERT INTO fragments (id, entry_day, kind, content) VALUES ("
            f"{sql_str(fragment['id'])}, {sql_str(entry_day)}, "
            f"{sql_str(fragment['kind'])}, {sql_str(fragment['content'])}) "
            "ON CONFLICT(id) DO UPDATE SET "
            "entry_day = excluded.entry_day, kind = excluded.kind, content = excluded.content"
        )
        out.append(f"DELETE FROM fragment_threads WHERE fragment_id = {sql_str(fragment['id'])}")
        for thread_id in fragment.get("threads") or []:
            out.append(
                "INSERT OR IGNORE INTO fragment_threads (fragment_id, thread_id) "
                f"VALUES ({sql_str(fragment['id'])}, {sql_str(thread_id)})"
            )

    # --- derived counters -------------------------------------------------
    # Recomputed rather than incremented, so replaying a file twice cannot
    # inflate them. Cheap at this scale and correct by construction.
    out.append(
        "UPDATE entities SET last_entry = (SELECT MAX(d) FROM ("
        "SELECT day AS d FROM entries WHERE location = entities.id "
        "UNION ALL SELECT entry_day FROM travel WHERE to_entity = entities.id "
        "UNION ALL SELECT valid_from FROM facts WHERE subject = entities.id)), "
        "reference_count = ("
        "SELECT COUNT(*) FROM entries WHERE location = entities.id) + ("
        "SELECT COUNT(*) FROM travel WHERE to_entity = entities.id)"
    )
    # Being somewhere means being inside everything that contains it. A system
    # is never an entry's `location` — one is at a dock within it — so without
    # this a place Ebner lives in reads as never visited. Repeated because the
    # containment chain is a few levels deep: station, planet, system.
    for _ in range(4):
        out.append(
            "UPDATE entities SET last_entry = ("
            "SELECT MAX(c.last_entry) FROM entities c WHERE c.parent = entities.id) "
            "WHERE (SELECT MAX(c.last_entry) FROM entities c WHERE c.parent = entities.id) "
            "> COALESCE(entities.last_entry, -1)"
        )

    out.append(
        "UPDATE threads SET "
        "last_used_day = (SELECT MAX(entry_day) FROM entry_threads WHERE thread_id = threads.id), "
        "reference_count = (SELECT COUNT(*) FROM entry_threads WHERE thread_id = threads.id)"
    )
    return out


def apply_state_file(path: Path, *, remote: bool = True) -> dict:
    """Apply one state file, with the entry beside it when there is one."""
    state = json.loads(path.read_text(encoding="utf-8").lstrip("﻿"))
    day = state["day"]

    entry = body = None
    if day > 0 and re.fullmatch(r"\d+\.json", path.name):
        entry_path = ENTRIES_DIR / f"{day:04d}.md"
        if not entry_path.exists():
            raise FileNotFoundError(f"{path.name}: no entry file at {entry_path.name}")
        entry, body = parse_entry(entry_path)

    statements = _statements(state, entry, body)
    execute(statements, remote=remote)
    return {"file": path.name, "day": day, "statements": len(statements)}


def state_files() -> list[Path]:
    """Every state file in replay order — which is filename order."""
    return sorted(STATE_DIR.glob("*.json"))


# Everything D1 holds that is a projection of content/state/, in an order that
# clears children before parents.
#
# `push_subscriptions` is deliberately absent. It is the one table here that is
# not derived from anything in the repository — a browser endpoint someone gave
# us — so a rebuild that emptied it would silently unsubscribe every reader and
# no replay could put them back.
WORLD_TABLES = (
    "fragment_threads",
    "entry_threads",
    "fragments",
    "travel",
    "facts",
    "threads",
    "entries",
    "entities",
)


def reset_world(*, remote: bool = True) -> int:
    """Empty the projection, leaving anything that is not one alone."""
    statements = [f"DELETE FROM {table}" for table in WORLD_TABLES]
    execute(statements, remote=remote)
    return len(statements)
