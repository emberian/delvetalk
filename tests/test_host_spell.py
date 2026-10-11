"""The host's spell parser (spec/Delvetalk/Host/Spell.lean, op `spell-parse`) answers every recorded
input as the fixtures say: parse, bare and fit, with the refusal clause names.

Evidence for WHOLENESS section 2 (layer: host): the host parses spells. The fixtures
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
    def test_each_refusal_names_its_clause_unclear_its_needs_and_prose_whether_it_has_fields(self):
        form = fixtures("fit")[0]["form"]
        for reply, clause in (("delvetalk garden-2 plant", "otherCard"), ("delvetalk garden-1 prune", "otherCard"),
                              ("prose", "noAction"), ("delvetalk garden-1 plant now", "noAction"),
                              ("delvetalk garden-1 plant\nsmell: x", "unknownField"),
                              ("delvetalk garden-1 plant\nseed: a\nseed: b", "duplicateField"),
                              ("delvetalk garden-1 plant\ncolour: green", "badValue"),
                              ("delvetalk garden-1 plant\nseed: <<S\nx", "unclosedBlock")):
            with self.subTest(reply=reply):
                fit = host({"text": reply, "form": form})["fit"]
                self.assertEqual(fit.get("refused", {}).get("clause"), clause, fit)
        self.assertEqual(host({"text": "delvetalk garden-1 plant\nseed: fern", "form": form})["fit"], {"unclear": {"needs": ["colour"]}})
        self.assertIs(host({"text": "plant: a fern"})["notASpell"]["fielded"], True)
        self.assertIs(host({"text": "just prose"})["notASpell"]["fielded"], False)


PREVIEW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "previews", "gsb-root-menu-v4.txt")


class Margin(unittest.TestCase):
    """A post quoting a card does not cast (the owner's outreach, 2026-10-11: the root menu quoted under a greeting
    was read as `env observe`, entry 147). A spell starts at the margin; an indented one is an example."""

    def test_the_owners_post_quoting_the_root_menu_casts_nothing(self):
        with open(PREVIEW, encoding="utf-8") as handle:
            post = "Hello delve! This is the town I have been building; here is its first card:\n\n" + handle.read()
        out = host({"text": post})
        self.assertNotIn("spell", out)
        self.assertTrue(out["quotation"]["reason"].startswith("This quotes a card (✾ DELVETALK · ROOT)"), out)
        form = fixtures("fit")[0]["form"]
        self.assertEqual(host({"text": post, "form": form})["fit"]["refused"]["clause"], "quotation")

    def test_a_spell_at_the_margin_casts_and_the_same_indented_does_not(self):
        spell = "delvetalk garden plant / seed: x / colour: amber"
        self.assertEqual(show_parsed(host({"text": spell})), "spell garden plant seed=x;colour=amber;")
        for indent in ("  ", "    ", "\t"):
            with self.subTest(indent=repr(indent)):
                self.assertIn("notASpell", host({"text": indent + spell}))
                self.assertIn("notASpell", host({"text": "see:\n" + indent + spell + "\nnice"}))
        # An indented example after a spell's fields neither ends nor replaces it.
        self.assertEqual(show_parsed(host({"text": "delvetalk garden plant\nseed: x\n  delvetalk tide tick\ncolour: amber"})),
                         "spell garden plant seed=x;colour=amber;")

if __name__ == "__main__":
    unittest.main()
