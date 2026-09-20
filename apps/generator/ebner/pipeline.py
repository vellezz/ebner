"""The four steps that turn world state into an entry.

  write   Opus writes the prose, and only the prose.
  check   Sonnet judges it against recorded state. This is enforcement, not
          advice: publication is unattended, so a hard contradiction stops here.
  edit    Sonnet fixes language without touching content or register.
  state   Haiku turns the finished entry into the delta it made to the world.

Nothing is written to disk until every step has passed and the guards agree,
so a failed run leaves no half-entry behind.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .apply import ENTRIES_DIR, STATE_DIR, parse_entry
from .config import PROMPTS_DIR, prompt, rhythm
from .context import load_world, render_location, render_places, render_state
from .d1 import REPO
from .llm import complete
from .retrieval import recall
from .retrieval import render as render_recall
from .rhythm import plan_entry

GUARD = REPO / "apps" / "site" / "scripts" / "check-state.mjs"
SCHEMA_DIR = REPO / "content" / "schema"


class PipelineError(RuntimeError):
    pass


def fill(template: str, values: dict[str, object]) -> str:
    """Substitute {name} placeholders.

    Deliberately not str.format: the prompts contain literal braces in their
    worked examples, and a formatter would choke on them or, worse, silently
    consume one.
    """
    for key, value in values.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def _style_samples() -> str:
    directory = PROMPTS_DIR / "style_samples"
    if not directory.exists():
        return ""
    samples = sorted(directory.glob("*.md"))
    if not samples:
        return ""
    return "\n\n".join(s.read_text(encoding="utf-8").strip() for s in samples)


def _strip_fence(text: str) -> str:
    """Models like to wrap an answer in a code fence. Take what is inside."""
    fenced = re.search(r"```(?:\w+)?\r?\n(.*?)```", text, re.DOTALL)
    return fenced.group(1).strip() if fenced else text.strip()


def generate(*, seed: int | None = None, remote: bool = True, dry_run: bool = False) -> dict:
    world = load_world(remote=remote)
    params = plan_entry(rhythm(), world, seed=seed)
    fragments = recall(world, params, remote=remote)

    common = {
        "stan": render_state(world),
        "miejsce": render_location(world),
        "zapomniane": render_places(world),
        "rag": render_recall(fragments),
        "dzien": params["day"],
        "rodzaj": f"{params['kind']} — {params['kind_label']}",
        "dlugosc": f"{params['length_label']}, {params['length_words'][0]}–{params['length_words'][1]} słów",
        "podpowiedz": params["hint"] or "brak",
        "nowy_swiat": "tak — dziś wypada sięgnąć gdzieś nowej" if params["new_destination"] else "nie",
        "style_samples": _style_samples(),
    }

    if dry_run:
        return {"params": params, "prompt": fill(prompt("diary_pl.md"), common)}

    # --- 2. write --------------------------------------------------------
    entry_text = _strip_fence(complete("write", fill(prompt("diary_pl.md"), common), "Napisz wpis."))

    # --- 3. check --------------------------------------------------------
    checked = complete(
        "check",
        fill(prompt("check_pl.md"), {**common, "wpis": entry_text}),
        "Sprawdź wpis.",
    )
    verdict = checked.splitlines()[0].strip().lower() if checked else ""
    if verdict.startswith("werdykt: blokuj"):
        raise PipelineError("consistency check blocked the entry:\n" + checked)
    entry_text = _strip_fence("\n".join(checked.splitlines()[1:]).strip() or entry_text)

    # --- 4. edit ---------------------------------------------------------
    entry_text = _strip_fence(
        complete("edit", fill(prompt("edit_pl.md"), {"wpis": entry_text}), "Zredaguj wpis.")
    )

    # --- 5. extract state -------------------------------------------------
    # The prose is finished and paid for by this point. If extraction fails,
    # the entry goes into the error rather than evaporating with the
    # traceback — a failed run should not also destroy the expensive part.
    schema = json.loads((SCHEMA_DIR / "state.schema.json").read_text(encoding="utf-8"))
    try:
        state_text = complete(
            "state",
            fill(
                prompt("state_pl.md"),
                {"stan": common["stan"], "wpis": entry_text, "schema": json.dumps(schema, ensure_ascii=False, indent=2)},
            ),
            "Wyciągnij stan.",
            output_schema=schema,
        )
        state = json.loads(_strip_fence(state_text))
    except Exception as error:
        raise PipelineError(
            f"state extraction failed: {error}\n\n"
            f"--- the entry was written, and is not lost ---\n{entry_text}"
        ) from error
    state["day"] = params["day"]

    return {"params": params, "entry": entry_text, "state": state}


def save(result: dict) -> dict:
    """Write both files, then let the guards decide whether they may stay.

    Guarding after the write rather than before is deliberate: the guard reads
    files, and it checks the entry against every other entry, which needs it on
    disk. A failure removes both files, so a rejected run leaves nothing.
    """
    day = result["params"]["day"]
    entry_path = ENTRIES_DIR / f"{day:04d}.md"
    state_path = STATE_DIR / f"{day:04d}.json"

    if entry_path.exists() or state_path.exists():
        raise PipelineError(f"day {day} already has files; refusing to overwrite")

    entry_path.write_text(result["entry"].rstrip() + "\n", encoding="utf-8")
    state_path.write_text(
        json.dumps(result["state"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    guard = subprocess.run(
        ["node", str(GUARD)], capture_output=True, text=True, encoding="utf-8", cwd=REPO
    )
    if guard.returncode != 0:
        entry_path.unlink(missing_ok=True)
        state_path.unlink(missing_ok=True)
        raise PipelineError("guards rejected the entry, nothing written:\n" + (guard.stdout + guard.stderr))

    # Frontmatter is parsed back rather than trusted: it came from a model.
    frontmatter, _ = parse_entry(entry_path)
    return {"day": day, "entry": entry_path, "state": state_path, "title": frontmatter["title"]}
