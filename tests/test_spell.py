"""The spell grammar: the last delvetalk line at the margin, field lines, slash forms, blocks, fences
skipped, fitted to a form or refused by name. The host alone parses (op `spell-parse`); a card's
receive is handed the spell it read (`Card.Cast`), and Bend reads no spell itself (fungus H1).

Evidence for FOUNDATION §5 Spell grammar (layer: host).

The recorded rows (tests/fixtures/spells, run by test_host_spell) hold the grammar case by case;
CASES here are the inputs the fixtures do not: the playtest's posts (docs/FLEX.md §3), a reply to a
card without `delvetalk`, values without names, the 128-byte card name, a trimmed spell line, an at:// URI inline.

    python3 -m unittest tests.test_spell -v
"""
import unittest

from tests.test_host_spell import host, show_fit, show_parsed


def plant_form(card="garden-1"):
    return {"card": card, "action": "plant", "fields": [
        {"name": "colour", "kind": {"choice": {"options": ["amber", "violet", "silver"]}}},
        {"name": "seed", "kind": {"text": {"min": 1, "max": 80}}}]}


CHIME = {"card": "chime", "action": "set", "fields": [
    {"name": "every", "kind": {"natural": {"min": 1, "max": 1000}}}, {"name": "note", "kind": {"text": {"min": 0, "max": 140}}}]}
TO = {"card": "garden-1", "actions": ["plant", "cistern"]}  # a reply to the card: its name and actions
NOT = "not a spell: No delvetalk line; the spell is the last unquoted one."
# The playtest posts indented it as a code block; a spell is cast only at the margin (an indented one is an example), so here it is.
ERRATA = "delvetalk garden plant\ncolour: amber\nseed: errata, kept not buried — soil for the corrections to stand on\n\n"
NAME = "did:plc:" + "a" * 120  # the longest card name, 128 bytes

# (text, form or None, addressee or None, what the host answers: the fit with a form, else the parse)
CASES = [
    # docs/FLEX.md §3, the playtest's 68673 and 68675 (the spell at the margin): a prose line with a colon after the fields ends them.
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
    ("delvetalk chime set\n60\nfirst light", CHIME, None, "proposal chime set every=60;note=first light;"),
    ("delvetalk chime set\ndaily", CHIME, None, "unclear every|"),
    # Prose after a blank line, or with a colon, is no value; a slashed value only before the named fields.
    ("delvetalk garden-1 plant\ncolour: amber\n\nlovely evening, all", plant_form(), None, "unclear seed|"),
    ("delvetalk garden-1 plant\ncolour: amber\nnote to self: water it", plant_form(), None, "unclear seed|"),
    ("delvetalk garden-1 plant\ncolour: amber\n\nseed: moss", plant_form(), None, "proposal garden-1 plant colour=amber;seed=moss;"),
    ("delvetalk garden-1 plant / colour: amber / seed: this / that", plant_form(), None, "proposal garden-1 plant colour=amber;seed=this / that;"),
    # An at:// URI in a slashed value is whole: its second `/` follows a `/`, not a blank, so `did:` is no field there.
    ("delvetalk register ask / anchor: at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpsppufbr2f / text: q", None, None,
     "spell register ask anchor=at://did:plc:7h7e6qfkhvoqgfwh7uloqok2/town.delve.feed.post/3mxpsppufbr2f;text=q;"),
    ("delvetalk register voice / on: 1 / anchor: at://did:web:gsb.example/town.delve.feed.post/3mx b / text: x //y: z", None, None,
     "spell register voice on=1;anchor=at://did:web:gsb.example/town.delve.feed.post/3mx b;text=x //y: z;"),
]


class Grammar(unittest.TestCase):
    def test_each_case_is_answered_as_written(self):
        for text, form, addressee, expected in CASES:
            with self.subTest(text=text[:60]):
                request = {"text": text, **({"form": form} if form else {}), **({"addressee": addressee} if addressee else {})}
                out = host(request)
                self.assertEqual(show_fit(out["fit"]) if form else show_parsed(out), expected)


if __name__ == "__main__":
    unittest.main()
