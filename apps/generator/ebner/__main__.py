"""Command line entry point.

    python -m ebner apply            # replay every state file, in order
    python -m ebner apply 0003.json  # apply one
    python -m ebner status           # what the world currently holds
    python -m ebner plan [--seed N]  # draw an entry's parameters and show the
                                     # context it would be written against
    python -m ebner experiment --seed N --effort high,medium
                                     # write the same entry under each setting
                                     # and compare; saves nothing
    python -m ebner rebuild          # clear the projection and replay every
                                     # state file; leaves subscriptions alone
"""

from __future__ import annotations

import sys
from pathlib import Path

from .apply import STATE_DIR, apply_state_file, state_files
from .config import rhythm
from .context import load_world, render_location, render_places, render_state
from .d1 import query
from .rhythm import plan_entry


def cmd_apply(args: list[str]) -> int:
    local = "--local" in args
    names = [a for a in args if not a.startswith("-")]
    paths = [STATE_DIR / n for n in names] if names else state_files()

    for path in paths:
        if not path.exists():
            print(f"  missing: {path.name}", file=sys.stderr)
            return 1
        result = apply_state_file(path, remote=not local)
        print(f"  applied {result['file']}: {result['statements']} statements")
    return 0


def cmd_status(args: list[str]) -> int:
    local = "--local" in args
    # Scalar subqueries rather than UNION ALL: D1 caps the number of terms in a
    # compound SELECT well below what SQLite allows, and seven is already over.
    rows = query(
        "SELECT "
        "(SELECT COUNT(*) FROM entities) AS entities, "
        "(SELECT COUNT(*) FROM entries) AS entries, "
        "(SELECT COUNT(*) FROM travel) AS travel, "
        "(SELECT COUNT(*) FROM threads WHERE status = 'active') AS threads_active, "
        "(SELECT COUNT(*) FROM threads) AS threads_total, "
        "(SELECT COUNT(*) FROM facts WHERE valid_to IS NULL) AS facts_valid, "
        "(SELECT COUNT(*) FROM facts WHERE valid_to IS NOT NULL) AS facts_closed, "
        "(SELECT COUNT(*) FROM fragments) AS fragments, "
        "(SELECT COALESCE(MAX(day), 0) FROM entries) AS last_day",
        remote=not local,
    )
    for key, value in rows[0].items():
        print(f"  {key:<16} {value}")
    return 0


def cmd_index(args: list[str]) -> int:
    """Embed fragments and put them in Vectorize.

    Two real uses, so two shapes: one day's fragments after an entry lands,
    or everything when the index is being rebuilt from scratch. No tracking
    column — the caller knows which of the two it wants.
    """
    from .ai import embed
    from . import vectorize

    local = "--local" in args
    days = [a for a in args if not a.startswith("-")]

    if "--all" in args:
        where = ""
    elif days:
        where = f"WHERE entry_day IN ({', '.join(str(int(d)) for d in days)})"
    else:
        print("  usage: index --all | index <day> [<day>...]", file=sys.stderr)
        return 2

    rows = query(f"SELECT id, content FROM fragments {where} ORDER BY id", remote=not local)
    if not rows:
        print("  nothing to index")
        return 0

    total = 0
    # Batched because a single request carrying every fragment would grow
    # without bound as the diary does.
    for start in range(0, len(rows), 50):
        batch = rows[start : start + 50]
        vectors = embed([r["content"] for r in batch])
        total += vectorize.upsert(
            [(r["id"], v) for r, v in zip(batch, vectors)]
        )
        print(f"  indexed {total}/{len(rows)}")
    return 0


def cmd_plan(args: list[str]) -> int:
    local = "--local" in args
    seed = None
    if "--seed" in args:
        seed = int(args[args.index("--seed") + 1])

    world = load_world(remote=not local)
    params = plan_entry(rhythm(), world, seed=seed)

    print("=== PARAMETRY ===")
    print(f"  dzień            {params['day']} (skok +{params['day_step']})")
    print(f"  rodzaj           {params['kind']} — {params['kind_label']}")
    print(f"  długość          {params['length']} {params['length_words']} słów")
    print(f"  nowy świat       {'tak' if params['new_destination'] else 'nie'}")
    print(f"  podpowiedź       {params['hint'] or '—'}")
    print()
    print("=== GDZIE JEST ===")
    print(render_location(world))
    print()
    print("=== STAN ŚWIATA ===")
    print(render_state(world))
    print()
    print("=== DAWNO NIE BYŁ ===")
    print(render_places(world))

    if "--no-recall" not in args:
        from .retrieval import recall, render
        print()
        print("=== Z WCZEŚNIEJSZYCH WPISÓW ===")
        print(render(recall(world, params, remote=not local)))
    return 0


def cmd_generate(args: list[str]) -> int:
    from .pipeline import PipelineError, generate, save

    local = "--local" in args
    dry = "--dry-run" in args
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else None

    try:
        result = generate(seed=seed, remote=not local, dry_run=dry)
    except PipelineError as error:
        from .llm import cost_report

        # A failed run still spent money. Report it rather than let it vanish
        # with the traceback.
        print(f"  {error}", file=sys.stderr)
        print("\n=== ZUŻYCIE (przebieg nieudany) ===", file=sys.stderr)
        print(cost_report(), file=sys.stderr)
        return 1

    if dry:
        print(result["prompt"])
        return 0

    from .llm import cost_report

    saved = save(result)
    print("\n=== ZUŻYCIE ===")
    print(cost_report())
    print()
    print(f"  {saved['title']}")
    print(f"  {saved['entry'].relative_to(saved['entry'].parents[2])}")
    print(f"  {saved['state'].relative_to(saved['state'].parents[2])}")
    return 0


def cmd_rebuild(args: list[str]) -> int:
    """Rebuild the whole projection from content/state/.

        python -m ebner rebuild

    Empties the world tables and replays every state file in filename order.
    This is what makes D1 a projection rather than a second source of truth,
    and it is the second half of unpublishing: delete an entry's two files and
    replay, and everything it introduced is gone.

    Subscriptions are not touched. They are the one thing in that database
    which nothing in the repository could put back.

    Self-checking by construction: a later entry that depends on something no
    longer there fails its guards during replay and names itself.
    """
    from .apply import apply_state_file, reset_world, state_files

    local = "--local" in args
    remote = not local

    files = state_files()
    print(f"  clearing the projection ({len(files)} state files to replay)")
    reset_world(remote=remote)

    total = 0
    for path in files:
        result = apply_state_file(path, remote=remote)
        total += result["statements"]
        print(f"    {result['file']}: {result['statements']} statements")
    print(f"  replayed {len(files)} files, {total} statements")

    print("  re-embedding fragments")
    return cmd_index(["--all"] + (["--local"] if local else []))


def cmd_experiment(args: list[str]) -> int:
    """Write the same entry under different settings and compare the cost.

        python -m ebner experiment --seed 7 --effort high,medium

    Nothing is saved. The same seed draws the same parameters and the same
    world, so the only difference between the variants is the setting under
    test — which is what makes the comparison worth anything.

    This exists for one question. `effort: high` on the writing step is about a
    third of the bill, and whether it buys anything a reader would notice has
    been an opinion up to now.
    """
    from . import llm
    from .pipeline import PipelineError, generate

    local = "--local" in args
    seed = int(args[args.index("--seed") + 1]) if "--seed" in args else 1
    efforts = (
        args[args.index("--effort") + 1].split(",") if "--effort" in args else ["high", "medium"]
    )

    # Forcing the band matters more than it looks. The first comparison drew a
    # note, which is the one length where thinking barely happens, and it
    # answered nothing — a difference of two cents on the question of whether
    # a third of the bill is earned.
    if "--length" in args:
        band = args[args.index("--length") + 1]
        cfg = rhythm()
        wanted = [b for b in cfg["length"] if b["id"] == band]
        if not wanted:
            print(f"  no such length band: {band}", file=sys.stderr)
            return 2
        # The config is cached and shared, so this holds for the process. That
        # is the intent: both variants must be drawn the same way.
        cfg["length"] = wanted
        print(f"  długość wymuszona: {band} {wanted[0]['words']} słów")

    results = []
    for effort in efforts:
        llm.reset_usage()
        llm.override("write", effort=effort.strip())
        print(f"\n{'=' * 70}\n=== effort: {effort.strip()} (seed {seed})\n{'=' * 70}\n")
        try:
            result = generate(seed=seed, remote=not local)
        except PipelineError as error:
            print(f"  {error}", file=sys.stderr)
            print(llm.cost_report(), file=sys.stderr)
            return 1
        print(result["entry"])
        print(f"\n--- zużycie ({effort.strip()}) ---")
        print(llm.cost_report())
        body = result["entry"].split("---", 2)[-1]
        results.append((effort.strip(), len(body), llm.cost_report().splitlines()[-1]))

    print(f"\n{'=' * 70}\n=== porównanie\n{'=' * 70}")
    for effort, chars, total in results:
        print(f"  {effort:<8} znaków {chars:<7,} {total.strip()}")
    print("\n  Oba teksty są wyżej. Różnica w cenie jest zmierzona; różnica w")
    print("  jakości jest do przeczytania i to jest jedyna część, której nie")
    print("  da się zautomatyzować.")
    return 0


def cmd_extract(args: list[str]) -> int:
    from .pipeline import PipelineError, extract_for

    local = "--local" in args
    days = [int(a) for a in args if not a.startswith("-")]
    if not days:
        print("  usage: extract <day> [<day>...]", file=sys.stderr)
        return 2
    try:
        for day in days:
            result = extract_for(day, remote=not local)
            print(f"  rewrote {result['state'].name}")
    except PipelineError as error:
        print(f"  {error}", file=sys.stderr)
        return 1
    return 0


def cmd_notify(args: list[str]) -> int:
    from .push import PushError, notify, wait_for_site

    local = "--local" in args
    expect = int(args[args.index("--expect-day") + 1]) if "--expect-day" in args else None

    if expect is not None and not wait_for_site(expect):
        # Not an error: the entry is published and the site will catch up. A
        # notification announcing the wrong day would be worse than none.
        print(f"  site has not published day {expect} yet; skipping notification")
        return 0

    try:
        result = notify(remote=not local)
    except PushError as error:
        print(f"  {error}", file=sys.stderr)
        return 1

    print(
        f"  wysłano {result['sent']}/{result['total']}"
        f" (wygasłe: {result['gone']}, błędy: {result['failed']})"
    )
    return 0


COMMANDS = {
    "apply": cmd_apply,
    "experiment": cmd_experiment,
    "rebuild": cmd_rebuild,
    "notify": cmd_notify,
    "extract": cmd_extract,
    "status": cmd_status,
    "plan": cmd_plan,
    "index": cmd_index,
    "generate": cmd_generate,
}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
