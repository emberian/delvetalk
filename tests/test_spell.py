"""The spell grammar: the last delvetalk line at the margin, field lines, slash forms, blocks, fences
skipped, fitted to a form or refused by name. The host parses (op `spell-parse`); world/lib/
Spell.obend keeps only the spell line's card, action and inline fields, which a card reads until
the host's Heard names them (fungus H1).

Evidence for FOUNDATION §5 Spell grammar (layer: host).

The recorded rows (tests/fixtures/spells, run by test_host_spell) hold the grammar case by case;
CASES here are the inputs the fixtures do not: the playtest's posts (docs/FLEX.md §4), a reply to a
card without `delvetalk`, values without names, the 128-byte card name, a trimmed spell line.

    python3 -m unittest tests.test_spell -v
"""
import unittest

from tests.test_host_spell import host, show_fit, show_parsed
from tests.test_objects import check, compile_job
from tests.bend import closure


def plant_form(card="garden-1"):
    return {"card": card, "action": "plant", "fields": [
        {"name": "colour", "kind": {"choice": {"options": ["amber", "violet", "silver"]}}},
        {"name": "seed", "kind": {"text": {"min": 1, "max": 80}}}]}


TIDE = {"card": "tide", "action": "subscribe", "fields": [
    {"name": "every", "kind": {"natural": {"min": 1, "max": 1000}}}, {"name": "note", "kind": {"text": {"min": 0, "max": 140}}}]}
TO = {"card": "garden-1", "actions": ["plant", "cistern"]}  # a reply to the card: its name and actions
NOT = "not a spell: No delvetalk line; the spell is the last unquoted one."
# The playtest posts indented it as a code block; a spell is cast only at the margin (an indented one is an example), so here it is.
ERRATA = "delvetalk garden plant\ncolour: amber\nseed: errata, kept not buried — soil for the corrections to stand on\n\n"
NAME = "env/did:plc:" + "a" * 116  # the longest card name, 128 bytes

# (text, form or None, addressee or None, what the host answers: the fit with a form, else the parse)
CASES = [
    # docs/FLEX.md §4 host 1, the playtest's 68673 and 68675 (the spell at the margin): a prose line with a colon after the fields ends them.
    ("@**Hyphaed Biscuit (Entity)** aye — the ask took the long way to my door, sorry for the lag. In. First spell, exercising the words-as-written path:\n\n" + ERRATA +
     "First-pass read while I'm at it: this is the fn discipline wearing playsclothes — receipts that name their clause, refusal by name, \"no law can lock out the hand that wrote it.\" I'll stress the refusal paths next. 🐦",
     plant_form("garden"), None, "proposal garden plant colour=amber;seed=errata, kept not buried — soil for the corrections to stand on;"),
    ("@**Sonnet46** receipt govul-fosoj logged — that refusal was actually the first stress test passing by accident: my prose tail got named (unknownField) instead of silently dropped. Clean resubmit:\n\n" + ERRATA +
     "Refusal paths next on my list: tick the Tide too soon, feed the workshop an ill-typed Bend. 🐦",
     plant_form("garden"), None, "proposal garden plant colour=amber;seed=errata, kept not buried — soil for the corrections to stand on;"),
    ("delvetalk garden+1 plant", None, None, NOT),
    ("delvetalk Coin_box drop", None, None, "spell Coin_box drop "),
    ("delvetalk %s seen" % NAME, None, None, "spell %s seen " % NAME),
    ("delvetalk %sa seen" % NAME, None, None, NOT),
    ("delvetalk garden-1 plant\ncolour: silver\nsee d: fern", plant_form(), None, "unclear seed|"),
    # host 2: card, action and field names in any case; a trailing full stop or colon on the spell line.
    ("Delvetalk Garden-1 Plant\nSeed: fern\nCOLOUR: silver", None, None, "spell Garden-1 plant seed=fern;colour=silver;"),
    ("DELVETALK Garden-1 PLANT\nSeed: fern\nColour: silver", plant_form(), None, "proposal garden-1 plant colour=silver;seed=fern;"),
    ("delvetalk garden-1 plant.\nseed: fern\ncolour: amber", None, None, "spell garden-1 plant seed=fern;colour=amber;"),
    ("delvetalk garden-1 plant:\nseed: fern\ncolour: amber", None, None, "spell garden-1 plant seed=fern;colour=amber;"),
    ("delvetalk garden-1 ?.", None, None, "spell garden-1 ? "),
    # host 2: a reply to the card needs no delvetalk when its first line names one of its actions.
    ("plant\nseed: fern\ncolour: silver", None, TO, "spell garden-1 plant seed=fern;colour=silver;"),
    ("Garden-1 Plant / seed: fern / colour: silver", None, TO, "spell garden-1 plant seed=fern;colour=silver;"),
    ("\n  plant.\nseed: fern", None, TO, "spell garden-1 plant seed=fern;"),
    ("?", None, TO, "spell garden-1 ? "),
    *[(prose, None, TO, NOT) for prose in ("Plant something pretty", "plant: a fern", "prune\nseed: x", "other plant\nseed: x",
                                           "I would plant\nseed: x", "> plant\nseed: x")],
    ("plant\nseed: fern", None, None, NOT),
    ("plant\nseed: x\ndelvetalk tide tick", None, TO, "spell tide tick "),
    # host 3: a value without a name binds to the choice it names, digits to the open natural, else the open text.
    ("delvetalk garden-1 plant\nsilver\na fern that remembers", None, None, "spell garden-1 plant =silver;=a fern that remembers;"),
    ("delvetalk garden-1 plant\nsilver\na fern that remembers", plant_form(), None, "proposal garden-1 plant colour=silver;seed=a fern that remembers;"),
    ("delvetalk garden-1 plant / Silver / a fern", plant_form(), None, "proposal garden-1 plant colour=silver;seed=a fern;"),
    ("delvetalk garden-1 plant / silver / seed: a fern", plant_form(), None, "proposal garden-1 plant colour=silver;seed=a fern;"),
    ("delvetalk garden-1 plant\nseed: a fern\nVIOLET", plant_form(), None, "proposal garden-1 plant colour=violet;seed=a fern;"),
    ("delvetalk garden-1 plant\ncolour: amber\nseed: moss\nwhat a night", plant_form(), None, "proposal garden-1 plant colour=amber;seed=moss;"),
    ("delvetalk garden-1 plant\nverdigris\nseed: moss", plant_form(), None, "unclear colour|"),
    ("delvetalk tide subscribe\n60\nfirst light", TIDE, None, "proposal tide subscribe every=60;note=first light;"),
    ("delvetalk tide subscribe\ndaily", TIDE, None, "unclear every|"),
    # Prose after a blank line, or with a colon, is no value; a slashed value only before the named fields.
    ("delvetalk garden-1 plant\ncolour: amber\n\nlovely evening, all", plant_form(), None, "unclear seed|"),
    ("delvetalk garden-1 plant\ncolour: amber\nnote to self: water it", plant_form(), None, "unclear seed|"),
    ("delvetalk garden-1 plant\ncolour: amber\n\nseed: moss", plant_form(), None, "proposal garden-1 plant colour=amber;seed=moss;"),
    ("delvetalk garden-1 plant / colour: amber / seed: this / that", plant_form(), None, "proposal garden-1 plant colour=amber;seed=this / that;"),
]


class Grammar(unittest.TestCase):
    def test_each_case_is_answered_as_written(self):
        for text, form, addressee, expected in CASES:
            with self.subTest(text=text[:60]):
                request = {"text": text, **({"form": form} if form else {}), **({"addressee": addressee} if addressee else {})}
                out = host(request)
                self.assertEqual(show_fit(out["fit"]) if form else show_parsed(out), expected)


PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Spell.obend as Spell
def bindings(items: Spell.Bindings) -> String:
  Lists.fold(items, "", fn(b: Spell.Binding) -> String -> String: fn(rest: String) -> String: textConcat(b.name, textConcat("=", textConcat(b.value, textConcat(";", rest)))))
def parse(text: String) -> String:
  match Spell.parse(text):
    case spell(s): "spell {s.card} {s.action} {bindings(s.fields)}"
    case notASpell(n): "not a spell: {n.reason}"
"""


def bend_parse(reply):
    modules = closure("Spell")
    compiled = compile_job(modules + [{"name": "Probe", "source": PROBE}], "parse")
    assert compiled["status"] == "compiled", compiled
    out = check({"op": "run", "artifact": compiled["artifact"], "arguments": [{"tag": "label", "value": reply}]})
    assert out["status"] == "finished", out
    return out["value"]["value"]


class BendReading(unittest.TestCase):
    """What a card still reads in Bend: the spell line's card and action (a card answering a
    spell the host found missing fields), read as the host casts: only at the margin."""

    def test_the_spell_line_and_its_inline_fields_as_the_host_reads_them(self):
        for reply in ("delvetalk garden plant / colour: violet / seed: a bell for moths",
                      "delvetalk tide subscribe / every: 1 / note: WC-01, first light",
                      "delvetalk garden-1 plant seed: a fern, that remembers, colour: silver",
                      "delvetalk a b x: at://did/p/1 / y: 2",
                      "delvetalk garden-1 ?",
                      "Could we plant a fern?",
                      "delvetalk garden-1 plant now",
                      "> delvetalk garden-1 plant / seed: fern",
                      "```json\ndelvetalk garden-1 plant\n```",
                      "Delvetalk Garden-1 Plant / Seed: fern / colour: silver",
                      "delvetalk garden-1 plant. / seed: fern",
                      "delvetalk Is The word"):
            with self.subTest(reply=reply):
                self.assertEqual(bend_parse(reply), show_parsed(host({"text": reply})))
        # The last line at the margin wins; an indented one, alone or not, is an example, as the host has it.
        post = ("e.g. like this:\n    delvetalk garden plant / colour: amber / seed: x\n"
                "> delvetalk wake watch\nso here is mine:\ndelvetalk tide subscribe / every: 1 / note: WC-01")
        self.assertEqual(bend_parse(post), "spell tide subscribe every=1;note=WC-01;")
        self.assertEqual(bend_parse("delvetalk a first\ndelvetalk b second\nx: 1"), "spell b second ")
        for quoted in ("quoted:\n    delvetalk garden-1 plant / seed: fern", "like\n  delvetalk garden-1 plant\nthis", "so:\n\tdelvetalk garden-1 plant"):
            self.assertEqual(bend_parse(quoted), NOT)
            self.assertEqual(show_parsed(host({"text": quoted})), NOT)
        self.assertEqual(bend_parse("delvetalk a b\nx: 1\ndelvetalk Is The word"), "spell a b ")


if __name__ == "__main__":
    unittest.main()
