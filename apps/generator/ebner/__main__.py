"""Command line entry point.

    python -m ebner apply            # replay every state file, in order
    python -m ebner apply 0003.json  # apply one
    python -m ebner status           # what the world currently holds
    python -m ebner plan [--seed N]  # draw an entry's parameters and show the
                                     # context it would be written against
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
    return 0


COMMANDS = {"apply": cmd_apply, "status": cmd_status, "plan": cmd_plan}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
