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

from tests import test_chain
from tests.test_objects import run_pure
from tests.test_scene import GATE, GLM, heard, plain, scene_fields
from tests.test_rooms import make_room
from tests.wire import cast_refusal, label, record

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
    case _: Scenes.symbol(t)
def op(o: Scenes.Op) -> String:
  match o:
    case set(_): "set"
    case add(_): "add"
    case sub(_): "sub"
def clauses(guard: Scenes.Guard) -> String:
  textJoin(Lists.map(guard, fn(c: Scenes.Clause) -> String: "{c.key} {test(c.test)} {c.value}"), ", ")
def effects(list: Lists.List<Scenes.Effect>) -> String:
  textJoin(Lists.map(list, fn(e: Scenes.Effect) -> String: "{e.key} {op(e.op)} {e.value}"), "; ")
def choice(c: Scenes.Choice) -> String:
  "  * {c.label} [{clauses(c.guard)}] ({effects(c.effects)}) -> {c.to}"
def passage(p: Scenes.Passage) -> String:
  "=== {p.id}: {p.text}\\n{textJoin(Lists.map(p.choices, choice), \\"\\\\n\\")}"
def summary(text: String) -> String:
  match Spween.parse(text):
    case refused(r): "refused: {r.reason}"
    case parsed(p): "{p.id} / {p.seed.title} / start {p.seed.start} / cooldown {natText(p.seed.cooldown)} / requires {clauses(p.seed.requires)}\\n{textJoin(Lists.map(p.seed.passages, passage), \\"\\\\n\\")}"
"""


def summary(text):
    out = run_pure("Spween", "summary", label(text), probe=PROBE, limits={"ticks": "1000000"})
    assert out["status"] == "finished", out
    return out["value"]["value"], out["ticksUsed"]


class Parse(unittest.TestCase):
    def test_weights_calls_has_stray_effects_dangling_targets_and_long_passages_are_refused_by_name(self):
        body = "---\nid: s\n---\n=== a\nText.\n* [Go]\n  %s\n  -> END\n"
        long = "---\nid: s\n---\n=== a\n%s\n* [Go]\n  -> END\n"
        for text, refusal in ((TAVERN, "refused: weight: a scene is entered by name here, never drawn by weight"),
                              (body % '~ play_sound "victory"', "refused: ~ call: play_sound"),
                              (body % '~ call("play_sound", "victory")', "refused: ~ call: call("),
                              ("---\nid: s\n---\n=== a\n* [Go] { inventory.sword }\n  -> END\n", "refused: has: inventory.sword"),
                              ("---\nid: s\nrequires:\n  has: [inventory.sword]\n---\n=== a\n", "refused: has:"),
                              ("---\nid: s\n---\n=== a\n~ gold += 1\n", "refused: an effect outside a choice"),
                              ("---\nid: s\n---\n=== a\n* [Go]\n  -> nowhere\n", "refused: -> nowhere: no passage of that name"),
                              ("=== a\nText.\n", "refused: a scene starts with frontmatter naming its id: ---, id: <name>, ---"),
                              (long % ("x" * 601), "refused: a passage holds at most 600 characters"),
                              (long % ("x" * 600), "s / s")):
            with self.subTest(refusal=refusal):
                self.assertTrue(summary(text)[0].startswith(refusal), summary(text)[0])


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
        self.assertEqual(self.refusal(bad), ("spween", "weight: a scene is entered by name here, never drawn by weight"))

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
        append = {"tag": "variant", "label": "insert", "payload": record(row=record(who=label(GLM), handle=label(""), at=label("intro")))}
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

    def test_an_unmet_requirement_keeps_everyone_out(self):
        sealed = WELL.replace("wishing_well", "sealed_well").replace("not: [well_sealed]", "flags: [well_open]")
        self.assertEqual(self.say("scene", "```spween\n" + sealed + "```\n", identity="post-sealed")["result"]["label"], "done")
        self.deliver_all()
        r = self.say("scene/room/1", "delvetalk scene/room/1 enter")
        self.assertEqual(self.refusal(r), ("unmet", "The room requires well_open."))


if __name__ == "__main__":
    unittest.main()
