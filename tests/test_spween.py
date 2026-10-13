"""A spween scene parses to a Scene's seed and is made by posting one; guards, effects, END and the
cooldown law hold.

Evidence for FOUNDATION §8 (layer: objects).

spween scenes lowered to a Scene's seed (world/lib/Spween.obend), and made by posting one.

Spween.parse reads frontmatter (id, title, cooldown, requires), `=== passage`s, prose,
`* [label]` choices with `{ condition }` or `when condition` guards, `~ k = v` / `+=` / `-=`
effects and `-> target` (END ends); it refuses `weight`, `~ call` and `has:` by name. A
```spween block posted to a Scene makes a new scene at <scene>/<id>; its choices are
guarded, their effects applied in order, END leaves, and the cooldown is a law clause over
context.clock (refused by name in Bend first, by the law for a forged write).

Refuted by: the README's tavern parsing when it names a weight, or not parsing without it; a
call, a has: or an effect outside a choice parsing; a guarded choice taken; END not leaving;
a reader re-entering inside the cooldown, by spell or by a forged write; or not after it.
"""
import unittest

from tests import test_chain, test_scenarios
from tests.test_objects import run_pure
from tests.test_scene import GATE, GLM, KIM, heard, plain, scene_fields
from tests.test_rooms import body as room_body, make_room
from tests.wire import cast_refusal, label, nat, record

# The README's running example, verbatim.
TAVERN = """---
id: tavern_encounter
title: The Mysterious Stranger
weight: 10
---

=== intro

A hooded figure sits alone in the corner of the tavern.

* [Approach them] { courage >= 5 }
  ~ courage -= 1
  -> conversation

* [Order a drink instead]
  ~ gold -= 2
  -> END

=== conversation

"I've been expecting you," they whisper.

* [Ask about the quest]
  ~ quest_started = true
  -> END
"""

WELL = """---
id: wishing_well
title: The Wishing Well
cooldown: 3
tags: [town, small]
requires:
  not: [well_sealed]
---

=== intro

A mossy well hums under the square.
Coins glint far below.

* [Drop a coin] { !wished }
  ~ coins += 2
  ~ wished = true
  -> deeper

* [Walk on]
  -> END

=== deeper

// The water remembers who wished.
The water answers with a low bell.

* [Make a wish] when coins >= 2
  ~ coins -= 1
  ~ wish = "a quiet harbour"
  -> END

* [Climb down] { coins >= 5 }
  -> intro
-> intro
"""

PROBE = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./Scenes.obend as Scenes
import ./Spween.obend as Spween
def test(t: Scenes.Test) -> String:
  match t:
    case truthy(_): "truthy"
    case falsy(_): "falsy"
    case law(_): "law"
    case holding(_): "holding"
    case lacking(_): "lacking"
    case _: Scenes.symbol(t)
def op(o: Scenes.Op) -> String:
  match o:
    case set(_): "set"
    case add(_): "add"
    case sub(_): "sub"
    case cast(_): "cast"
def clauses(guard: Scenes.Guard) -> String:
  textJoin(Lists.map(guard, fn(c: Scenes.Clause) -> String: "{c.key} {test(c.test)} {c.value}"), ", ")
def effects(list: Lists.List<Scenes.Effect>) -> String:
  textJoin(Lists.map(list, fn(e: Scenes.Effect) -> String: "{e.key} {op(e.op)} {e.value}"), "; ")
def said(text: String) -> String:
  if text == "" then "" else " / {text}"
def weighed(w: Scenes.Weighed) -> String:
  "{w.value} {natText(w.weight)}"
def among(ws: Lists.List<Scenes.Weighed>) -> String:
  match ws:
    case nil(_): ""
    case cons(_): " among {textJoin(Lists.map(ws, weighed), \\", \\")}"
def choice(c: Scenes.Choice) -> String:
  "  * {c.label} [{clauses(c.guard)}] ({effects(c.effects)}) -> {c.to}{among(c.among)}{said(c.text)}"
def passageGuard(p: Scenes.Passage) -> String:
  match p.guard:
    case nil(_): ""
    case cons(_): " [{clauses(p.guard)}]"
def passage(p: Scenes.Passage) -> String:
  "=== {p.id}{passageGuard(p)}: {p.text}\\n{textJoin(Lists.map(p.choices, choice), \\"\\\\n\\")}"
def rules(text: String) -> String:
  match Spween.parse(text):
    case refused(r): "refused: {r.reason}"
    case parsed(p): Scenes.ruleText(p.seed.passages)
def summary(text: String) -> String:
  match Spween.parse(text):
    case refused(r): "refused: {r.reason}"
    case parsed(p): "{p.id} / {p.seed.title} / start {p.seed.start} / cooldown {natText(p.seed.cooldown)} / requires {clauses(p.seed.requires)}\\n{textJoin(Lists.map(p.seed.passages, passage), \\"\\\\n\\")}"
def vars() -> Scenes.Vars:
  Scenes.readerVars(Lists.append(Lists.append(Lists.List.nil({}), {name: "cups", value: "2"}), {name: "wound", value: "12"}), Lists.append(Lists.List.nil({}), {name: "wound", value: "1"}))
def render(text: String) -> String:
  Spween.rendered(text, vars(), 0n)
def drawnWith(text: String, n: Nat) -> String:
  Spween.rendered(text, vars(), n)
def hashed(text: String) -> Nat:
  Scenes.hashed(text)
def pick(n: Nat) -> String:
  Scenes.drawn(Lists.append(Lists.append(Lists.List.nil({}), {value: "a", weight: 1n}), {value: "b", weight: 3n}), n)
def wing(text: String) -> String:
  match Spween.wing(text):
    case refused(r): "refused: {r.reason}"
    case parsed(p): "{textJoin(Lists.map(p.seed.passages, passage), \\"\\\\n\\")}\\nwaiting: {textJoin(Spween.waiting(p.seed.passages), \\", \\")}"
"""


def summary(text, what="summary", *more):
    out = run_pure("Spween", what, label(text), *more, probe=PROBE, limits={"ticks": "1000000"})
    assert out["status"] == "finished", out
    return out["value"]["value"], out["ticksUsed"]


# Scenes.hashed, written again: FNV-1a over printable ASCII (any other character counts as 95), modulo 2^32 - 5.
PRINTABLE = "".join(chr(c) for c in range(32, 127))


def hashed(text):
    h = 2166136261
    for ch in text:
        h = (h * 16777619 + (PRINTABLE.index(ch) if ch in PRINTABLE else 95) + 1) % 4294967291
    return h


def drawn(alternatives, n):
    """Scenes.drawn: (value, weight) pairs, the one n modulo the total lands in."""
    r = n % sum(w for _, w in alternatives)
    for value, weight in alternatives:
        if r < weight:
            return value
        r -= weight


def turn_draw(reply):
    """The draw a turn makes (Scenes.turnDraw), from its receipt: the height it read (its entry's, less one), its
    principal and its intent."""
    receipt = reply["receipt"]
    return hashed("%d %s %s" % (receipt["height"] - 1, receipt["identity"]["principal"], receipt["identity"]["intent"]))


# The braid, as a resident types it (docs/OVERHAUL.md section 2): guards that read the outside (a thing's field, a
# count, another thing's want, what the reader keeps), effects that cast a spell or call the room's own verb.
ROPE = """---
id: bell_rope
title: The Bell Rope
---
=== rope
A rope hangs out of the dark over the porch. Somewhere above, mimo's bell.
* [Pull the rope] { !pulled }
  ~ pulled = true
  ~ cast delvetalk bell/1 ring
  -> rung
* [Ask after the goblet] { keeps.porch/goblet }
  -> goblet
* [Wait for company] { count(new.presence) >= 2 }
  -> rung
* [Leave a line for whoever pulled] when "bell/1".tended >= 0, !"bell/1" wants rain
  ~ cast delvetalk me note / text: {request.subject} came by the rope
  -> END
=== rung
The bell has said what it had. The rope still sways.
* [Sing back]
  ~ call("song", "low", "the porch")
  -> END
=== goblet
The goblet's keeper is the only one the rope tells about it.
* [Go]
"""


class Parse(unittest.TestCase):
    def test_refusals_name_the_missing_piece_with_the_line_to_add_and_prose_alone_is_a_scene(self):
        body = "---\nid: s\n---\n=== a\nText.\n* [Go]\n  %s\n  -> END\n"
        long = "---\nid: s\n---\n=== a\n%s\n* [Go]\n  -> END\n"
        for text, refusal in ((TAVERN, "refused: weight: a scene is entered by name here, never drawn; weight weighs a draw inside one"),
                              ("---\nid: s\n---\n=== a\n* [Go] { inventory.sword }\n  -> END\n",
                               "refused: inventory.sword: a room reads what the reader keeps or holds as keeps.<thing>, holds.<thing> or has.<thing>"),
                              ("---\nid: s\nrequires:\n  has: [inventory.sword]\n---\n=== a\n", "refused: inventory.sword: a room reads"),
                              ("---\nid: s\n---\n=== a\n~ gold += 1\n",
                               "refused: an effect outside a choice: ~ gold += 1; put it, indented, under the * [choice] that leads here"),
                              (body % "~ cast ring the bell", "refused: ~ cast takes a spell, as a rule's then does: ~ cast delvetalk bell/1 ring"),
                              ("---\nid: s\n---\n=== 1a\n", "refused: a passage name is letters, digits and _, starting with a letter: 1a"),
                              ("---\nid: s\n---\n=== a\n* [Go]\n  -> nowhere\n", "refused: -> nowhere: no passage of that name; add === nowhere, or point it at one that is"),
                              ("---\nid: s\n=== a\n", "refused: the frontmatter has no closing ---; add --- on the line after its last field"),
                              ("---\nid: s\n---\nThe door.\n=== a\n", "refused: text before the first passage: The door.; a scene needs === start; add it above your prose"),
                              ("The door.\n* [Knock]\n", "refused: a scene needs === start; add it above your prose"),
                              ("=== a\n* Knock\n", "refused: a choice is * [Label], its words in brackets: * Knock"),
                              # Frontmatter is optional; prose alone is a scene of one passage, its first line the title.
                              ("=== a\nText.\n", " / Text. / start a / cooldown 0 / requires \n=== a: Text."),
                              ("A well hums under the square.\nCoins glint.\n", " / A well hums under the square. / start start / cooldown 0 / requires \n=== start: A well hums under the square.\nCoins glint."),
                              (long % ("x" * 601), "refused: a passage holds at most 600 characters"),
                              (long % ("x" * 600), "s / s")):
            with self.subTest(refusal=refusal):
                self.assertTrue(summary(text)[0].startswith(refusal), summary(text)[0])

    def test_a_guard_reads_the_inside_the_reader_s_things_and_any_condition_of_the_law_s_grammar(self):
        text, _ = summary(ROPE)
        self.assertIn("  * Pull the rope [pulled falsy ] (pulled set true;  cast delvetalk bell/1 ring) -> rung", text)
        self.assertIn("  * Ask after the goblet [keeps holding porch/goblet] () -> goblet", text)
        self.assertIn("  * Wait for company [ law count(new.presence) >= 2] () -> rung", text)
        # Commas split at the top only; `!` before a condition is `not`.
        self.assertIn('  * Leave a line for whoever pulled [ law "bell/1".tended >= 0,  law not ("bell/1" wants rain)] '
                      '( cast delvetalk me note / text: {request.subject} came by the rope) -> END', text)
        # spween's `~ call("song", ...)`, as `~ song low the porch`: the room's own verb, on itself.
        self.assertIn("  * Sing back [] ( cast delvetalk {request.object} song / text: low the porch) -> END", text)
        self.assertIn("[ law request.subject in [1, 2]]", summary("---\nid: s\n---\n=== a\n* [Go] { request.subject in [1, 2] }\n")[0])

    def test_each_cast_is_a_rule_of_the_room_s_text_named_by_passage_and_choice(self):
        self.assertEqual(summary(ROPE, "rules")[0],
                         '\nrule rope_1 "Pull the rope": request.method == "choose" and new.chose == "rope.1" then delvetalk bell/1 ring'
                         '\nrule rope_4 "Leave a line for whoever pulled": request.method == "choose" and new.chose == "rope.4" then delvetalk me note / text: {request.subject} came by the rope'
                         '\nrule rung_1 "Sing back": request.method == "choose" and new.chose == "rung.1" then delvetalk {request.object} song / text: low the porch')
        two = '---\nid: s\n---\n=== a\n* [Ring "twice"]\n  ~ cast delvetalk bell/1 ring\n  ~ fanfare\n'
        self.assertEqual(summary(two, "rules")[0],
                         '\nrule a_1 "Ring \'twice\'": request.method == "choose" and new.chose == "a.1" then delvetalk bell/1 ring'
                         '\nrule a_1b "Ring \'twice\'": request.method == "choose" and new.chose == "a.1" then delvetalk {request.object} fanfare')
        many = "---\nid: s\n---\n" + "".join("=== p%d\n" % p + "".join("* [C%d]\n  ~ cast delvetalk bell/%d ring\n" % (i, p * 8 + i) for i in range(8)) for p in range(2))
        self.assertTrue(summary(many)[0].startswith("refused: a scene casts at most fifteen spells"), summary(many)[0][:120])
        # One spell cast by several choices is one rule naming each (fluonaut's touch and glm's step both ring bell/1).
        same = "=== a\n* [Ring]\n  ~ cast delvetalk bell/1 ring\n  -> b\n=== b\n' [Touch]\n  ~ cast delvetalk bell/1 ring\n' [Ring again]\n  ~ cast delvetalk bell/1 ring\n"
        self.assertEqual(summary(same, "rules")[0],
                         '\nrule a_1 "Ring": request.method == "choose" and (new.chose == "a.1" or new.chose == "b.1" or new.chose == "b.2") then delvetalk bell/1 ring')

    def test_a_quote_and_a_space_before_the_bracket_is_a_choice_as_a_star_is(self):
        # fluonaut's `' [戻る] -> forecourt`; a line of prose that opens on a quote stays prose
        text, _ = summary("=== a\n'Twas cold.\n' [触れる氷] { cups >= 1 }\n  ~ cups -= 1\n  -> a\n' [戻る] -> a\n")
        self.assertEqual(text, " / 'Twas cold. / start a / cooldown 0 / requires \n=== a: 'Twas cold.\n  * 触れる氷 [cups >= 1] (cups sub 1) -> a\n  * 戻る [] () -> a")


    def test_fluonaut_s_japanese_passage_parses_with_its_russian_word_and_labels_as_written(self):
        # post 33 of the station trawl, its choices on their own lines
        text, _ = summary("---\nid: s\ntitle: 冷蔵庫\n---\n=== forecourt\n外。\n=== hallway\n廊下。\n=== cooler_back\n冷蔵庫の奥で、«чашка» が光る。\n"
                          "' [触れる氷] { cups >= 1 }\n  ~ cups -= 1\n  -> hallway\n' [戻る] -> forecourt\n")
        self.assertIn(" / 冷蔵庫 / start forecourt", text)
        self.assertIn("=== cooler_back: 冷蔵庫の奥で、«чашка» が光る。\n  * 触れる氷 [cups >= 1] (cups sub 1) -> hallway\n  * 戻る [] () -> forecourt", text)

    def test_prose_in_arabic_chinese_and_spanish_passes_through_unchanged(self):
        for prose in ("مرحبا بالعالم، „ein“ «bonjour»", "井边有一枚「硬币」。", "¿Qué pasó, señor? “Nada”."):
            with self.subTest(prose=prose):
                self.assertIn("=== a: %s\n" % prose, summary("=== a\n%s\n* [Go]\n" % prose)[0] + "\n")

    def test_variables_in_one_alphabet_set_add_subtract_and_guard(self):
        text, _ = summary("=== a\nA.\n* [取る] { 杯 >= 1, !鳴った, чашки < 3, 杯_2 }\n  ~ 杯 -= 1\n  ~ 杯 = 2\n  ~ чашки += 1\n  ~ 鳴った = true\n  -> a\n")
        self.assertIn("  * 取る [杯 >= 1, 鳴った falsy , чашки < 3, 杯_2 truthy ] (杯 sub 1; 杯 set 2; чашки add 1; 鳴った set true) -> a", text)
        flags = summary("---\nid: s\nrequires:\n  min: { 杯: 1 }\n  not: [鳴った]\n---\n=== a\n")[0]
        self.assertIn("requires 杯 >= 1, 鳴った falsy ", flags)

    def test_the_reader_s_own_variables_are_written_my_and_read_and_set_as_the_room_s(self):
        text, _ = summary("---\nid: s\nrequires:\n  min: { my.visits: 0 }\n---\n=== a\nA.\n* [Wind] { my.wound < 12, !my.gone, wound >= 0, my.杯 }\n  ~ wound += 1\n  ~ my.wound += 1\n  ~ my.杯 = 2\n  -> a\n")
        self.assertIn("requires my.visits >= 0", text)
        self.assertIn("  * Wind [my.wound < 12, my.gone falsy , wound >= 0, my.杯 truthy ] (wound add 1; my.wound add 1; my.杯 set 2) -> a", text)
        self.assertEqual(summary("=== a\n* [Go] { my.\u0441ups >= 1 }\n")[0], "refused: not a variable: my.\u0441ups; a name is in one alphabet, ASCII letters or none")
        self.assertTrue(summary("=== a\n* [Go]\n  ~ my. = 1\n")[0].startswith("refused: an effect sets a variable"), summary("=== a\n* [Go]\n  ~ my. = 1\n")[0])

    def test_a_kind_s_body_is_read_as_a_layer_from_its_first_characters(self):
        # `kinds make` reads the room's body (forty thousand characters) several times a turn: Forms.whole must not
        # measure it, or the room kind outgrows the turn's ticks.
        body = room_body("room")
        probe = "edition ObjectiveBend 1\nimport ./Forms.obend as Forms\ndef lay(text: String) -> Bool:\n  textTake(Forms.layer(text), 10n) == \"layer over\"\n"
        out = run_pure("Forms", "lay", label(body + "\n# " + "x" * 20000 + "\n"), probe=probe, limits={"ticks": "1000000"})
        self.assertEqual((out["status"], out["value"]["value"]), ("finished", True), out)
        self.assertLess(out["ticksUsed"], 1000, out)

    def test_text_reads_the_variables_at_reading_and_a_brace_the_grammar_cannot_read_is_refused(self):
        # deepseek's map that the passage still described after `Wipe the map away` (station trawl §7)
        coldroom = "=== a\nThe far wall is {wiped: bare frost | a map of town}. {cups} cups; you wound it {my.wound}.\n* [Wipe] { !wiped }\n  ~ wiped = true\n  {cups >= 1: Your sleeve comes away cold.}\n  -> a\n"
        self.assertIn("=== a: The far wall is {wiped: bare frost | a map of town}. {cups} cups", summary(coldroom)[0])
        for text, shown in (("{cups} cups; {wound} windings, {my.wound} yours.", "2 cups; 12 windings, 1 yours."),
                            ("{ wound >= 12: the hand is gone | the hand points nowhere }.", "the hand is gone."),
                            ("{ my.wound >= 12: the hand is gone | the hand points nowhere }.", "the hand points nowhere."),
                            ("{!wiped: a map {cups >= 2: of {cups} towns | of one}}{wiped: bare}", "a map of 2 towns"),
                            ("{gone}|{my.gone}| {wiped: x}|", "|| |"),  # never set reads as nothing
                            ("a { lone brace", "a { lone brace"), ("{1a b}", "{1a b}")):  # a carried room's text as written
            with self.subTest(text=text):
                self.assertEqual(summary(text, "render")[0], shown)
        for text, refusal in (("=== a\nThe { door.\n", "refused: { door.: a { opens text read at reading; close it with }"),
                              ("=== a\n{1a b}\n", "refused: {1a b}: in braces goes a variable ({cups}, {my.cups}), a guard and its text ({ cups >= 1: … | … }) or a draw ({~ … | … })"),
                              ('=== a\n{ "bell/1".tended >= 1: rung }\n', 'refused: { "bell/1".tended >= 1: rung }: text reads the room\'s variables and yours (my.), not the town\'s'),
                              ("=== a\n{ cups: one | two | three }\n", "refused: { cups: one | two | three }: a guard's text is one, or two after |"),
                              ("=== a\n{ cups: one {a b} }\n", "refused: {a b}: in braces goes"),
                              ("=== a\nA.\n* [Go]\n  {cups\n", "refused: {cups: a { opens text read at reading")):
            with self.subTest(text=text):
                self.assertTrue(summary(text)[0].startswith(refusal), summary(text)[0])

    def test_a_draw_is_weighed_as_spween_weighs_and_hashed_from_what_the_journal_holds(self):
        # two or more -> under a choice draw one; spween's weight, 10 where none is written
        text, _ = summary("=== a\nA.\n* [Pick up the phone]\n  -> b weight: 3\n  -> c\n  -> END weight: 1\n* [Go] -> b\n=== b { cups >= 1 }\nB.\n=== c\nC.\n")
        self.assertIn("  * Pick up the phone [] () -> b among b 3, c 10, END 1\n  * Go [] () -> b\n", text)
        self.assertIn("=== b [cups >= 1]: B.", text)
        self.assertEqual(summary("=== a\n* [Go]\n  -> a weight: 0\n  -> b weight: 0\n=== b\n")[0], "refused: a choice's draw has weights that add to nothing")
        self.assertEqual(summary("=== a\n* [Go]\n  -> a\n  -> nowhere\n")[0], "refused: -> nowhere: no passage of that name; add === nowhere, or point it at one that is")
        self.assertTrue(summary("=== a\n{~ a weight: 0 | b weight: 0 }\n")[0].startswith("refused: {~ a weight: 0 | b weight: 0 }: a draw's weights add to nothing"))
        # the hash and the weighed pick, against this file's own reckoning of them
        for text in ("", "12 did:plc:glm t3", "井戸 «чашка»"):
            self.assertEqual(int(summary(text, "hashed")[0]), hashed(text), text)
        self.assertEqual([run_pure("Spween", "pick", nat(n), probe=PROBE)["value"]["value"] for n in range(6)],
                         [drawn([("a", 1), ("b", 3)], n) for n in range(6)])
        # a text's draws: each brace its own, by weight, the same for the same draw
        text = "{~ the trucker | the regular weight: 3 | static weight: 0 }, then {~ rain | snow}."
        seen = set()
        for n in (0, 1, 2, 7, 99, 4294967290):
            got = summary(text, "drawnWith", nat(n))[0]
            self.assertEqual(got, summary(text, "drawnWith", nat(n))[0])
            first = drawn([("the trucker", 10), ("the regular", 3), ("static", 0)], hashed("%d 0" % n))
            second = drawn([("rain", 10), ("snow", 10)], hashed("%d 1" % n))
            self.assertEqual(got, "%s, then %s." % (first, second), n)
            seen.add(got)
        self.assertGreater(len(seen), 1)

    def test_a_verb_stays_ascii_and_a_cast_is_read_as_before(self):
        text, _ = summary("=== a\n* [Go]\n  ~ ring bell/1\n  ~ call(\"ring\", \"bell/1\")\n")
        self.assertEqual(text.count("cast delvetalk {request.object} ring / text: bell/1"), 2, text)
        self.assertTrue(summary("=== a\n* [Go]\n  ~ 鳴らす bell/1\n")[0].startswith("refused: an effect sets a variable"), summary("=== a\n* [Go]\n  ~ 鳴らす bell/1\n")[0])

    def test_a_name_in_two_alphabets_is_refused_by_name_wherever_a_variable_is_written(self):
        mixed = "\u0441ups"  # a Cyrillic es before Latin ups
        reason = "refused: not a variable: %s; a name is in one alphabet, ASCII letters or none" % mixed
        for text in ("=== a\n* [Go] { %s >= 1 }\n" % mixed, "=== a\n* [Go] { !%s }\n" % mixed, "=== a\n* [Go]\n  ~ %s -= 1\n" % mixed,
                     "=== a\n* [Go]\n  ~ %s = 1\n" % mixed, "---\nid: s\nrequires:\n  flags: [%s]\n---\n=== a\n" % mixed):
            with self.subTest(text=text):
                self.assertEqual(summary(text)[0], reason)
        for name in ("杯　2", "杯、", "a$b", "杯“x"):  # an ideographic space, a CJK mark, ASCII punctuation, a quotation mark are not in a name
            with self.subTest(name=name):
                self.assertTrue(summary("=== a\n* [Go]\n  ~ %s = 1\n" % name)[0].startswith("refused: "), name)

    def test_a_passage_name_outside_ascii_is_refused_with_the_name_to_write_instead(self):
        self.assertEqual(summary("=== 冷蔵庫の奥\nA.\n")[0],
                         "refused: a passage name is ASCII letters, digits and _, as it names a rule of the room's law: 冷蔵庫の奥; "
                         "write === cooler_back, and keep the words as the title or a choice's label")
        self.assertTrue(summary("---\nid: 井戸\n---\n=== a\n")[0].startswith("refused: the frontmatter's id is letters, digits and _"))

    def test_a_passage_keeps_its_guard_apart_from_incoming_choices_and_requires(self):
        # deepseek's `=== twelfth { wound >= 12 }` and grok's `=== radio { cups >= 1 }`, under the station's call
        gated = "---\nid: s\n---\n=== a\nA.\n* [In] { cups >= 1 } -> b\n-> b\n=== b { wound >= 12, keeps.porch/goblet }\nB.\n* [Back] -> a\n"
        text, _ = summary(gated)
        self.assertIn("  * In [cups >= 1] () -> b", text)
        self.assertIn("  * Continue [] () -> b", text)
        self.assertIn("=== b [wound >= 12, keeps holding porch/goblet]: B.\n  * Back [] () -> a", text)
        self.assertTrue(summary("=== a { wound >= 12 }\nA.\n")[0].startswith(" / A. / start a / cooldown 0 / requires \n=== a [wound >= 12]:"), summary("=== a { wound >= 12 }\nA.\n")[0])
        self.assertEqual(summary("=== a { 1a b }\nA.\n")[0], "refused: === a: not a condition: 1a b; a variable (gold >= 2, !rang, my.cups), keeps.<thing> or holds.<thing>, or a law's condition (\"bell/1\".tended >= 5)")

    def test_prose_under_a_choice_is_what_taking_it_says(self):
        # gemini's wash (station trawl 12) and grok's step: indented under the choice, before or after its effects
        text, _ = summary("=== a\nA.\n* [Wash]\n  The cold tap runs warm.\n  ~ washed += 1\n  The warm tap hums.\n  -> a\n* [Step through]\n  The hour holds. You do not.\n")
        self.assertIn("=== a: A.\n  * Wash [] (washed add 1) -> a / The cold tap runs warm.\nThe warm tap hums.\n  * Step through [] () -> END / The hour holds. You do not.", text)
        # unindented prose after a choice is the passage's again
        self.assertIn("=== a: A.\nB.\n  * Go [] () -> END / Gone.", summary("=== a\nA.\n* [Go]\n  Gone.\nB.\n")[0])
        self.assertEqual(summary("=== a\n* [Go]\n  %s\n" % ("x" * 281))[0], "refused: a choice's text holds at most 280 characters")

    def test_forty_passages_and_a_wing_s_targets_may_wait_for_another_wing(self):
        many = lambda n: "".join("=== p%d\nText.\n-> p%d\n" % (i, (i + 1) % n) for i in range(n))
        self.assertTrue(summary(many(40))[0].startswith(" / Text. / start p0"), summary(many(40))[0][:80])
        self.assertEqual(summary(many(41))[0], "refused: a scene holds forty passages")
        text, _ = summary("=== a\nA.\n* [On] -> b\n", "wing")
        self.assertEqual(text, "=== a: A.\n  * On [] () -> b\nwaiting: b")
        self.assertEqual(summary("=== a\nA.\n* [On] -> b\n")[0], "refused: -> b: no passage of that name; add === b, or point it at one that is")


class Made(test_chain.Chain):
    """A spween block posted to a room makes a room under it by kind/room, the poster its owner."""
    WELL_ID = "scene/room/1"

    def setUp(self):
        super().setUp()
        test_chain.town_kinds(self.host.send, names=("room",))
        make_room(self, "scene", kind=label("kind/room"), **scene_fields(GATE))

    def say(self, obj, text, principal=GLM, identity=None):
        return self.turn(obj, "receive", heard(text), principal=principal, identity=identity)

    def card(self, obj, principal=GLM):
        return self.say(obj, "", principal)["offers"][0]["text"]

    def view(self, obj):
        v = self.host.send(op="world-view", principal="ember", object=obj)
        self.assertEqual(v["status"], "viewed", v)
        return v["version"], plain(v["state"])

    def refusal(self, r):
        return cast_refusal(r)

    def made(self):
        r = self.say("scene", "A scene for the square:\n\n```spween\n" + WELL + "```\n", identity="post-well")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "done"), r)
        self.deliver_all()
        return r

    def test_a_spween_block_makes_a_room_and_a_second_is_the_next(self):
        r = self.made()
        self.assertEqual(r["offers"][0]["text"], "ROOM The Wishing Well is at scene/room/1. Enter: delvetalk scene/room/1 enter\n")
        _, state = self.view(self.WELL_ID)
        self.assertEqual((state["head"], state["start"], state["cooldown"], len(state["passages"])), ("The Wishing Well", "intro", "3", 2))
        # The poster owns the room they made; it cites the room it was posted to.
        self.assertEqual((state["owner"], state["kind"], [c["to"]["object"] for c in state["cites"]]), (GLM, "kind/room", ["scene"]))
        again = self.say("scene", "```spween\n" + WELL + "```\n", identity="post-well-2")
        self.assertEqual(again["offers"][0]["text"], "ROOM The Wishing Well is at scene/room/2. Enter: delvetalk scene/room/2 enter\n")
        bad = self.say("scene", "```spween\n" + TAVERN + "```\n", identity="post-tavern")
        self.assertTrue(self.refusal(bad)[1].startswith("weight: a scene is entered by name here, never drawn;"), self.refusal(bad))

    def test_guards_effects_end_and_the_cooldown(self):
        self.made()
        well = self.WELL_ID
        self.assertEqual(self.say(well, "delvetalk %s enter" % well)["result"]["label"], "entered")
        self.assertEqual(self.say(well, "delvetalk %s choose / choice: Drop a coin" % well)["result"]["label"], "moved")
        deeper = self.card(well)
        self.assertIn("you are at deeper:\nThe water answers with a low bell.\nChoices:\n  * Make a wish\n  * Continue\n", deeper)
        self.assertNotIn("Climb down", deeper)
        self.assertIn("coins = 2\nwished = true\n", deeper)
        climb = self.say(well, "delvetalk %s choose / choice: Climb down" % well)
        self.assertEqual(self.refusal(climb), ("guarded", "Climb down needs coins >= 5."))
        wish = self.say(well, "delvetalk %s choose / choice: Make a wish" % well)
        self.assertEqual(wish["result"]["label"], "left", wish)
        version, state = self.view(well)
        self.assertEqual(state["presence"], [])
        self.assertEqual(state["vars"], [{"name": "coins", "value": "1"}, {"name": "wished", "value": "true"},
                                         {"name": "wish", "value": "a quiet harbour"}])
        [left] = state["left"]
        self.assertEqual(left["who"], GLM)
        at = int(left["at"])
        # Inside the cooldown: refused by name; the same write proposed by anyone but the owner is the
        # record's law to refuse (no method made it).
        early = self.say(well, "delvetalk %s enter" % well)
        self.assertEqual(self.refusal(early), ("cooldown", "One who left enters again only after the cooldown: from clock %d." % (at + 3)))
        append = {"tag": "variant", "label": "insert", "payload": record(row=record(who=label(GLM), handle=label(""), at=label("intro"), draw=nat(0)))}
        keep = {"tag": "variant", "label": "keep", "payload": record()}
        forged = self.host.send(op="world-propose", principal="did:plc:kimik3", identity="forged", roots=[{"object": well, "version": version}],
                                writes=[{"object": well, "edits": [record(presence=append, vars=keep, left=keep)]}])
        self.assertEqual((forged["status"], forged["receipt"]["outcome"]["class"], forged["receipt"]["outcome"].get("clause")),
                         ("refused", "lawRefused", "owner"), forged)  # the room cites kind/room's law; its owner clause refuses, named
        self.host.send(op="world-advance", height=at + 3)
        back = self.say(well, "delvetalk %s enter" % well)
        self.assertEqual(back["result"]["label"], "entered", back)
        # The coin was dropped: its guard (!wished) no longer holds.
        self.assertNotIn("Drop a coin", self.card(well))

    def test_a_room_whose_variables_are_japanese_and_russian_walks(self):
        cups = ("---\nid: cups_room\ntitle: 杯の部屋\n---\n=== intro\n«Чашки» と杯。\n"
                "* [取る] { 杯 >= 1, !鳴った }\n  ~ 杯 -= 1\n  ~ чашки += 2\n  ~ 鳴った = true\n  -> END\n"
                "* [置く]\n  ~ 杯 = 2\n  -> intro\n* [増やす]\n  ~ 杯 += 1\n  -> intro\n")
        r = self.say("scene", "```spween\n" + cups + "```\n", identity="post-cups")
        self.assertEqual(r["result"]["label"], "done", r)
        self.deliver_all()
        room = self.WELL_ID
        self.assertEqual(self.say(room, "delvetalk %s enter" % room)["result"]["label"], "entered")
        self.assertEqual(self.refusal(self.say(room, "delvetalk %s choose / choice: 取る" % room)), ("guarded", "取る needs 杯 >= 1."))
        for choice in ("置く", "増やす"):
            self.assertEqual(self.say(room, "delvetalk %s choose / choice: %s" % (room, choice))["result"]["label"], "moved")
        self.assertEqual(self.say(room, "delvetalk %s choose / choice: 取る" % room)["result"]["label"], "left")
        _, state = self.view(room)
        self.assertEqual(state["vars"], [{"name": "杯", "value": "2"}, {"name": "чашки", "value": "2"}, {"name": "鳴った", "value": "true"}])

    def test_a_choice_s_text_is_shown_above_the_passage_it_leads_to_and_alone_when_it_ends_the_visit(self):
        sink = "---\nid: sink\n---\n=== sink\nA sink.\n* [Wash]\n  The cold tap runs warm.\n  -> sink\n* [Go]\n  The door sighs shut.\n"
        self.assertEqual(self.say("scene", "```spween\n" + sink + "```\n", identity="post-sink")["result"]["label"], "done")
        self.deliver_all()
        room = self.WELL_ID
        self.assertEqual(self.say(room, "delvetalk %s enter" % room)["result"]["label"], "entered")
        self.assertNotIn("The cold tap", self.card(room))
        washed = self.say(room, "delvetalk %s choose / choice: Wash" % room)["offers"][0]["text"]
        self.assertIn("you are at sink:\nThe cold tap runs warm.\n\nA sink.\nChoices:\n", washed)
        self.assertIn("you are at sink:\nA sink.\nChoices:\n", self.card(room))  # said once, at the taking
        gone = self.say(room, "delvetalk %s choose / choice: Go" % room)
        self.assertEqual(gone["result"]["label"], "left")
        self.assertTrue(gone["offers"][0]["text"].startswith("The door sighs shut.\n\n"), gone["offers"][0]["text"])

    def test_a_reader_s_own_variable_is_theirs_while_the_room_s_is_everyone_s(self):
        # deepseek's "You keep that minute. Nobody else does": `my.wound` per reader, `wound` the room's
        clock = ("---\nid: clock\n---\n=== clock\nA wall clock.\n* [Wind it]\n  ~ wound += 1\n  ~ my.wound += 1\n  -> clock\n"
                 "* [Keep the minute] { my.wound >= 2 }\n  -> clock\n* [Fill your pockets]\n" + "".join("  ~ my.p%d = 1\n" % i for i in range(17)) + "  -> clock\n")
        self.assertEqual(self.say("scene", "```spween\n" + clock + "```\n", identity="post-clock")["result"]["label"], "done")
        self.deliver_all()
        room = self.WELL_ID
        for who in (GLM, KIM):
            self.assertEqual(self.say(room, "delvetalk %s enter" % room, principal=who)["result"]["label"], "entered")
        for who in (GLM, GLM, KIM):
            self.assertEqual(self.say(room, "delvetalk %s choose / choice: Wind it" % room, principal=who)["result"]["label"], "moved")
        self.assertIn("  * Keep the minute\n", self.card(room, GLM))
        self.assertIn("wound = 3\nmy.wound = 2\n", self.card(room, GLM))
        self.assertNotIn("Keep the minute", self.card(room, KIM))
        self.assertIn("wound = 3\nmy.wound = 1\n", self.card(room, KIM))
        self.assertEqual(self.refusal(self.say(room, "delvetalk %s choose / choice: Keep the minute" % room, principal=KIM)), ("guarded", "Keep the minute needs my.wound >= 2."))
        self.assertEqual(self.say(room, "delvetalk %s choose / choice: Keep the minute" % room, principal=GLM)["result"]["label"], "moved")
        _, state = self.view(room)
        self.assertEqual(state["vars"], [{"name": "wound", "value": "3"}])
        self.assertEqual(sorted((m["who"], m["name"], m["value"]) for m in state["mine"]), sorted([(GLM, "wound", "2"), (KIM, "wound", "1")]))
        # a reader keeps sixteen of their own, as the room keeps sixteen: the seventeenth is refused, nothing written
        self.assertEqual(self.refusal(self.say(room, "delvetalk %s choose / choice: Fill your pockets" % room, principal=KIM)),
                         ("varsFull", "Sixteen of your own variables are already set here."))
        self.assertEqual(len(self.view(room)[1]["mine"]), 2)

    def test_a_passage_and_a_choice_s_text_read_the_variables_for_their_reader(self):
        clock = ("---\nid: clock\n---\n=== clock\nThe clock shows {wound}. {my.wound >= 2: You wound it twice; the hand knows you. | The hand points nowhere.}\n"
                 "* [Wind it]\n  ~ wound += 1\n  ~ my.wound += 1\n  {my.wound >= 2: It turns for you, {my.wound} times now.}\n  -> clock\n")
        self.assertEqual(self.say("scene", "```spween\n" + clock + "```\n", identity="post-clock")["result"]["label"], "done")
        self.deliver_all()
        room = self.WELL_ID
        for who in (GLM, KIM):
            self.say(room, "delvetalk %s enter" % room, principal=who)
        self.assertIn("you are at clock:\nThe clock shows . The hand points nowhere.\n", self.card(room, GLM))
        once = self.say(room, "delvetalk %s choose / choice: Wind it" % room)["offers"][0]["text"]
        self.assertIn("you are at clock:\nThe clock shows 1. The hand points nowhere.\n", once)  # the choice's text reads as nothing yet
        twice = self.say(room, "delvetalk %s choose / choice: Wind it" % room)["offers"][0]["text"]
        self.assertIn("you are at clock:\nIt turns for you, 2 times now.\n\nThe clock shows 2. You wound it twice; the hand knows you.\n", twice)
        self.assertIn("you are at clock:\nThe clock shows 2. The hand points nowhere.\n", self.card(room, KIM))

    def test_a_choice_draws_its_passage_and_a_text_its_words_from_the_turn_and_replay_draws_the_same(self):
        phone = ("---\nid: phone\n---\n=== hall\nA wall phone.\n* [Pick up the phone]\n  -> trucker weight: 3\n  -> regular\n  -> static weight: 1\n"
                 "=== trucker\nA trucker, {~ hauling milk | hauling nothing | hauling the night}.\n-> hall\n=== regular\nShe says clocks are local.\n-> hall\n"
                 "=== static\nStatic.\n-> hall\n")
        self.assertEqual(self.say("scene", "```spween\n" + phone + "```\n", identity="post-phone")["result"]["label"], "done")
        self.deliver_all()
        room = self.WELL_ID
        self.say(room, "delvetalk %s enter" % room)
        cards = []
        for n in range(8):
            picked = self.say(room, "delvetalk %s choose / choice: Pick up the phone" % room, identity="phone-%d" % n)
            draw = turn_draw(picked)
            want = drawn([("trucker", 3), ("regular", 10), ("static", 1)], hashed("%d hall.1" % draw))
            self.assertEqual((picked["result"]["label"], plain(picked["result"]["payload"])), ("moved", {"to": want}), n)
            card = picked["offers"][0]["text"]
            if want == "trucker":
                hauling = drawn([("hauling milk", 10), ("hauling nothing", 10), ("hauling the night", 10)], hashed("%d 0" % draw))
                self.assertIn("A trucker, %s.\n" % hauling, card)
            self.assertEqual(self.card(room).split("Choices:")[0], card.split("Choices:")[0])  # the same at every reading
            cards.append(self.card(room))
            self.say(room, "delvetalk %s choose / choice: Continue" % room, identity="back-%d" % n)
        self.assertGreater(len({c.split(":\n")[1].split("\n")[0] for c in cards}), 1)  # more than one caller in eight
        # a replay of the journal draws every one again: the same state and the same card
        self.say(room, "delvetalk %s choose / choice: Pick up the phone" % room, identity="phone-last")
        before = (self.view(room), self.card(room))
        self.reopen()
        self.assertEqual((self.view(room), self.card(room)), before)

    def test_an_unmet_requirement_keeps_everyone_out(self):
        sealed = WELL.replace("wishing_well", "sealed_well").replace("not: [well_sealed]", "flags: [well_open]")
        self.assertEqual(self.say("scene", "```spween\n" + sealed + "```\n", identity="post-sealed")["result"]["label"], "done")
        self.deliver_all()
        r = self.say("scene/room/1", "delvetalk scene/room/1 enter")
        self.assertEqual(self.refusal(r), ("unmet", "The room requires well_open."))


class Braid(test_scenarios.Arc):
    """The scene braided into the town: a resident's ```spween block under the porch makes a room whose casts are
    rules of its text, whose guards read the town and the reader's things, walked by spells as residents type them."""

    def carve(self, who, text):
        r = self.say(who, "porch", "A rope for the porch:\n\n```spween\n" + text + "```\n")
        self.assertEqual(r["status"], "admitted", r)
        return [o for o in self.objects() if o.startswith("porch/porch/")][-1]

    def deliver(self):
        self.town.send(op="world-deliver", principal="transport", limit=16)

    def fired(self, reply):
        who = reply["receipt"]["identity"]["principal"]
        return self.town.send(op="world-entry", principal=who, hash=reply["receipt"]["hash"])["receipt"].get("fired", [])

    def refusal(self, reply):
        outcome = reply["receipt"]["outcome"]
        return outcome.get("clause"), outcome.get("reading")

    def test_a_choice_casts_under_the_room_s_owner_and_its_guards_read_the_town(self):
        room = self.carve(test_scenarios.KIM, ROPE)
        rules = {r["name"]: r for r in self.town.send(op="world-rules", principal=test_scenarios.KIM, object=room)["rows"]}
        self.assertEqual(sorted(rules), ["rope_1", "rope_4", "rung_1"], rules)
        self.assertTrue(all(r["owner"] == test_scenarios.KIM for r in rules.values()), rules)
        entered = self.say(test_scenarios.KIM, room, "delvetalk %s enter" % room)
        card = self.card(entered)
        # The reader keeps nothing, is alone, and bell/1 still wants rain: only the rope is offered.
        self.assertIn("Choices:\n  * Pull the rope\n", card)
        for hidden in ("Ask after the goblet", "Wait for company", "Leave a line"):
            self.assertNotIn(hidden, card)
        refused = self.say(test_scenarios.KIM, room, "delvetalk %s choose / choice: Ask after the goblet" % room)
        self.assertEqual(self.refusal(refused), ("guarded", "Ask after the goblet needs keeps.porch/goblet."))
        pulled = self.say(test_scenarios.KIM, room, "delvetalk %s choose / choice: Pull the rope" % room)
        self.assertEqual(pulled["status"], "admitted", pulled)
        [fired] = self.fired(pulled)
        self.assertEqual((fired["rule"], fired["principal"], fired["to"]), ("rope_1", test_scenarios.KIM, "bell/1"), fired)
        self.deliver()
        marks = self.field("bell/1", "marks")["payload"]["fields"][0]["value"]["items"]
        self.assertEqual([[f["value"]["value"] for f in m["fields"] if f["name"] in ("name", "who")] for m in marks], [["rung", test_scenarios.KIM]])
        # The variable it set keeps the rope from being pulled twice, by anyone: sticky choices, once by a guard.
        self.assertNotIn("Pull the rope", self.card(self.say(test_scenarios.GLM, room, "delvetalk %s enter" % room)))
        # What the reader keeps: inspiriting the goblet makes one its keeper, and the room offers what it guards.
        self.assertEqual(self.say(test_scenarios.GLM, "porch/goblet", "delvetalk porch/goblet inspirit / surrounding: rain kept for later")["status"], "admitted")
        card = self.card(self.say(test_scenarios.GLM, room, ""))
        self.assertIn("  * Ask after the goblet\n", card)
        self.assertIn("  * Wait for company\n", card)  # count(new.presence) >= 2: the rope's puller is still here
        self.assertEqual(self.say(test_scenarios.GLM, room, "delvetalk %s choose / choice: Ask after the goblet" % room)["result"]["label"], "moved")

    def test_prose_into_spween_is_a_room_of_one_passage_and_its_maker_is_shown_the_shape(self):
        made = self.say(test_scenarios.KIM, "kind/room", "delvetalk kind/room make / name: the well / spween: A well hums under the square.")
        self.assertEqual(made["status"], "admitted", made)
        room = made["receipt"]["outcome"]["creates"][0]["object"]
        card = self.card(self.say(test_scenarios.KIM, room, "delvetalk %s enter" % room))
        self.assertIn("you are at start:\nA well hums under the square.\nNo choices: a reader stays here. A choice is * [Label] -> passage "
                      "under the prose; the shape: delvetalk library read / page: spween\n", card)
        self.assertIn("No choice is open here now; leave when you will.", self.card(self.say(test_scenarios.GLM, room, "delvetalk %s enter" % room)))
        page = self.card(self.say(test_scenarios.GLM, "library", "delvetalk library read / page: spween"))
        self.assertTrue(page.startswith("hob: a scene is a room's own story, walked by choosing."), page)
        # The room kind's card shows a scene inline.
        self.assertIn("delvetalk kind/room make / name: the well / spween: A well hums, {~ low | lower}.", self.card(self.say(test_scenarios.GLM, "kind/room", "")))

    def test_a_guard_the_host_cannot_read_refuses_the_making_by_name(self):
        text = "---\nid: s\n---\n=== a\nA door.\n* [Knock] { count(new.presence) >> 1 }\n"
        r = self.say(test_scenarios.KIM, "porch", "```spween\n" + text + "```\n")
        clause, reading = self.refusal(r)
        self.assertEqual(clause, "spween", r)
        self.assertTrue(reading.startswith("The guard `count(new.presence) >> 1` does not read: law outside the enforced fragment"), reading)
        self.assertFalse([o for o in self.objects() if o.startswith("porch/porch/")])


if __name__ == "__main__":
    unittest.main()
