"""The spell grammar: the last unquoted delvetalk line, field lines, slash forms, blocks, fences
skipped, fitted to a form or refused by name. The host parses (op `spell-parse`); world/lib/
Spell.obend keeps only the spell line's card, action and inline fields, which a card reads.

Evidence for FOUNDATION §5 Spell grammar (layer: host; the Bend reading: objects).

    python3 -m unittest tests.test_spell -v
"""
import unittest

from tests.test_host_spell import host, show_fit, show_parsed
from tests.test_objects import check, closure, compile_job, record

# Garden's plant form, as the host's fit takes it.
def plant_form(card="garden-1"):
    return {"card": card, "action": "plant", "fields": [
        {"name": "colour", "kind": {"choice": {"options": ["amber", "violet", "silver"]}}},
        {"name": "seed", "kind": {"text": {"min": 1, "max": 80}}}]}


def text(value):
    return {"tag": "label", "value": value}


def unique(modules):
    seen = set()
    return [m for m in modules if not (m["name"] in seen or seen.add(m["name"]))]


def context(card="garden-1"):
    return record(world=text(""), object=text(card), principal=text("glm"), handle=text(""),
                  caller=text(""), intent=text("probe"), height={"tag": "natural", "value": "0"}, clock={"tag": "natural", "value": "0"},
                  inputOrigin=record(
        kind=text("request"), object=text(""), command=text(""), program=text(""),
        immediatelyPrevious={"tag": "boolean", "value": False}))


def propose(reply, card="garden-1"):
    return show_fit(host({"text": reply, "form": plant_form(card)})["fit"])


def parse(reply):
    return show_parsed(host({"text": reply}))


class Parse(unittest.TestCase):
    def test_the_v1_card_sample_spells_parse_and_become_proposals_with_fields_sorted(self):
        self.assertEqual(parse("delvetalk garden-1 plant\nseed: fern\ncolour: silver\n"),
                         "spell garden-1 plant seed=fern;colour=silver;")
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: fern\ncolour: silver\n"),
                         "proposal garden-1 plant colour=silver;seed=fern;")
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: A fern whose leaves remember\ncolour: amber"),
                         "proposal garden-1 plant colour=amber;seed=A fern whose leaves remember;")

    def test_blank_comment_and_after_the_rule_lines_are_ignored(self):
        reply = "\n# hello\n  delvetalk garden-1 plant  \r\n\nseed:   fern  \r\n# note\ncolour: violet\n---\nnot: a field\nProse here\n"
        self.assertEqual(propose(reply), "proposal garden-1 plant colour=violet;seed=fern;")

    def test_prose_is_not_a_spell(self):
        for prose in ("Could we plant a silver fern whose leaves remember last night's rain?",
                      "", "\n\n# only a comment\n"):
            with self.subTest(prose=prose[:30]):
                self.assertTrue(parse(prose).startswith("not a spell: The reply has no delvetalk line"))
        self.assertTrue(propose("Could we plant a fern?").startswith("refused The reply has no delvetalk line"))

    def test_lines_before_the_spell_are_skipped_so_a_quoted_invitation_may_precede_it(self):
        quoted = ("> ✾ DELVETALK · ROOT\n> \n> GARDEN\n> Plant something.\n> Say: delvetalk is the word\n"
                  "---\nSure!\n\ndelvetalk garden-1 plant\nseed: fern\ncolour: silver\n---\ntrailing prose")
        self.assertEqual(propose(quoted), "proposal garden-1 plant colour=silver;seed=fern;")
        self.assertEqual(propose("Sure!\ndelvetalk garden-1 plant\nseed: fern\ncolour: silver"),
                         "proposal garden-1 plant colour=silver;seed=fern;")
        self.assertEqual(parse("one\ntwo\nthree"), "not a spell: The reply has no delvetalk line.")

    def test_the_one_line_form_takes_comma_separated_fields_after_the_action(self):
        self.assertEqual(parse("delvetalk garden-1 plant seed: fern, colour: silver"),
                         "spell garden-1 plant seed=fern;colour=silver;")
        self.assertEqual(propose("delvetalk garden-1 plant seed: a fern, that remembers, colour: silver"),
                         "proposal garden-1 plant colour=silver;seed=a fern, that remembers;")
        self.assertEqual(propose("Quoted menu\n  delvetalk garden-1 plant  colour: amber ,  seed: moth  \n"),
                         "proposal garden-1 plant colour=amber;seed=moth;")
        self.assertEqual(parse("delvetalk garden-1 plant seed: fern\ncolour: silver"),
                         "spell garden-1 plant seed=fern;colour=silver;")
        self.assertEqual(parse("delvetalk a b x: 1, y: 2, ---"), "spell a b x=1;y=2, ---;")
        self.assertTrue(parse("delvetalk garden-1 plant now").startswith("not a spell: Not a field"))

    def test_malformed_lines_are_not_a_spell(self):
        for bad in ("delvetalk garden-1\nseed: fern", "delvetalk Garden-1 plant", "delvetalk garden-1 plant now"):
            with self.subTest(bad=bad):
                self.assertTrue(parse(bad).startswith("not a spell"), parse(bad))
        # A line that is not a field ends the fields; the spell stands with what came before
        # (prose may follow a spell), and fit names what is missing.
        for prose in ("delvetalk garden-1 plant\nseed fern", "delvetalk garden-1 plant\n: fern"):
            with self.subTest(prose=prose):
                self.assertEqual(parse(prose), "spell garden-1 plant ")
                self.assertEqual(propose(prose), "unclear colour|seed|")
        self.assertEqual(propose("delvetalk garden-1 plant / seed: fern / colour: amber\nthanks, all!\nmore: prose"),
                         "proposal garden-1 plant colour=amber;seed=fern;")

    def test_a_card_name_may_carry_a_did_and_a_path(self):
        self.assertEqual(parse("delvetalk env/did:plc:abc123 seen\nat: 3"), "spell env/did:plc:abc123 seen at=3;")
        self.assertEqual(parse("delvetalk did:web:town.example set\nhandle: glm"), "spell did:web:town.example set handle=glm;")
        self.assertEqual(propose("delvetalk env/did:plc:abc plant\nseed: fern\ncolour: silver", card="env/did:plc:abc"),
                         "proposal env/did:plc:abc plant colour=silver;seed=fern;")
        self.assertEqual(parse("delvetalk garden-1 ?"), "spell garden-1 ? ")

    def test_the_longest_card_name_is_160_bytes(self):
        name = "env/did:plc:" + "a" * 148
        self.assertEqual(parse("delvetalk %s seen" % name), "spell %s seen " % name)
        self.assertTrue(parse("delvetalk %sa seen" % name).startswith("not a spell"))

    def test_only_the_card_name_gains_colon_slash_and_dot(self):
        for bad in ("delvetalk env/DID:plc:x seen", "delvetalk env/did:plc:x? seen", "delvetalk env_did seen",
                    "delvetalk env/did:plc:x se:en", "delvetalk env/x see/n", "delvetalk env/x seen\na.b: 1"):
            with self.subTest(bad=bad):
                self.assertNotEqual(propose(bad, card="env/x").split(" ")[0], "proposal", bad)
        self.assertTrue(parse("delvetalk env/x ??").startswith("not a spell"))

    def test_the_slash_form_separates_fields_and_a_field_line_keeps_its_slashes(self):
        """All five spells in the archive use ` / ` (rehearsal/REPORT.md, finding 1)."""
        self.assertEqual(parse("delvetalk tide subscribe / every: 1 / note: WC-01, first light"),
                         "spell tide subscribe every=1;note=WC-01, first light;")
        self.assertEqual(propose("delvetalk garden-1 plant / colour: amber / seed: a fern"),
                         "proposal garden-1 plant colour=amber;seed=a fern;")
        # A field line holds one field: its value keeps its slashes.
        self.assertEqual(parse("delvetalk garden-1 plant\nseed: a / b fern"), "spell garden-1 plant seed=a / b fern;")
        self.assertEqual(parse("delvetalk a b x: at://did/p/1 / y: 2"), "spell a b x=at://did/p/1;y=2;")
        self.assertEqual(parse("delvetalk a b x: 1/2 / y: and/or"), "spell a b x=1/2;y=and/or;")

    def test_the_last_unquoted_delvetalk_line_is_the_spell(self):
        post = ("e.g. like this:\n    delvetalk garden plant / colour: amber / seed: x\n"
                "> delvetalk wake watch\nso here is mine:\ndelvetalk tide subscribe / every: 1 / note: WC-01")
        self.assertEqual(parse(post), "spell tide subscribe every=1;note=WC-01;")
        self.assertEqual(parse("delvetalk a first\ndelvetalk b second\nx: 1"), "spell b second x=1;")
        # Only quotation: the indented spell is taken; a `>` line never is.
        self.assertEqual(parse("quoted:\n    delvetalk garden-1 plant\n    seed: fern"), "spell garden-1 plant seed=fern;")
        self.assertTrue(parse("> delvetalk garden-1 plant\n> seed: fern").startswith("not a spell"))
        # A malformed last delvetalk line does not hide a real one.
        self.assertEqual(parse("delvetalk a b\nx: 1\ndelvetalk Is The word"), "spell a b x=1;")

    def test_fences_and_quoted_lines_among_the_fields_are_skipped(self):
        post = "```\ndelvetalk garden-1 plant\n```\n```\nseed: fern\n> colour: violet\ncolour: silver\n```"
        self.assertEqual(propose(post), "proposal garden-1 plant colour=silver;seed=fern;")

    def test_a_field_named_as_the_action_fills_the_open_text_field(self):
        """The town writes `plant: a fern` for the seed (the §11 hour)."""
        self.assertEqual(propose("delvetalk garden-1 plant\nplant: a fern\ncolour: silver"), "proposal garden-1 plant colour=silver;seed=a fern;")
        self.assertEqual(propose("delvetalk garden-1 plant\nplant: a fern"), "unclear colour|")
        self.assertEqual(propose("delvetalk garden-1 plant\nplant: a fern\nseed: moss\ncolour: silver"), "refused Unknown field plant")

    def test_a_fence_with_an_info_string_is_code_never_a_spell(self):
        """Rehearsal run 4, finding C: gemini's 3mxhfzx7rlk2f proposes code in a ```bend block that
        opens with `delvetalk forge make` and a --- rule, and plants after it."""
        post = ("a companion card:\n\n```bend\ndelvetalk forge make / name: sentry\n---\nrecord State:\n  n: Nat\n```\n\n"
                "And planting an initial token:\n\ndelvetalk garden-1 plant / colour: silver / seed: an open gate")
        self.assertEqual(propose(post), "proposal garden-1 plant colour=silver;seed=an open gate;")
        self.assertTrue(parse("```json\ndelvetalk garden-1 plant\n```").startswith("not a spell"))
        self.assertEqual(parse("delvetalk a b\nx: 1\n```obend\ny: 2\n```\nz: 3"), "spell a b x=1;z=3;")

    def test_unicode_values_survive(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: 🌙 é “moths” 蛾\ncolour: silver"),
                         "proposal garden-1 plant colour=silver;seed=🌙 é “moths” 蛾;")

    def test_colons_in_a_value_belong_to_the_value(self):
        self.assertEqual(parse("delvetalk a b\nnote: time: 12:30"), "spell a b note=time: 12:30;")


class Blocks(unittest.TestCase):
    """`field: <<DELIM` opens a block ending at a line that is exactly DELIM."""

    def parsed(self, reply):
        return parse(reply)

    def test_a_block_value_is_its_lines_joined_without_a_trailing_newline(self):
        reply = "delvetalk workshop check\nsource: <<BEND\nedition ObjectiveBend 1\n\ndef f(n: Nat) -> Nat:\n  n\nBEND\ntarget: bell-1\n"
        self.assertEqual(self.parsed(reply), "spell workshop check source=edition ObjectiveBend 1\n\ndef f(n: Nat) -> Nat:\n  n;target=bell-1;")
        # A line merely containing the delimiter does not close it; an empty block is "".
        self.assertEqual(self.parsed("delvetalk w c\nnote: <<END_1\nnot END_1 yet\nEND_1\n"), "spell w c note=not END_1 yet;")
        self.assertEqual(self.parsed("delvetalk w c\nnote: <<X\nX"), "spell w c note=;")
        # Not a delimiter (lowercase, or too long): the value is as written.
        self.assertEqual(self.parsed("delvetalk w c\nnote: <<end\nx: y\n"), "spell w c note=<<end;x=y;")

    def test_an_unclosed_block_is_refused_by_name(self):
        self.assertEqual(self.parsed("delvetalk w c\nsource: <<BEND\nline\n"),
                         "not a spell: the block <<BEND for source is never closed by a line BEND")


class Fit(unittest.TestCase):
    def test_a_missing_field_is_unclear_and_named(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: fern"), "unclear colour|")
        self.assertEqual(propose("delvetalk garden-1 plant"), "unclear colour|seed|")

    def test_an_unknown_field_is_refused_by_name(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: fern\ncolour: silver\nsmell: sweet"), "refused Unknown field smell")

    def test_a_refusal_wins_over_a_missing_field(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nsmell: sweet"), "refused Unknown field smell")

    def test_a_choice_outside_the_set_is_refused(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: fern\ncolour: green"), "refused colour is one of: amber, violet, silver")
        self.assertTrue(propose("delvetalk garden-1 plant\nseed: fern\ncolour: Silver").startswith("refused colour"))

    def test_text_bounds_count_scalars(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nseed:\ncolour: silver"), "refused seed takes 1 to 80 characters.")
        ok = "é" * 80
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: %s\ncolour: silver" % ok), "proposal garden-1 plant colour=silver;seed=%s;" % ok)
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: %s\ncolour: silver" % (ok + "é")), "refused seed takes 1 to 80 characters.")

    def test_a_name_outside_the_identifier_alphabet_is_an_unknown_field(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nSeed: fern\ncolour: silver"), "refused Unknown field Seed")
        self.assertEqual(propose("delvetalk garden-1 plant\nsee d: fern\ncolour: silver"), "refused Unknown field see d")

    def test_a_duplicate_field_is_refused(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: a\nseed: b\ncolour: amber"), "refused Duplicate field seed")

    def test_another_card_or_action_is_refused(self):
        self.assertEqual(propose("delvetalk garden-2 plant\nseed: a\ncolour: amber"), "refused This card offers garden-1 plant")
        self.assertEqual(propose("delvetalk garden-1 prune\nseed: a\ncolour: amber"), "refused This card offers garden-1 plant")

    def test_naturals_are_read_in_plain_digits_within_bounds(self):
        form = {"card": "c", "action": "a", "fields": [{"name": "n", "kind": {"natural": {"min": 2, "max": 300}}}]}

        def go(value):
            return show_fit(host({"text": "delvetalk c a\nn: " + value, "form": form})["fit"])
        self.assertEqual(go("42"), "proposal c a n=42;")
        self.assertEqual(go("300"), "proposal c a n=300;")
        self.assertEqual(go("301"), "refused n takes 2 to 300")
        self.assertEqual(go("1"), "refused n takes 2 to 300")
        for bad in ("042", "4 2", "-3", "4.5", "x", "", "9" * 19):
            self.assertEqual(go(bad), "refused n takes a natural number in plain digits.", bad)


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
    compiled = compile_job(unique(closure("Spell")) + [{"name": "Probe", "source": PROBE}], "parse")
    assert compiled["status"] == "compiled", compiled
    out = check({"op": "run", "artifact": compiled["artifact"], "arguments": [text(reply)]})
    assert out["status"] == "finished", out
    return out["value"]["value"]


class BendReading(unittest.TestCase):
    """What a card still reads in Bend: the spell line's card and action (a card answering a
    spell the host found missing fields) and the fields on that line (a macro's expansion)."""

    def test_the_spell_line_and_its_inline_fields_as_the_host_reads_them(self):
        for reply in ("delvetalk garden plant / colour: violet / seed: a bell for moths",
                      "delvetalk tide subscribe / every: 1 / note: WC-01, first light",
                      "delvetalk garden-1 plant seed: a fern, that remembers, colour: silver",
                      "delvetalk a b x: at://did/p/1 / y: 2",
                      "delvetalk garden-1 ?",
                      "Could we plant a fern?",
                      "delvetalk garden-1 plant now",
                      "> delvetalk garden-1 plant / seed: fern",
                      "```json\ndelvetalk garden-1 plant\n```"):
            with self.subTest(reply=reply):
                self.assertEqual(bend_parse(reply), parse(reply))

    def test_the_last_unquoted_line_wins_and_a_quoted_one_only_alone(self):
        post = ("e.g. like this:\n    delvetalk garden plant / colour: amber / seed: x\n"
                "> delvetalk wake watch\nso here is mine:\ndelvetalk tide subscribe / every: 1 / note: WC-01")
        self.assertEqual(bend_parse(post), "spell tide subscribe every=1;note=WC-01;")
        self.assertEqual(bend_parse("delvetalk a first\ndelvetalk b second\nx: 1"), "spell b second ")
        self.assertEqual(bend_parse("quoted:\n    delvetalk garden-1 plant / seed: fern"), "spell garden-1 plant seed=fern;")
        self.assertEqual(bend_parse("delvetalk a b\nx: 1\ndelvetalk Is The word"), "spell a b ")


if __name__ == "__main__":
    unittest.main()
