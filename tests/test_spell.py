"""The spell grammar in Bend: parse a card reply, fit it to the card's form.

    python3 -m unittest tests.test_spell -v
"""
import unittest

from tests.test_objects import check, closure, compile_job, record

PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Abi.obend as Abi
import ./Spell.obend as Spell
import ./Form.obend as Form
# Garden's plant form (Garden.planting), written out: these are Spell's tests, and
# Garden's closure leaves no room for a probe this size.
def plantForm(context: Abi.Context) -> Form.Form:
  {card: context.object, action: "plant", fields: Form.Fields.cons({head: {name: "colour", kind: Form.Kind.choice({options: Lists.append::<String>(Lists.append::<String>(Lists.append::<String>(Form.Names.nil(), "amber"), "violet"), "silver")})}, tail: Form.Fields.cons({head: {name: "seed", kind: Form.Kind.text({min: 1n, max: 80n})}, tail: Form.Fields.nil()})})}
def bar(items: Form.Names) -> String:
  Lists.fold::<String, String>(items, "", fn(head: String) -> String -> String: fn(rest: String) -> String: textConcat(head, textConcat("|", rest)))
def value(v: Spell.Value) -> String:
  match v:
    case text(t): t.value
    case natural(n): natText(n.value)
    case choice(c): c.value
def entries(items: Spell.Entries) -> String:
  Lists.fold::<Spell.Entry, String>(items, "", fn(e: Spell.Entry) -> String -> String: fn(rest: String) -> String: textConcat(e.name, textConcat("=", textConcat(value(e.value), textConcat(";", rest)))))
def bindings(items: Spell.Bindings) -> String:
  Lists.fold::<Spell.Binding, String>(items, "", fn(b: Spell.Binding) -> String -> String: fn(rest: String) -> String: textConcat(b.name, textConcat("=", textConcat(b.value, textConcat(";", rest)))))
def showParsed(parsed: Spell.Parsed) -> String:
  match parsed:
    case spell(s): textConcat("spell ", textConcat(s.card, textConcat(" ", textConcat(s.action, textConcat(" ", bindings(s.fields))))))
    case notASpell(n): textConcat("not a spell: ", n.reason)
def parse(text: String) -> String:
  showParsed(Spell.parse(text))
def fieldCount(text: String) -> Nat:
  match Spell.parse(text):
    case spell(s): Lists.length::<Spell.Binding>(s.fields)
    case notASpell(_): 9999n
def show(fit: Spell.Fit) -> String:
  match fit:
    case proposal(p): textConcat("proposal ", textConcat(p.card, textConcat(" ", textConcat(p.action, textConcat(" ", entries(p.bindings))))))
    case unclear(u): textConcat("unclear ", bar(u.needs))
    case refused(r): textConcat("refused ", r.reason)
def propose(text: String, context: Abi.Context) -> String:
  show(Spell.fit(Spell.parse(text), plantForm(context)))
"""


def unique(modules):
    seen = set()
    return [m for m in modules if not (m["name"] in seen or seen.add(m["name"]))]


def text(value):
    return {"tag": "label", "value": value}


def context(card="garden-1"):
    return record(world=text(""), object=text(card), principal=text("glm"), handle=text(""),
                  caller=text(""), intent=text("probe"), height={"tag": "natural", "value": "0"}, clock={"tag": "natural", "value": "0"},
                  inputOrigin=record(
        kind=text("request"), object=text(""), command=text(""), program=text(""),
        immediatelyPrevious={"tag": "boolean", "value": False}))


def run(entry, *arguments, limits=None):
    compiled = compile_job(unique(closure("Spell") + closure("Abi")) + [{"name": "Probe", "source": PROBE}], entry)
    assert compiled["status"] == "compiled", compiled
    request = {"op": "run", "artifact": compiled["artifact"], "arguments": list(arguments)}
    if limits:
        request["limits"] = limits
    return check(request)


def propose(reply, card="garden-1"):
    out = run("propose", text(reply), context(card))
    assert out["status"] == "finished", out
    return out["value"]["value"]


def parse(reply):
    out = run("parse", text(reply))
    assert out["status"] == "finished", out
    return out["value"]["value"]


class Parse(unittest.TestCase):
    def test_the_v1_cards_two_sample_spells(self):
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
        for bad in ("delvetalk garden-1\nseed: fern", "delvetalk Garden-1 plant", "delvetalk garden-1 plant now",
                    "delvetalk garden-1 plant\nseed fern", "delvetalk garden-1 plant\n: fern"):
            with self.subTest(bad=bad):
                self.assertTrue(parse(bad).startswith("not a spell"), parse(bad))

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

    def test_the_slash_form_the_town_writes(self):
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
        post = "```\ndelvetalk garden-1 plant\n```\n```text\nseed: fern\n> colour: violet\ncolour: silver\n```"
        self.assertEqual(propose(post), "proposal garden-1 plant colour=silver;seed=fern;")

    def test_unicode_values_survive(self):
        self.assertEqual(propose("delvetalk garden-1 plant\nseed: 🌙 é “moths” 蛾\ncolour: silver"),
                         "proposal garden-1 plant colour=silver;seed=🌙 é “moths” 蛾;")

    def test_colons_in_a_value_belong_to_the_value(self):
        self.assertEqual(parse("delvetalk a b\nnote: time: 12:30"), "spell a b note=time: 12:30;")


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

    def test_naturals_are_parsed_by_hand_within_bounds(self):
        form = PROBE + """def form() -> Form.Form:
  {card: "c", action: "a", fields: Form.Fields.cons({head: {name: "n", kind: Form.Kind.natural({min: 2n, max: 300n})}, tail: Form.Fields.nil()})}
def natural(text: String) -> String:
  show(Spell.fit(Spell.parse(text), form()))
"""
        compiled = compile_job(unique(closure("Spell") + closure("Abi")) + [{"name": "Probe", "source": form}], "natural")
        self.assertEqual(compiled["status"], "compiled", compiled)

        def go(value):
            out = check({"op": "run", "artifact": compiled["artifact"], "arguments": [text("delvetalk c a\nn: " + value)]})
            return out["value"]["value"]
        self.assertEqual(go("42"), "proposal c a n=42;")
        self.assertEqual(go("300"), "proposal c a n=300;")
        self.assertEqual(go("301"), "refused n takes 2 to 300")
        self.assertEqual(go("1"), "refused n takes 2 to 300")
        for bad in ("042", "4 2", "-3", "4.5", "x", "", "9" * 19):
            self.assertEqual(go(bad), "refused n takes a natural number in plain digits.", bad)


class Maximum(unittest.TestCase):
    """Cost model, measured: take and drop are charged 2 x the bytes of the prefix
    they traverse (an exact bounded scan, no longer 2 x min(size, 4 x scalars)),
    break 2 x (|alphabet| + 2) per visited scalar, plus about 400 ticks of fixed
    work per line. Bytes after a --- rule are never scanned. A 4,096-byte reply
    with 64 fields and a rule parses in about 68,000 ticks; one whose every byte
    is in a field line (4,057 bytes) in about 76,000 (each line is also checked
    for a later spell line, which takes over): both fit the default
    100,000 ticks (the dense one needed 1,000,000 under the 4-bytes-per-scalar
    charge)."""

    def reply(self, value_size, rule=True):
        lines = ["delvetalk garden-1 plant"] + ["f%02d: %s" % (i, "v" * value_size) for i in range(64)]
        body = "\n".join(lines) + "\n"
        if not rule:
            return body
        body += "---\n"
        return body + "#" * (4096 - len(body.encode()))

    def test_a_4096_byte_reply_with_64_fields_parses_under_the_default_budget(self):
        reply = self.reply(44)
        self.assertEqual(len(reply.encode()), 4096)
        out = run("fieldCount", text(reply))
        print("\n  4096 bytes, 64 fields (3.2 KB of them before the rule): parse %s ticks, %s heap cells" %
              (out.get("ticksUsed"), out.get("heapCells")))
        self.assertEqual(out["status"], "finished", out)
        self.assertEqual(out["value"]["value"], "64")
        self.assertLess(out["ticksUsed"], 100000)

    def test_a_dense_4057_byte_reply_fits_the_default_budget(self):
        reply = self.reply(57, rule=False)
        self.assertEqual(len(reply.encode()), 4057)
        default = run("fieldCount", text(reply))
        print("  dense 4057 bytes: default budget %s, %s ticks" % (default["status"], default.get("ticksUsed")))
        self.assertEqual(default["status"], "finished", default)
        self.assertEqual(default["value"]["value"], "64")
        self.assertLess(default["ticksUsed"], 100000)
        starved = run("fieldCount", text(reply), limits={"ticks": "20000"})
        self.assertEqual(starved["status"], "refused", starved)
        self.assertTrue(starved["failure"].endswith("tickExhausted"))

    def test_a_4096_byte_prose_reply_is_cheap(self):
        out = run("parse", text("word " * 819))
        print("  4096 bytes of prose: %s ticks" % out.get("ticksUsed"))
        self.assertEqual(out["status"], "finished", out)


if __name__ == "__main__":
    unittest.main()
