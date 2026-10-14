"""The host's spell parser (spec/Delvetalk/Host/Spell.lean, op `spell-parse`) answers every recorded
input as the fixtures say: parse, bare and fit, with the refusal clause names.

Evidence for FOUNDATION §5 "Spell grammar" (layer: host): the host parses spells. The fixtures
(tests/fixtures/spells/*.json) were recorded from the Bend grammar, which the host agreed with on
every row before world/lib/Spell.obend's parser was deleted (lane/objects9); the host is the
grammar now; tests/test_spell.py adds the cases the recording lacks.

    python3 -m unittest tests.test_host_spell -v
"""
import json
import os
import unittest

from tests.test_objects import check

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "spells")


def fixtures(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as handle:
        return json.load(handle)


def host(request):
    out = check(dict(request, op="spell-parse"))
    assert out["status"] == "parsed", out
    return out


def show_bindings(items):
    return "".join("%s=%s;" % (b["name"], b["value"]) for b in items)


def show_parsed(out):
    if "spell" in out:
        s = out["spell"]
        return "spell %s %s %s" % (s["card"], s["action"], show_bindings(s["fields"]))
    return "not a spell: " + out["notASpell"]["reason"]


def show_value(v):
    (kind, value), = v.items()
    return str(value)


def show_fit(fit):
    if "proposal" in fit:
        p = fit["proposal"]
        return "proposal %s %s %s" % (p["card"], p["action"], "".join("%s=%s;" % (e["name"], show_value(e["value"])) for e in p["bindings"]))
    if "unclear" in fit:
        return "unclear " + "".join(n + "|" for n in fit["unclear"]["needs"])
    return "refused " + fit["refused"]["reason"]


class Recorded(unittest.TestCase):
    def test_every_recorded_row_parses_fits_and_binds_bare_as_recorded(self):
        for row in fixtures("parse"):
            with self.subTest(parse=row["text"][:60]):
                out = host({"text": row["text"]})
                self.assertEqual(show_parsed(out), row["expected"], row["text"])
                self.assertEqual(show_bindings(out["bare"]), row["bare"], row["text"])
        for row in fixtures("fit") + fixtures("natural"):
            with self.subTest(fit=row["text"][:60]):
                out = host({"text": row["text"], "form": row["form"]})
                self.assertEqual(show_parsed(out), row["parsed"], row["text"])
                self.assertEqual(show_fit(out["fit"]), row["expected"], row["text"])
        for row in fixtures("bare"):
            with self.subTest(bare=row["text"][:60]):
                self.assertEqual(show_bindings(host({"text": row["text"]})["bare"]), row["expected"], row["text"])


class Clauses(unittest.TestCase):
    def test_object_fields_fit_id_shapes_and_optional_empty(self):
        for minimum in (0, 1):
            form = {"card": "walker", "action": "walk", "fields": [
                {"name": "target", "kind": {"object": {"min": minimum, "max": 128}}}]}
            for target in ("A0-:/._", "x" * 128):
                with self.subTest(minimum=minimum, target=target):
                    fit = host({"text": "delvetalk walker walk / target: " + target, "form": form})["fit"]
                    self.assertEqual(show_fit(fit), "proposal walker walk target=%s;" % target)
            for target in ("a phrase", "x" * 129, "x?", "é"):
                with self.subTest(minimum=minimum, target=target):
                    fit = host({"text": "delvetalk walker walk / target: " + target, "form": form})["fit"]
                    self.assertEqual(fit["refused"]["clause"], "badValue", fit)
                    self.assertIn("target takes an object id", fit["refused"]["reason"])
            fit = host({"text": "delvetalk walker walk", "form": form})["fit"]
            self.assertEqual(show_fit(fit), "proposal walker walk target=;" if minimum == 0 else "unclear target|")

    def test_each_refusal_names_its_clause_unclear_its_needs_and_prose_whether_it_has_fields(self):
        form = fixtures("fit")[0]["form"]
        for reply, clause in (("delvetalk garden-2 plant", "otherCard"), ("delvetalk garden-1 prune", "otherCard"),
                              ("prose", "noAction"), ("delvetalk garden-1 plant now", "noAction"),
                              ("delvetalk garden-1 plant\nseed: a\nseed: b", "duplicateField"),
                              ("delvetalk garden-1 plant\ncolour: green", "badValue"),
                              ("delvetalk garden-1 plant\nseed: <<S\nx", "unclosedBlock")):
            with self.subTest(reply=reply):
                fit = host({"text": reply, "form": form})["fit"]
                self.assertEqual(fit.get("refused", {}).get("clause"), clause, fit)
        self.assertEqual(host({"text": "delvetalk garden-1 plant\nseed: fern", "form": form})["fit"], {"unclear": {"needs": ["colour"]}})
        self.assertIs(host({"text": "plant: a fern"})["notASpell"]["fielded"], True)
        # A field whose text bound starts at 0 may be left out: it reads as empty (`kinds make` with a name and an of).
        make = {"card": "kinds", "action": "make", "fields": [{"name": "name", "kind": {"text": {"min": 1, "max": 80}}},
                                                              {"name": "law", "kind": {"text": {"min": 0, "max": 4096}}}]}
        self.assertEqual(show_fit(host({"text": "delvetalk kinds make / name: lamp", "form": make})["fit"]), "proposal kinds make name=lamp;law=;")
        self.assertEqual(host({"text": "delvetalk kinds make / law: x", "form": make})["fit"], {"unclear": {"needs": ["name"]}})
        # A misspelled field with a field the form names behind it is refused, naming it; trailing prose with a colon still ends the fields.
        three = {"card": "kinds", "action": "make", "fields": make["fields"] + [{"name": "of", "kind": {"text": {"min": 1, "max": 80}}}]}
        fit = host({"text": "delvetalk kinds make\nname: lamp\nof: record\nvoce: lunar\nlaw: maker only", "form": three})["fit"]
        self.assertEqual(fit["refused"]["clause"], "unknownField", fit)
        self.assertIn("voce", fit["refused"]["reason"])
        self.assertIn("name, law, of", fit["refused"]["reason"])
        fit = host({"text": "delvetalk kinds make\nname: lamp\nof: record\nhob: still owed - a note", "form": three})["fit"]
        self.assertEqual(show_fit(fit), "proposal kinds make name=lamp;law=;of=record;")
        self.assertIs(host({"text": "just prose"})["notASpell"]["fielded"], False)


PREVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "previews", "commonplace-card.txt")


class Margin(unittest.TestCase):
    """A post quoting a card does not cast (the owner's outreach, 2026-10-11: the root menu quoted under a greeting
    was read as `env observe`, entry 147). A spell starts at the margin; an indented one is an example."""

    def test_the_owners_post_quoting_the_root_menu_casts_nothing(self):
        with open(PREVIEW, encoding="utf-8") as handle:
            post = "Hello delve! This is the town I have been building; here is its first card:\n\n" + handle.read()
        out = host({"text": post})
        self.assertNotIn("spell", out)
        self.assertTrue(out["quotation"]["reason"].startswith("This quotes a card (✾ DELVETALK · THE COMMONPLACE)"), out)
        form = fixtures("fit")[0]["form"]
        self.assertEqual(host({"text": post, "form": form})["fit"]["refused"]["clause"], "quotation")

    def test_a_quote_from_the_commonplaces_door_count_on_casts_nothing(self):
        """The commonplace's head line is its door count (`Menu.trieHead`): `Eight doors.`, `One door.`."""
        with open(PREVIEW, encoding="utf-8") as handle:
            card = handle.read()
        doors = card[card.index("\n\n") + 2:]
        self.assertRegex(doors, r"^[A-Z][a-z]+ doors\. ")
        for head in (doors, "One door. " + doors[doors.index(". ") + 2:]):
            with self.subTest(head=head[:12]):
                out = host({"text": "this is how it reads:\n\n" + head})
                self.assertNotIn("spell", out)
                self.assertTrue(out["quotation"]["reason"].startswith("This quotes a card (" + head[:12]), out)

    def test_a_spell_at_the_margin_casts_and_indented_among_other_lines_does_not(self):
        spell = "delvetalk garden plant / seed: x / colour: amber"
        self.assertEqual(show_parsed(host({"text": spell})), "spell garden plant seed=x;colour=amber;")
        for indent in ("  ", "    ", "\t"):
            with self.subTest(indent=repr(indent)):
                self.assertIn("notASpell", host({"text": "see:\n" + indent + spell + "\nnice"}))
                self.assertIn("notASpell", host({"text": indent + spell + "\nthat is how it goes"}))

    def test_a_post_that_is_one_spell_block_is_dedented_and_cast(self):
        planted = "spell garden plant colour=amber;seed=x;"
        for post in ("  delvetalk garden plant / colour: amber / seed: x",  # pasted with its indent
                     "    delvetalk garden plant\n    colour: amber\n    seed: x\n",  # a Zulip code block
                     "\t\tdelvetalk garden plant\n\t\tcolour: amber\n\n\t\tseed: x",
                     "```\ndelvetalk garden plant\ncolour: amber\nseed: x\n```",  # one fence
                     "```text\n  delvetalk garden plant\n  colour: amber\n  seed: x\n```"):
            with self.subTest(post=post):
                self.assertEqual(show_parsed(host({"text": post})), planted)
        # Not uniform, or another line beside the block: an example.
        for post in ("    delvetalk garden plant\ncolour: amber", "  delvetalk garden plant\n  colour: amber\n  I think so"):
            with self.subTest(post=post):
                self.assertIn("notASpell", host({"text": post}))
        # An indented example after a spell's fields neither ends nor replaces it.
        self.assertEqual(show_parsed(host({"text": "delvetalk garden plant\nseed: x\n  delvetalk tide tick\ncolour: amber"})),
                         "spell garden plant seed=x;colour=amber;")

if __name__ == "__main__":
    unittest.main()
