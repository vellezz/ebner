"""What the generator must get right without asking a model.

Every case here is a failure that happened. Each one destroyed an entry that
had already been written, checked, edited and paid for, because the pipeline
asked a model for a mechanical detail and then rejected its answer. The fix in
each case was to stop asking; these tests are what stops the fix from being
quietly undone.

The project has no test suite for its *writing*, deliberately — prose is not
testable and the guards are the only layer. This is the other half: the code
that decides what the world records, which has broken four times on the same
shape of mistake.

    python -m unittest discover -s apps/generator/tests
"""

from __future__ import annotations

import copy
import unittest

from ebner.context import FACT_LIMIT, select_facts
from ebner.pipeline import (
    calendar_slips,
    normalise_entry,
    normalise_state,
    reconcile_travel,
    register_slip,
    report_extraction,
)
from ebner.rhythm import pick_length


KNOWN_THREADS = {"nowe-zlecenie-glosowanie", "dlug-z-varnu"}
KNOWN_FACTS = {"f-hanna-rura-do-sprzedazy", "f-ebner-strategia-wywiad"}
KNOWN_ENTITIES = {"ebner-gripe", "hanna", "stacja-glosowania", "szlak-za-hoonem"}


def normalise(state: dict) -> dict:
    return normalise_state(
        copy.deepcopy(state), KNOWN_THREADS, KNOWN_FACTS, KNOWN_ENTITIES
    )


class References(unittest.TestCase):
    """Ids off by a syllable. Three entries died on these in one run of seven.

    Every one of the ids below was listed verbatim in the context the
    extractor was given, which is why wording the request more firmly is not a
    remedy that remains available.
    """

    def test_fact_close_mangled(self):
        state = normalise({"facts_closed": [{"id": "f-ebner-strategi-a-wywiad-postep"}]})
        self.assertEqual(state["facts_closed"][0]["id"], "f-ebner-strategia-wywiad")

    def test_fact_close_missing_prefix(self):
        state = normalise({"facts_closed": [{"id": "hanna-rura-do-sprzedazy"}]})
        self.assertEqual(state["facts_closed"][0]["id"], "f-hanna-rura-do-sprzedazy")

    def test_fragment_thread_typo(self):
        state = normalise(
            {
                "fragments": [
                    {
                        "id": "x",
                        "kind": "scene",
                        "content": "c",
                        "threads": ["nowe-zlecenie-glosowania"],
                    }
                ]
            }
        )
        self.assertEqual(state["fragments"][0]["threads"], ["nowe-zlecenie-glosowanie"])

    def test_thread_operation_typo_renames_rather_than_forking(self):
        """The case that decides the design.

        Flipping a near-miss to `open` would fork one thread into two, and
        nothing downstream could tell the halves apart afterwards.
        """
        state = normalise(
            {"threads": [{"id": "nowe-zlecenie-glosowania", "op": "update", "summary": "s"}]}
        )
        self.assertEqual(state["threads"][0]["id"], "nowe-zlecenie-glosowanie")
        self.assertEqual(state["threads"][0]["op"], "update")

    def test_genuinely_unknown_thread_becomes_an_opening(self):
        state = normalise(
            {"threads": [{"id": "zupelnie-inna-sprawa", "op": "update", "summary": "s"}]}
        )
        self.assertEqual(state["threads"][0]["op"], "open")
        self.assertEqual(state["threads"][0]["id"], "zupelnie-inna-sprawa")

    def test_an_opening_is_never_resolved_onto_an_existing_thread(self):
        """A new thread is allowed to be named almost anything."""
        state = normalise(
            {"threads": [{"id": "nowe-zlecenie-glosowania", "op": "open", "summary": "s"}]}
        )
        self.assertEqual(state["threads"][0]["id"], "nowe-zlecenie-glosowania")

    def test_thread_opened_by_this_delta_counts_as_known(self):
        state = normalise(
            {
                "threads": [{"id": "swiezy-watek", "op": "open", "summary": "s"}],
                "fragments": [
                    {"id": "x", "kind": "scene", "content": "c", "threads": ["swiezy-watek"]}
                ],
            }
        )
        self.assertEqual(state["fragments"][0]["threads"], ["swiezy-watek"])

    def test_entity_parent_and_fact_subject_and_travel(self):
        state = normalise(
            {
                "entities": [
                    {"id": "nowy-dok", "kind": "place", "name": "N", "parent": "stacja-glosowani"}
                ],
                "facts_opened": [{"id": "f-a", "content": "c", "subject": "ebner-grype"}],
                "travel": [{"seq": 1, "from": "szlak-za-hoone", "to": "stacja-glosowania"}],
            }
        )
        self.assertEqual(state["entities"][0]["parent"], "stacja-glosowania")
        self.assertEqual(state["facts_opened"][0]["subject"], "ebner-gripe")
        self.assertEqual(state["travel"][0]["from"], "szlak-za-hoonem")

    def test_a_destination_this_delta_introduces_is_left_alone(self):
        state = normalise(
            {
                "entities": [{"id": "orbita-nowa", "kind": "place", "name": "O"}],
                "travel": [{"seq": 1, "from": "stacja-glosowania", "to": "orbita-nowa"}],
            }
        )
        self.assertEqual(state["travel"][0]["to"], "orbita-nowa")

    def test_unrelated_references_are_dropped_not_forced_onto_a_neighbour(self):
        state = normalise(
            {
                "fragments": [
                    {"id": "x", "kind": "scene", "content": "c", "threads": ["calkiem-co-innego"]}
                ],
                "facts_closed": [{"id": "f-nic-takiego-nie-bylo"}],
                "entities": [
                    {"id": "nowy-dok", "kind": "place", "name": "N", "parent": "cos-z-kosmosu"}
                ],
            }
        )
        self.assertEqual(state["fragments"][0]["threads"], [])
        self.assertEqual(state["facts_closed"], [])
        self.assertIsNone(state["entities"][0]["parent"])

    def test_fact_about_an_entity_the_delta_never_introduced_is_dropped(self):
        """Left to the guard once, on the grounds that it is a real
        inconsistency rather than a typo. That judgement cost a fourth entry:
        the extractor described a freighter at length and forgot to list it.
        """
        state = normalise(
            {
                "facts_opened": [
                    {"id": "f-a", "content": "c", "subject": "frachtowiec-na-stacji"},
                    {"id": "f-b", "content": "c", "subject": "hanna"},
                ]
            }
        )
        self.assertEqual([f["id"] for f in state["facts_opened"]], ["f-b"])

    def test_slugs_still_fold(self):
        state = normalise({"entities": [{"id": "Pierścień_3", "kind": "place", "name": "P"}]})
        self.assertEqual(state["entities"][0]["id"], "pierscien-3")

    def test_correct_input_is_untouched(self):
        clean = {
            "threads": [{"id": "dlug-z-varnu", "op": "update", "summary": "s"}],
            "facts_closed": [{"id": "f-hanna-rura-do-sprzedazy"}],
            "fragments": [
                {"id": "x", "kind": "scene", "content": "c", "threads": ["dlug-z-varnu"]}
            ],
        }
        self.assertEqual(normalise(clean), clean)


class Frontmatter(unittest.TestCase):
    """`image` is a constant at this point, and the writer was asked to
    remember it. It forgot once, after the entry was written and paid for."""

    BASE = (
        "---\n"
        "day: 10\n"
        'title: "Dzień 10. Gdzieś"\n'
        "location: gdzies\n"
        "kind: quiet\n"
        "threads: [a-b]\n"
        "{extra}---\n\n"
        "Treść wpisu.\n"
    )

    def test_missing_image_is_supplied(self):
        self.assertEqual(
            normalise_entry(self.BASE.format(extra="")),
            self.BASE.format(extra="image: null\n"),
        )

    def test_present_image_is_untouched(self):
        for value in ("image: null\n", "image: sketches/abc.webp\n"):
            text = self.BASE.format(extra=value)
            self.assertEqual(normalise_entry(text), text)

    def test_missing_kind_is_supplied_from_the_draw(self):
        """The second field to be dropped after an entry was paid for. The
        randomiser chose it and the prompt was told it, so the writer was
        being asked to copy back something it had already been given."""
        without = self.BASE.format(extra="").replace("kind: quiet\n", "")
        out = normalise_entry(without, {"day": 10, "kind": "travel"})
        self.assertIn("kind: travel", out)
        self.assertIn("day: 10", out)
        self.assertEqual(out.count("day:"), 1)

    def test_a_field_that_disagrees_is_left_for_the_check_step(self):
        """This function reads no prose and cannot judge which is right."""
        text = self.BASE.format(extra="image: null\n")
        self.assertEqual(normalise_entry(text, {"day": 99, "kind": "travel"}), text)

    def test_body_containing_a_rule_survives(self):
        text = self.BASE.format(extra="").replace("Treść wpisu.", "Treść.\n\n---\n\nDalej.")
        out = normalise_entry(text)
        self.assertIn("image: null", out)
        self.assertTrue(out.endswith("Treść.\n\n---\n\nDalej.\n"))

    def test_no_frontmatter_is_left_to_the_guard(self):
        text = "Sam tekst, bez frontmattera.\n"
        self.assertEqual(normalise_entry(text), text)


class Calendar(unittest.TestCase):
    """This world has days and years, not weeks, months or weekday names.

    The rule is in the writing prompt and on the consistency check's list.
    Between them they let it through eight times, four of them as the same
    closing sentence word for word.
    """

    def words(self, text: str) -> list[str]:
        import re

        return sorted(re.search(r'zamień „(.+?)"', f).group(1) for f in calendar_slips(text))

    def test_the_real_offenders(self):
        self.assertEqual(self.words("Odpisałem, że zapłacę w przyszłym tygodniu."), ["tygodniu"])
        self.assertEqual(self.words("Drugi raz w ciągu dwóch tygodni."), ["tygodni"])
        self.assertEqual(self.words("od czterech lat i dwóch miesięcy"), ["miesięcy"])
        self.assertEqual(self.words("Wiedziałem to od czwartku."), ["czwartku"])

    def test_this_worlds_own_units_are_left_alone(self):
        for text in (
            "Nadajnik nie działa od trzech lat.",
            "Dwie doby do głosowania. Wczoraj, przedwczoraj, jutro.",
            "Trzy dni temu, tego samego dnia, na dniach.",
        ):
            self.assertEqual(calendar_slips(text), [], text)

    def test_words_that_merely_start_the_same_way(self):
        """Polish-specific, and the reason the list is not a simple prefix
        match: `lut` is Ebner's trade, not February."""
        for text in (
            "Zimny lut na nóżce dławika. Lutowałem kołnierz.",
            "Ludzie mają osiemdziesiąt siedem złączek w spisie.",
            "W środku było ciepło. Środek ciężkości. Ośrodek.",
            "Gruda smaru na prowadnicy.",
        ):
            self.assertEqual(calendar_slips(text), [], text)

    def test_one_fix_per_word_not_per_occurrence(self):
        text = "W tygodniu i w przyszłym tygodniu, i jeszcze raz w tygodniu."
        self.assertEqual(len(calendar_slips(text)), 1)


class Register(unittest.TestCase):
    """The diary is written by a repairman; the paperwork is there for the
    concrete to break against. Day 30 had twenty-three clerical words against
    one from the workshop, and the reader stopped reading at exactly the run
    of entries this measure points at."""

    CLERICAL = (
        'Rubryka nie przewiduje. Przepis mówi o dostawie, a dostawa ma linijkę '
        'w księdze. Odbiorca rozlicza się wstecz, termin biegnie od zdarzenia, '
        'a rejestr zapisuje właściciela. Urzędniczka wpisała aneks i zapis. '
        'Wniosek przechodzi na taryfę. Deklaracja, procedura, formalność.'
    )
    WORKSHOP = (
        'Rozebrałem wciągarkę: zapadka miała wyrobiony nos, sprężyna zmęczona, '
        'w gnieździe stary smar. Podciąłem pilnikiem, przetarłem gwint, '
        'dokręciłem złącza pod kołnierzem i wymieniłem uszczelkę przy zaworze. '
        'Rura, blacha, kątownik, łożysko, ogniwo.'
    )

    def test_a_clerical_entry_is_flagged(self):
        self.assertTrue(register_slip(self.CLERICAL))

    def test_an_entry_with_the_work_in_it_is_not(self):
        self.assertEqual(register_slip(self.CLERICAL + ' ' + self.WORKSHOP), [])
        self.assertEqual(register_slip(self.WORKSHOP), [])

    def test_a_short_note_is_never_flagged_on_proportion_alone(self):
        """Two clerical words and no tools is a sentence, not a protocol."""
        self.assertEqual(register_slip('Przepis mówi, że rubryka nie przewiduje.'), [])


class Travel(unittest.TestCase):
    """`location` is written by the step that wrote the prose; the hops are
    read back out of it afterwards by a different model. When they disagree
    about where the day ended, the entry is the one that knows."""

    def test_the_run_this_killed(self):
        state = reconcile_travel({"travel": [{"seq": 1, "from": "ubrek", "to": "oskra"}]}, "ubrek")
        self.assertEqual(state["travel"][-1]["to"], "ubrek")

    def test_only_the_last_hop_moves(self):
        state = reconcile_travel(
            {"travel": [{"seq": 2, "from": "b", "to": "c"}, {"seq": 1, "from": "a", "to": "b"}]},
            "d",
        )
        self.assertEqual([(h["from"], h["to"]) for h in state["travel"]], [("a", "b"), ("b", "d")])

    def test_nothing_to_reconcile(self):
        agreed = {"travel": [{"seq": 1, "from": "a", "to": "b"}]}
        self.assertEqual(reconcile_travel(copy.deepcopy(agreed), "b"), agreed)
        self.assertEqual(reconcile_travel(copy.deepcopy(agreed), None), agreed)
        self.assertEqual(reconcile_travel({"travel": []}, "a"), {"travel": []})
        self.assertEqual(reconcile_travel({}, "a"), {})


class EmptyDelta(unittest.TestCase):
    """Three entries in a row recorded no facts and nothing said so.

    One of them was entirely about measuring how often a signal arrives. The
    gap surfaced only when a later entry contradicted a figure that had never
    been written down, and a reader noticed.
    """

    def test_an_empty_delta_is_reported(self):
        notes = report_extraction({"day": 30})
        self.assertEqual(len(notes), 3)
        self.assertTrue(any("faktów" in n for n in notes))

    def test_a_full_delta_is_silent(self):
        notes = report_extraction(
            {
                "facts_opened": [{"id": "f-a", "content": "c", "subject": "hanna"}],
                "fragments": [{"id": "x", "kind": "scene", "content": "c"}],
                "threads": [{"id": "t", "op": "update"}],
            }
        )
        self.assertEqual(notes, [])

    def test_each_gap_is_named_separately(self):
        notes = report_extraction(
            {
                "facts_opened": [{"id": "f-a", "content": "c", "subject": "hanna"}],
                "fragments": [],
                "threads": [{"id": "t", "op": "update"}],
            }
        )
        self.assertEqual(len(notes), 1)
        self.assertIn("fragment", notes[0])


class Facts(unittest.TestCase):
    """Facts accumulate at about four an entry against half a closure, so
    every one of them going into every prompt is unbounded growth."""

    WORLD = {
        "last_day": 100,
        "location": [{"id": "stacja"}, {"id": "szlak"}],
        "entities": [
            {"id": "ebner-gripe", "last_entry": 100},
            {"id": "hanna", "last_entry": 100},
            {"id": "stacja", "last_entry": 98},
            {"id": "szlak", "last_entry": 100},
            {"id": "holdmark", "last_entry": 0},
            {"id": "daleki-ksiezyc", "last_entry": 30},
            {"id": "varnu", "last_entry": None},
        ],
    }

    def fact(self, i, subject, day, kind=None):
        return {"id": i, "subject": subject, "valid_from": day, "kind": kind, "content": "c"}

    def select(self, facts):
        return select_facts({**self.WORLD, "facts": facts})

    def test_what_survives(self):
        kept, omitted = self.select(
            [
                self.fact("f-seed-varnu", "varnu", 0),  # the debt: never touched
                self.fact("f-here", "stacja", 40),  # where he is, though old
                self.fact("f-in-play", "hanna", 20),  # subject in play
                self.fact("f-news", "daleki-ksiezyc", 95),  # elsewhere, fresh
                self.fact("f-cold", "daleki-ksiezyc", 30),  # elsewhere, cold
            ]
        )
        self.assertEqual(
            {f["id"] for f in kept}, {"f-seed-varnu", "f-here", "f-in-play", "f-news"}
        )
        self.assertEqual(omitted, 1)

    def test_the_seed_is_the_premise_and_never_goes(self):
        """The first version of this ranked by recency and dropped the entire
        backstory — who Ebner is, what Hanna is, where the debt comes from."""
        flood = [self.fact(f"f-far{i}", "daleki-ksiezyc", 99) for i in range(FACT_LIMIT + 20)]
        kept, _ = self.select(flood + [self.fact("f-seed", "ebner-gripe", 0)])
        self.assertIn("f-seed", {f["id"] for f in kept})

    def test_the_cap_cuts_the_far_invoice_before_the_local_rule(self):
        """A cap of thirty once cut the voting rule out from under a thread
        that was still running. An entry cannot contradict what it was told."""
        flood = [self.fact(f"f-far{i}", "daleki-ksiezyc", 99) for i in range(FACT_LIMIT + 20)]
        kept, _ = self.select(flood + [self.fact("f-rule-here", "stacja", 5, kind="world_rule")])
        self.assertIn("f-rule-here", {f["id"] for f in kept})
        self.assertEqual(len(kept), FACT_LIMIT)

    def test_a_subject_never_placed_is_not_recent(self):
        kept, _ = self.select([self.fact("f-varnu-new", "varnu", 50)])
        self.assertEqual(kept, [])


class Length(unittest.TestCase):
    """A journey needs room for a departure, a way and an arrival. Asked for a
    travel entry in two hundred words, the writer described a lift ride that
    went nowhere."""

    CFG = {
        "length": [
            {"id": "note", "weight": 20, "words": [50, 200]},
            {"id": "medium", "weight": 50, "words": [300, 700]},
            {"id": "long", "weight": 30, "words": [900, 1600]},
        ],
        "length_floor": {"travel": ["note"], "new_job": ["note"]},
    }

    def drawn(self, kind):
        import random

        rng = random.Random(7)
        return {pick_length(self.CFG, rng, kind)["id"] for _ in range(300)}

    def test_kinds_that_describe_movement_never_draw_a_note(self):
        for kind in ("travel", "new_job"):
            self.assertNotIn("note", self.drawn(kind), kind)

    def test_every_other_kind_keeps_the_whole_range(self):
        for kind in ("quiet", "continuation", "documents", None):
            self.assertIn("note", self.drawn(kind), kind)


if __name__ == "__main__":
    unittest.main()
