"""Retrieval: what the writer is shown from earlier entries.

The flow is: build a query from where Ebner is and what is running, embed it,
ask Vectorize for neighbours, then filter in D1. Vectorize decides what is
*similar*; D1 decides what is *allowed*, and the two are not the same question.

One rule is absolute: a fragment belonging to a `do_not_touch` thread never
reaches the prompt. Not labelled, not de-ranked — excluded.
"""

from __future__ import annotations

from . import vectorize
from .ai import embed
from .config import load
from .context import POLICY_LABEL
from .d1 import query as d1_query
from .d1 import sql_str


def build_query(world: dict, params: dict) -> str:
    """What to look for: where he is, what is running, what today is about."""
    parts: list[str] = []
    if world["location"]:
        parts.append(world["location"][0]["name"])
    for thread in world["threads"][:3]:
        if thread.get("summary"):
            parts.append(thread["summary"])
    if params.get("hint"):
        parts.append(params["hint"])
    parts.append(params.get("kind_label", ""))
    return " ".join(p for p in parts if p)


def recall(world: dict, params: dict, *, remote: bool = True) -> list[dict]:
    cfg = load("cloudflare.yaml")["retrieval"]

    text = build_query(world, params)
    vector = embed([text])[0]
    matches = vectorize.query(vector, cfg["top_k"])
    if not matches:
        return []

    scores = {m["id"]: m.get("score", 0.0) for m in matches}
    ids = ", ".join(sql_str(i) for i in scores)

    # Everything the filter needs, in one read. A fragment with no thread at
    # all — a world description from the seed — is always allowed, hence the
    # left join and the COALESCE.
    rows = d1_query(
        "SELECT f.id, f.kind, f.content, f.entry_day, "
        "COALESCE(MIN(CASE t.reference_policy "
        "WHEN 'do_not_touch' THEN 0 WHEN 'mention' THEN 1 "
        "WHEN 'may_return' THEN 2 ELSE 3 END), 3) AS policy_rank, "
        "MAX(COALESCE(t.last_used_day, -1)) AS thread_last_used, "
        "MAX(COALESCE(t.cooldown_days, 0)) AS cooldown, "
        # Readers' verdicts on the entry this fragment came from. Only the
        # negative count is read: see the penalty below.
        "(SELECT COUNT(*) FROM opinions o "
        " WHERE o.entry_day = f.entry_day AND o.verdict = 'nok') AS nok "
        f"FROM fragments f "
        "LEFT JOIN fragment_threads ft ON ft.fragment_id = f.id "
        "LEFT JOIN threads t ON t.id = ft.thread_id "
        f"WHERE f.id IN ({ids}) GROUP BY f.id",
        remote=remote,
    )

    rank_to_policy = {0: "do_not_touch", 1: "mention", 2: "may_return", 3: "develop"}
    last_day = world["last_day"]
    kept: list[dict] = []

    for row in rows:
        rank = int(row["policy_rank"])
        if rank == 0:
            # do_not_touch: excluded outright, never shown and never labelled.
            continue

        score = scores.get(row["id"], 0.0)
        # A thread used very recently is pushed down rather than dropped: the
        # spec asks for recently referenced threads to be penalised, and
        # dropping them would make a continuation impossible.
        last_used = int(row["thread_last_used"])
        cooldown = int(row["cooldown"])
        if last_used >= 0 and cooldown and (last_day - last_used) < cooldown:
            score *= 0.5

        # A scene from an entry readers said did not work is pushed down, and
        # a scene from one they liked is not pushed up. The asymmetry is the
        # whole design: a signal that rewards creates a gradient to climb, and
        # this diary has already shown what it does with one — it found an
        # ending that worked and used it in eight entries of thirteen with no
        # reward at all. Penalising a miss steers away from one scene;
        # rewarding a hit steers towards a formula.
        #
        # Bounded, never zero: an entry can be disliked and still be the only
        # place a thread was opened.
        nok = int(row["nok"] or 0)
        if nok:
            score *= max(1.0 - 0.2 * nok, 0.4)

        kept.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "content": row["content"],
                "entry_day": row["entry_day"],
                "policy": rank_to_policy[rank],
                "score": score,
            }
        )

    kept.sort(key=lambda r: r["score"], reverse=True)
    return kept[: cfg["keep"]]


def render(fragments: list[dict]) -> str:
    if not fragments:
        return "Brak — nie ma jeszcze do czego wracać."
    lines = []
    for fragment in fragments:
        label = POLICY_LABEL.get(fragment["policy"], fragment["policy"])
        where = f"dzień {fragment['entry_day']}" if fragment["entry_day"] else "kanon"
        lines.append(f"- [{label}] ({where}) {fragment['content']}")
    return "\n".join(lines)
