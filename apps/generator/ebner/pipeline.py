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

import difflib
import json
import re
import subprocess
import unicodedata
from functools import lru_cache
from pathlib import Path

from .apply import ENTRIES_DIR, STATE_DIR, parse_entry
from .config import PROMPTS_DIR, prompt, rhythm
from .context import (
    load_world,
    render_entities,
    render_location,
    render_opinions,
    render_places,
    render_previous,
    render_state,
)
from .d1 import REPO
from .d1 import query as d1_query
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


def slugify(value: str) -> str:
    """Force a string into the slug shape the schemas require.

    `pattern` is stripped from the schema sent to the API, so nothing stops a
    model from returning `Pierścień_3` where `pierscien-3` is wanted. The guard
    catches it, but catching costs a run; normalising costs nothing and is
    deterministic. Polish diacritics fold to ASCII because the ids are
    identifiers, not prose — the prose beside them keeps its accents.
    """
    folded = value.replace("ł", "l").replace("Ł", "L")
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    folded = re.sub(r"[^a-zA-Z0-9]+", "-", folded).strip("-").lower()
    return folded or "x"


# Every field the schemas type as a slug. Normalising them together keeps
# references intact: an id and the places that point at it fold the same way.
_SLUG_FIELDS = {
    "entities": ("id", "parent"),
    "travel": ("from", "to"),
    "threads": ("id",),
    "facts_opened": ("id", "subject"),
    "facts_closed": ("id",),
    "fragments": ("id",),
}


def _nearest(value: object, known: set[str], cutoff: float = 0.78) -> str | None:
    """The id `value` plainly means, or None if nothing is close enough."""
    if not isinstance(value, str) or not known:
        return None
    if value in known:
        return value
    near = difflib.get_close_matches(value, sorted(known), n=1, cutoff=cutoff)
    return near[0] if near else None


def normalise_state(
    state: dict,
    known_threads: set[str] | None = None,
    known_facts: set[str] | None = None,
    known_entities: set[str] | None = None,
) -> dict:
    """Fix mechanically what a prompt would only ask for.

    Every failure this function handles began as an instruction in a prompt,
    which the model then got slightly wrong, which cost an entry that was
    already written, checked, edited and paid for. Slugs were the first. Three
    more in one run of seven were all the same shape — an id off by a syllable
    — which is why references are now resolved as a class rather than patched
    one identifier at a time.

    Anything with a single correct answer derivable from the data belongs
    here. What is left for the prompt is judgement.
    """
    for section, fields in _SLUG_FIELDS.items():
        for item in state.get(section) or []:
            for field in fields:
                if isinstance(item.get(field), str):
                    item[field] = slugify(item[field])
    for fragment in state.get("fragments") or []:
        if isinstance(fragment.get("threads"), list):
            fragment["threads"] = [slugify(t) for t in fragment["threads"] if isinstance(t, str)]

    # --- references ------------------------------------------------------
    #
    # Every id in a delta either names something that already exists or
    # introduces it. A near miss does neither, and three finished entries have
    # now been destroyed by one: `f-ebner-strategi-a-wywiad-postep` for
    # `f-ebner-strategia-wywiad`, `hanna-rura-do-sprzedazy` for
    # `f-hanna-rura-do-sprzedazy`, `nowe-zlecenie-glosowania` for
    # `nowe-zlecenie-glosowanie`. Each of those ids was listed verbatim in the
    # context the extractor was given, so asking more clearly is not a fix that
    # remains available.
    #
    # So every reference is resolved to what it plainly means. What cannot be
    # resolved is dropped where the schema permits a gap, and left alone where
    # it does not — an unresolvable subject means the entry referred to
    # something it never introduced, which is a real inconsistency and the
    # guard's business, not a typo.
    def _note(kind: str, was: object, now: str) -> None:
        print(f"  {kind}: `{now}`, which the extractor called `{was}`")

    # An operation on a thread nobody has heard of is either a typo for one we
    # have or an opening the model mislabelled. Try the typo first: flipping to
    # `open` when the thread already exists would fork it in two.
    if known_threads is not None:
        for thread in state.get("threads") or []:
            if thread.get("op") == "open" or thread.get("id") in known_threads:
                continue
            match = _nearest(thread.get("id"), known_threads)
            if match:
                _note("thread", thread.get("id"), match)
                thread["id"] = match
            else:
                thread["op"] = "open"
                thread.setdefault("status", "active")

    # Ids introduced by this very delta count as known to the rest of it.
    thread_ids = set(known_threads or set()) | {
        t["id"] for t in state.get("threads") or [] if isinstance(t.get("id"), str)
    }
    entity_ids = set(known_entities or set()) | {
        e["id"] for e in state.get("entities") or [] if isinstance(e.get("id"), str)
    }

    if known_threads is not None:
        for fragment in state.get("fragments") or []:
            if not isinstance(fragment.get("threads"), list):
                continue
            kept_threads: list[str] = []
            for ref in fragment["threads"]:
                match = _nearest(ref, thread_ids)
                if match:
                    if match != ref:
                        _note("fragment thread", ref, match)
                    kept_threads.append(match)
                else:
                    print(f"  dropping fragment reference to unknown thread `{ref}`")
            fragment["threads"] = kept_threads

    if known_entities is not None:
        for entity in state.get("entities") or []:
            parent = entity.get("parent")
            if parent is None:
                continue
            match = _nearest(parent, entity_ids - {entity.get("id")})
            if match and match != parent:
                _note("parent", parent, match)
                entity["parent"] = match
            elif not match:
                print(f"  clearing unknown parent `{parent}` of `{entity.get('id')}`")
                entity["parent"] = None

        # A fact about something the delta never introduced is dropped, not
        # fatal. This was left to the guard on the grounds that it is a real
        # inconsistency rather than a typo — and then it destroyed a fourth
        # entry, for two facts about a freighter the extractor described at
        # length and forgot to list as an entity.
        #
        # Inventing the entity is the worse repair: `kind` comes from an enum
        # and a wrong guess would put a ship in the geography. Dropping costs a
        # recorded detail, and `extract` can re-derive a day's state later,
        # which is not true of prose that was never published.
        kept_facts: list[dict] = []
        for fact in state.get("facts_opened") or []:
            match = _nearest(fact.get("subject"), entity_ids)
            if match:
                if match != fact.get("subject"):
                    _note("subject", fact.get("subject"), match)
                fact["subject"] = match
                kept_facts.append(fact)
            else:
                print(
                    f"  dropping fact `{fact.get('id')}`:"
                    f" subject `{fact.get('subject')}` was never introduced"
                )
        if "facts_opened" in state:
            state["facts_opened"] = kept_facts

        for hop in state.get("travel") or []:
            for end in ("from", "to"):
                if hop.get(end) is None:
                    continue
                match = _nearest(hop.get(end), entity_ids)
                if match and match != hop.get(end):
                    _note(f"travel {end}", hop.get(end), match)
                    hop[end] = match

    # A fact can only be closed by the id it was opened under. A close nothing
    # matches is dropped rather than fatal: in D1 it updates no rows either
    # way, so failing the run would destroy the prose to punish a typo.
    if known_facts is not None:
        kept: list[dict] = []
        for fact in state.get("facts_closed") or []:
            match = _nearest(fact.get("id"), known_facts, cutoff=0.72)
            if match:
                if match != fact.get("id"):
                    _note("closing", fact.get("id"), match)
                fact["id"] = match
                kept.append(fact)
            else:
                print(f"  dropping close of `{fact.get('id')}`: no open fact by that name")
        if "facts_closed" in state:
            state["facts_closed"] = kept

    return state


def _strip_fence(text: str) -> str:
    """Models like to wrap an answer in a code fence. Take what is inside."""
    fenced = re.search(r"```(?:\w+)?\r?\n(.*?)```", text, re.DOTALL)
    return fenced.group(1).strip() if fenced else text.strip()


def _fenced(text: str, tag: str) -> str:
    """The body of the first ```tag block."""
    found = re.search(rf"```{tag}\r?\n(.*?)```", text, re.DOTALL)
    return found.group(1) if found else ""


@lru_cache(maxsize=1)
def _calendar_rule() -> tuple[re.Pattern[str] | None, str]:
    """The forbidden vocabulary and its repair, read from the prompt.

    Both live in `prompts/calendar_pl.md` rather than here: they are the
    world's vocabulary, so changing the rule should be an edit to Polish text,
    not to Python.
    """
    text = prompt("calendar_pl.md")
    patterns = [
        line.strip()
        for line in _fenced(text, "regex").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    repair = _fenced(text, "text").strip()
    if not patterns or not repair:
        return None, ""
    return re.compile(r"\b(" + "|".join(patterns) + r")\b", re.IGNORECASE), repair


def calendar_slips(text: str) -> list[str]:
    """Fixes for earthly calendar units, found mechanically.

    The writing prompt forbids these and the consistency check is told to
    catch them, and between them they let `w przyszłym tygodniu` through four
    times — word for word, as the closing sentence of four separate entries.
    Two prompts asking twice is where this stops being a wording problem.

    Detection is deterministic; the repair is not, so these join the fix list
    the edit step applies rather than a guard that would throw the entry away.
    """
    pattern, repair = _calendar_rule()
    if pattern is None:
        return []

    fixes = []
    for word in dict.fromkeys(m.group(0) for m in pattern.finditer(text)):
        sentence = next((l.strip() for l in text.splitlines() if word in l), "")
        where = f" (w zdaniu: {sentence[:70]}…)" if sentence else ""
        fixes.append("- " + repair.replace("{slowo}", word) + where)
    return fixes


def report_edit(before: str, after: str) -> dict:
    """Say how much the language pass actually changed.

    The edit step regenerates the whole entry to apply a handful of fixes, and
    on a long entry that is an eighth of the bill. Whether it earns that is a
    measurable question nobody had measured: a step that rewrites Opus's Polish
    with Sonnet at low effort might be improving it, or might be flattening it,
    or might be changing three commas for five cents.

    Reporting rather than deciding. A few runs of this is the evidence the
    decision needs.
    """
    ratio = difflib.SequenceMatcher(None, before, after).ratio()
    para_before = [p.strip() for p in before.split("\n\n") if p.strip()]
    para_after = [p.strip() for p in after.split("\n\n") if p.strip()]
    touched = sum(1 for p in para_after if p not in para_before)

    print(
        f"  redakcja: podobieństwo {ratio:.3f},"
        f" akapitów zmienionych {touched}/{len(para_after)},"
        f" znaków {len(before)} → {len(after)}"
    )
    # One example, so a high similarity score can be read rather than trusted.
    for line in difflib.unified_diff(
        before.splitlines(), after.splitlines(), n=0, lineterm=""
    ):
        if line.startswith(("+++", "---", "@@")):
            continue
        print(f"    {line[:150]}")
        break

    return {"ratio": ratio, "paragraphs_touched": touched, "paragraphs": len(para_after)}


def report_extraction(state: dict) -> list[str]:
    """Say out loud when a delta records suspiciously little.

    Days 28, 29 and 30 each opened no facts at all, and nothing said so. Three
    entries in a row added nothing to the canon — including the one whose whole
    subject was measuring how often the signal arrives — and the gap only
    surfaced when day 33 contradicted a figure that had never been written
    down, and a reader noticed.

    A warning rather than a refusal: a genuinely uneventful day can legitimately
    record nothing, and throwing away a finished entry over a judgement call is
    the wrong trade. But an empty delta looked exactly like a quiet one, and
    that is the property worth removing — every silent failure in this project
    has cost more than the loud ones.
    """
    notes = []
    if not (state.get("facts_opened") or []):
        notes.append("żadnych faktów — czy wpis na pewno niczego nie ustalił?")
    if not (state.get("fragments") or []):
        notes.append("żadnych fragmentów — nic nie trafi do wyszukiwania")
    if not (state.get("threads") or []):
        notes.append("żadnej operacji na sprawach")

    for note in notes:
        print(f"  uwaga: {note}")
    return notes


def reconcile_travel(state: dict, location: str | None) -> dict:
    """Make the recorded journey end where the entry says the day ended.

    Two sources disagree here and one of them knows the story. `location` is
    written by the step that wrote the prose; the hops are read back out of
    that prose afterwards by a different model. When the last hop lands
    somewhere else, the hop is what is wrong — and the guard rejects the run
    for it, which is a whole paid entry lost to a disagreement we can settle.

    Only the final destination is corrected. The route in between is the
    extractor's to report and there is nothing here that could check it.
    """
    hops = state.get("travel") or []
    if not location or not hops:
        return state

    hops = sorted(hops, key=lambda h: h.get("seq") or 0)
    last = hops[-1]
    if last.get("to") == location:
        return state

    print(f"  podróż kończy się w `{location}`, nie w `{last.get('to')}` — poprawiam")
    last["to"] = location
    state["travel"] = hops
    return state


def normalise_entry(text: str, known: dict[str, object] | None = None) -> str:
    """Supply the frontmatter keys the writer has no say over.

    Twice now an entry has been written, checked, edited, paid for and then
    rejected for a missing frontmatter field. `image` is always null at this
    point, since the sketch step does not exist; `kind` and `day` were drawn by
    the randomiser and handed to the prompt, so the pipeline knows both. In
    every case the writer was being asked to copy back something it had been
    told, and the schema required it.

    Missing keys are filled in. A key that is present is left alone, even when
    it disagrees: the writer may have had a reason, the consistency check reads
    the prose and can judge, and this function cannot.
    """
    match = re.match(r"^﻿?---\r?\n(.*?)\r?\n---\r?\n", text, re.DOTALL)
    if not match:
        # No frontmatter at all is a real failure, not a missing default: leave
        # it for the guard to report against the schema.
        return text

    block = match.group(1)
    defaults: dict[str, object] = {"image": None, **(known or {})}

    added = []
    for key, value in defaults.items():
        if re.search(rf"^{re.escape(key)}:", block, re.MULTILINE):
            continue
        if value is None:
            rendered = "null"
        elif isinstance(value, int):
            rendered = str(value)
        else:
            rendered = str(value)
        added.append(f"{key}: {rendered}")
        print(f"  frontmatter: dopisuję `{key}: {rendered}`")

    if not added:
        return text
    return text[: match.start(1)] + block + "\n" + "\n".join(added) + text[match.end(1) :]


def generate(*, seed: int | None = None, remote: bool = True, dry_run: bool = False) -> dict:
    world = load_world(remote=remote)
    params = plan_entry(rhythm(), world, seed=seed)
    fragments = recall(world, params, remote=remote)

    common = {
        "stan": render_state(world),
        "poprzedni": render_previous(world),
        "miejsce": render_location(world),
        "zapomniane": render_places(world),
        "oceny": render_opinions(world),
        "rag": render_recall(fragments),
        "dzien": params["day"],
        # The bare id, because this also lands in the frontmatter, where the
        # schema wants a value from the enum and not a description of it. The
        # readable label goes in `rodzaj_opis`.
        "rodzaj": params["kind"],
        "rodzaj_opis": params["kind_label"],
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
    lines = [line.strip() for line in checked.splitlines() if line.strip()]
    verdict = lines[0].lower() if lines else ""
    if verdict.startswith("werdykt: blokuj"):
        raise PipelineError("consistency check blocked the entry:\n" + checked)

    # The check returns fixes, not a rewritten entry. It used to return the
    # whole thing, which cost more output tokens than writing it did — for a
    # step that usually changes nothing.
    fixes = [line for line in lines[1:] if line.startswith("-")]
    # Merged rather than trusted to the checker, which has been told to find
    # these and does not reliably.
    for slip in calendar_slips(entry_text):
        if slip not in fixes:
            fixes.append(slip)
            print(f"  kalendarz: {slip[:88]}")
    fixes_text = "\n".join(fixes) if fixes else "Brak — wpis przeszedł bez uwag."

    # --- 4. edit ---------------------------------------------------------
    # Applies those fixes and passes over the language, so the full text is
    # generated once in the pipeline rather than twice.
    before_edit = entry_text
    entry_text = normalise_entry(
        _strip_fence(
            complete(
                "edit",
                fill(prompt("edit_pl.md"), {"wpis": entry_text, "poprawki": fixes_text}),
                "Zredaguj wpis.",
            )
        ),
        {"day": params["day"], "kind": params["kind"]},
    )
    report_edit(before_edit, entry_text)

    # Checked again, because the step that was given these fixes rewrites the
    # prose and can introduce the very thing it was told to remove. Day 36 came
    # back with `tydzień` in a sentence the writer had not written: the
    # detector ran before the edit, found nothing, and nothing looked again.
    #
    # One further pass, never a loop. If a second editor still cannot say it in
    # days, that is a sentence worth publishing with the flaw rather than
    # paying indefinitely to remove one word.
    remaining = calendar_slips(entry_text)
    if remaining:
        print(f"  kalendarz: po redakcji zostało {len(remaining)} — jeszcze raz")
        entry_text = normalise_entry(
            _strip_fence(
                complete(
                    "edit",
                    fill(
                        prompt("edit_pl.md"),
                        {"wpis": entry_text, "poprawki": "\n".join(remaining)},
                    ),
                    "Zredaguj wpis.",
                )
            ),
            {"day": params["day"], "kind": params["kind"]},
        )
        still = calendar_slips(entry_text)
        if still:
            print(f"  kalendarz: nadal {len(still)}, zostawiam i publikuję")

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
                {
                    "stan": common["stan"],
                    "byty": render_entities(world),
                    "skad": common["miejsce"],
                    "wpis": entry_text,
                    "schema": json.dumps(schema, ensure_ascii=False, indent=2),
                },
            ),
            "Wyciągnij stan.",
            output_schema=schema,
        )
        state = normalise_state(
            json.loads(_strip_fence(state_text)),
            {t["id"] for t in world["threads"]},
            {f["id"] for f in world["facts"]},
            {e["id"] for e in world["entities"]},
        )
    except Exception as error:
        raise PipelineError(
            f"state extraction failed: {error}\n\n"
            f"--- the entry was written, and is not lost ---\n{entry_text}"
        ) from error
    state["day"] = params["day"]

    # The entry knows where the day ended; the extractor only read about it.
    frontmatter = re.search(r"^location:\s*(\S+)\s*$", entry_text, re.MULTILINE)
    reconcile_travel(state, frontmatter.group(1) if frontmatter else None)
    report_extraction(state)

    return {"params": params, "entry": entry_text, "state": state}


def _location_before(day: int, *, remote: bool = True) -> str:
    """Where the entry before this one ended."""
    rows = d1_query(
        "SELECT e.location, n.name FROM entries e "
        "LEFT JOIN entities n ON n.id = e.location "
        f"WHERE e.day < {int(day)} ORDER BY e.day DESC LIMIT 1",
        remote=remote,
    )
    if not rows:
        return "Nigdzie — to pierwszy wpis."
    row = rows[0]
    return f"**{row.get('name') or row['location']}** (`{row['location']}`)"


def extract_for(day: int, *, remote: bool = True) -> dict:
    """Re-run step 5 against an entry that already exists.

    A recovery path, not part of the daily loop. Extraction is the cheapest of
    the four steps, so when it produces something wrong there is no reason to
    pay for the prose again to fix it.
    """
    entry_path = ENTRIES_DIR / f"{day:04d}.md"
    if not entry_path.exists():
        raise PipelineError(f"no entry at {entry_path.name}")

    world = load_world(remote=remote)
    schema = json.loads((SCHEMA_DIR / "state.schema.json").read_text(encoding="utf-8"))
    entry_text = entry_path.read_text(encoding="utf-8")

    state_text = complete(
        "state",
        fill(
            prompt("state_pl.md"),
            {
                "stan": render_state(world),
                "byty": render_entities(world),
                # Where the entry BEFORE this one ended — not the current
                # location, which for a historical re-extraction is a later
                # day's and would push the hops somewhere the entry never was.
                "skad": _location_before(day, remote=remote),
                "wpis": entry_text,
                "schema": json.dumps(schema, ensure_ascii=False, indent=2),
            },
        ),
        "Wyciągnij stan.",
        output_schema=schema,
    )
    state = normalise_state(
        json.loads(_strip_fence(state_text)),
        {t["id"] for t in world["threads"]},
        {f["id"] for f in world["facts"]},
        {e["id"] for e in world["entities"]},
    )
    state["day"] = day

    state_path = STATE_DIR / f"{day:04d}.json"
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"day": day, "state": state_path}


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
