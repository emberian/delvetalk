"""The host's Lean spell parser (spec/Delvetalk/Host/Spell.lean, op `spell-parse`) agrees with the
Bend grammar (world/lib/Spell.obend) on every input tests/test_spell.py exercises, plus edge inputs.

Evidence for WHOLENESS section 2 (layer: host): the host parses spells: parse, bare and fit, with the refusal
clause names. The Bend parser is the reference; the fixtures are tests/fixtures/spells/*.json.

    python3 -m unittest tests.test_host_spell -v
"""
import json
import os
import unittest

from tests.test_objects import check, closure, compile_job
from tests.test_spell import PROBE, context, text, unique

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "spells")
CLAUSES = {"otherCard", "noAction", "unknownField", "duplicateField", "badValue", "unclosedBlock", "unclear"}

PROBE2 = PROBE + """def natForm() -> Form.Form:
  {card: "c", action: "a", fields: Form.Fields.cons({head: {name: "n", kind: Form.Kind.natural({min: 2n, max: 300n})}, tail: Form.Fields.nil()})}
def natural(text: String) -> String:
  show(Spell.fit(Spell.parse(text), natForm()))
def bare(text: String) -> String:
  bindings(Spell.bare(text))
"""


def fixtures(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as handle:
        return json.load(handle)


def bend(entry, *arguments):
    compiled = compile_job(unique(closure("Spell") + closure("Form") + closure("Abi")) + [{"name": "Probe", "source": PROBE2}], entry)
    assert compiled["status"] == "compiled", compiled
    out = check({"op": "run", "artifact": compiled["artifact"], "arguments": list(arguments), "limits": {"ticks": "1000000"}})
    assert out["status"] == "finished", out
    return out["value"]["value"]


def bend_parse(reply):
    return bend("parse", text(reply))


def bend_fit(reply, form):
    if form["card"] == "c":
        return bend("natural", text(reply))
    return bend("propose", text(reply), context(form["card"]))


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
    for prefix, clause in (("This card offers", "otherCard"), ("Unknown field", "unknownField"),
                           ("Duplicate field", "duplicateField"), ("the block <<", "unclosedBlock")):
        if reason.startswith(prefix):
            return clause
    if "takes" in reason or " is one of: " in reason:
        return "badValue"
    return "noAction"


class Agree(unittest.TestCase):
    def parsed_agrees(self, row, expect=True):
        out = host({"text": row["text"]})
        self.assertEqual(show_parsed(out), bend_parse(row["text"]), row["text"])
        if "notASpell" in out:
            self.assertEqual(out["notASpell"]["fielded"] is True or out["notASpell"]["fielded"] is False, True)
        if expect and "expected" in row:
            self.assertEqual(show_parsed(out), row["expected"], row["text"])
        return out

    def test_parse_fixtures_agree_with_the_bend_parser(self):
        for row in fixtures("parse"):
            with self.subTest(text=row["text"][:60]):
                self.parsed_agrees(row)

    def test_fit_fixtures_agree_with_the_bend_fit(self):
        for row in fixtures("fit") + fixtures("natural"):
            with self.subTest(text=row["text"][:60]):
                self.parsed_agrees(row, expect=False)
                out = host({"text": row["text"], "form": row["form"]})
                shown = show_fit(out["fit"])
                self.assertEqual(shown, bend_fit(row["text"], row["form"]), row["text"])
                if "expected" in row:
                    self.assertEqual(shown, row["expected"], row["text"])

    def test_bare_agrees_with_the_bend_bare(self):
        for row in fixtures("bare") + fixtures("parse"):
            with self.subTest(text=row["text"][:60]):
                out = host({"text": row["text"]})
                self.assertEqual(show_bindings(out["bare"]), bend("bare", text(row["text"])), row["text"])

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
