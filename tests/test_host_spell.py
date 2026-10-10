"""The host's spell parser (spec/Delvetalk/Host/Spell.lean, op `spell-parse`) answers every recorded
input as the fixtures say: parse, bare and fit, with the refusal clause names.

Evidence for WHOLENESS section 2 (layer: host): the host parses spells. The fixtures
(tests/fixtures/spells/*.json) were recorded from the Bend grammar, which the host agreed with on
every row before world/lib/Spell.obend's parser was deleted (lane/objects9); the host is the
grammar now, and tests/test_spell.py exercises it case by case.

    python3 -m unittest tests.test_host_spell -v
"""
import json
import os
import unittest

from tests.test_objects import check

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "spells")
CLAUSES = {"otherCard", "noAction", "unknownField", "duplicateField", "badValue", "unclosedBlock", "unclear"}


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


def clause_for(reason):
    for prefix, clause in (("This card answers", "otherCard"), ("No field ", "unknownField"),
                           ("The block <<", "unclosedBlock")):
        if reason.startswith(prefix):
            return clause
    if reason.endswith(" is given twice; keep one."):
        return "duplicateField"
    if "takes" in reason or " is one of: " in reason:
        return "badValue"
    return "noAction"


class Recorded(unittest.TestCase):
    def test_parse_fixtures(self):
        for row in fixtures("parse"):
            with self.subTest(text=row["text"][:60]):
                out = host({"text": row["text"]})
                self.assertEqual(show_parsed(out), row["expected"], row["text"])
                self.assertEqual(show_bindings(out["bare"]), row["bare"], row["text"])
                if "notASpell" in out:
                    self.assertIn(out["notASpell"]["fielded"], (True, False))

    def test_fit_fixtures(self):
        for row in fixtures("fit") + fixtures("natural"):
            with self.subTest(text=row["text"][:60]):
                out = host({"text": row["text"], "form": row["form"]})
                self.assertEqual(show_parsed(out), row["parsed"], row["text"])
                self.assertEqual(show_fit(out["fit"]), row["expected"], row["text"])

    def test_bare_fixtures(self):
        for row in fixtures("bare"):
            with self.subTest(text=row["text"][:60]):
                self.assertEqual(show_bindings(host({"text": row["text"]})["bare"]), row["expected"], row["text"])

    def test_the_fielded_flag_is_whether_some_line_may_be_a_field(self):
        self.assertIs(host({"text": "plant: a fern"})["notASpell"]["fielded"], True)
        self.assertIs(host({"text": "just prose"})["notASpell"]["fielded"], False)


class Clauses(unittest.TestCase):
    def clause(self, reply, form=None):
        fit = host({"text": reply, "form": form or fixtures("fit")[0]["form"]})["fit"]
        self.assertIn("refused", fit, fit)
        self.assertIn(fit["refused"]["clause"], CLAUSES)
        return fit["refused"]["clause"]

    def test_every_refusal_names_its_clause(self):
        for row in fixtures("fit") + fixtures("natural"):
            with self.subTest(text=row["text"][:60]):
                fit = host({"text": row["text"], "form": row["form"]})["fit"]
                if "refused" in fit:
                    self.assertEqual(fit["refused"]["clause"], clause_for(fit["refused"]["reason"]))

    def test_the_clauses_by_case(self):
        self.assertEqual(self.clause("delvetalk garden-2 plant"), "otherCard")
        self.assertEqual(self.clause("delvetalk garden-1 prune"), "otherCard")
        self.assertEqual(self.clause("prose"), "noAction")
        self.assertEqual(self.clause("delvetalk garden-1 plant now"), "noAction")
        self.assertEqual(self.clause("delvetalk garden-1 plant\nsmell: x"), "unknownField")
        self.assertEqual(self.clause("delvetalk garden-1 plant\nseed: a\nseed: b"), "duplicateField")
        self.assertEqual(self.clause("delvetalk garden-1 plant\ncolour: green"), "badValue")
        self.assertEqual(self.clause("delvetalk garden-1 plant\nseed: <<S\nx"), "unclosedBlock")

    def test_unclear_is_a_fit_with_needs(self):
        fit = host({"text": "delvetalk garden-1 plant\nseed: fern", "form": fixtures("fit")[0]["form"]})["fit"]
        self.assertEqual(fit, {"unclear": {"needs": ["colour"]}})

    def test_the_answer_shape(self):
        out = host({"text": "delvetalk garden-1 plant\nseed: fern\ncolour: silver", "form": fixtures("fit")[0]["form"]})
        self.assertEqual(out["spell"], {"card": "garden-1", "action": "plant", "fields": [
            {"name": "seed", "value": "fern"}, {"name": "colour", "value": "silver"}]})
        self.assertEqual(out["fit"]["proposal"]["bindings"], [
            {"name": "colour", "value": {"choice": "silver"}}, {"name": "seed", "value": {"text": "fern"}}])
        self.assertEqual(out["bare"], [{"name": "seed", "value": "fern"}, {"name": "colour", "value": "silver"}])
        nat = fixtures("natural")[0]
        out = host({"text": nat["text"], "form": nat["form"]})
        self.assertEqual(out["fit"]["proposal"]["bindings"], [{"name": "n", "value": {"natural": 42}}])


if __name__ == "__main__":
    unittest.main()
