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
from tests.test_scene import GATE, GLM, heard, plain, scene_state
from tests.test_objects import closure
from tests.test_turn_world import label, record

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
def clauses(guard: Scenes.Guard) -> String:
  textJoin(Lists.map(guard, fn(c: Scenes.Clause) -> String: "{c.key} {c.op} {c.value}"), ", ")
def effects(list: Lists.List<Scenes.Effect>) -> String:
  textJoin(Lists.map(list, fn(e: Scenes.Effect) -> String: "{e.key} {e.op} {e.value}"), "; ")
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
    def test_the_readmes_tavern_names_a_weight_and_is_refused_by_name(self):
        text, _ = summary(TAVERN)
        self.assertEqual(text, "refused: weight: a scene is entered by name here, never drawn by weight")

    def test_the_tavern_without_its_weight_lowers_to_two_passages(self):
        text, ticks = summary(TAVERN.replace("weight: 10\n", ""))
        self.assertEqual(text, "tavern-encounter / The Mysterious Stranger / start intro / cooldown 0 / requires \n"
                               "=== intro: A hooded figure sits alone in the corner of the tavern.\n"
                               "  * Approach them [courage >= 5] (courage sub 1) -> conversation\n"
                               "  * Order a drink instead [] (gold sub 2) -> END\n"
                               "=== conversation: \"I've been expecting you,\" they whisper.\n"
                               "  * Ask about the quest [] (quest_started set true) -> END")

    def test_the_well_keeps_its_cooldown_requirements_guards_and_divert(self):
        text, ticks = summary(WELL)
        self.assertEqual(text, "wishing-well / The Wishing Well / start intro / cooldown 3 / requires well_sealed falsy \n"
                               "=== intro: A mossy well hums under the square.\nCoins glint far below.\n"
                               "  * Drop a coin [wished falsy ] (coins add 2; wished set true) -> deeper\n"
                               "  * Walk on [] () -> END\n"
                               "=== deeper: The water answers with a low bell.\n"
                               "  * Make a wish [coins >= 2] (coins sub 1; wish set a quiet harbour) -> END\n"
                               "  * Climb down [coins >= 5] () -> intro\n"
                               "  * Continue [] () -> intro")

    def test_calls_has_and_stray_effects_are_refused_by_name(self):
        body = "---\nid: s\n---\n=== a\nText.\n* [Go]\n  %s\n  -> END\n"
        self.assertTrue(summary(body % '~ play_sound "victory"')[0].startswith("refused: ~ call: play_sound"))
        self.assertTrue(summary(body % '~ call("play_sound", "victory")')[0].startswith("refused: ~ call: call("))
        self.assertTrue(summary("---\nid: s\n---\n=== a\n* [Go] { inventory.sword }\n  -> END\n")[0].startswith("refused: has: inventory.sword"))
        self.assertTrue(summary("---\nid: s\nrequires:\n  has: [inventory.sword]\n---\n=== a\n")[0].startswith("refused: has:"))
        self.assertTrue(summary("---\nid: s\n---\n=== a\n~ gold += 1\n")[0].startswith("refused: an effect outside a choice"))
        self.assertEqual(summary("---\nid: s\n---\n=== a\n* [Go]\n  -> nowhere\n")[0], "refused: -> nowhere: no passage of that name")
        self.assertEqual(summary("=== a\nText.\n")[0], "refused: a scene starts with frontmatter naming its id: ---, id: <name>, ---")


class Made(test_chain.Chain):
    WELL_ID = "scene/wishing-well"

    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-scene", object="scene",
                           modules=closure("Scene"), entry="initial", seed=scene_state(GATE))
        self.assertEqual(r["status"], "created", r)

    def say(self, obj, text, principal=GLM, identity=None):
        return self.turn(obj, "receive", heard(text), principal=principal, identity=identity)

    def card(self, obj, principal=GLM):
        return self.say(obj, "", principal)["offers"][0]["text"]

    def view(self, obj):
        v = self.host.send(op="world-view", principal="ember", object=obj)
        self.assertEqual(v["status"], "viewed", v)
        return v["version"], plain(v["state"])

    def refusal(self, r):
        fields = {f["name"]: f["value"]["value"] for f in r["result"]["payload"]["fields"]}
        return fields["clause"], fields["reading"]

    def made(self):
        r = self.say("scene", "A scene for the square:\n\n```spween\n" + WELL + "```\n", identity="post-well")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "done"), r)
        return r

    def test_a_spween_block_makes_a_scene_and_a_second_is_refused_its_name(self):
        r = self.made()
        self.assertEqual(r["offers"][0]["text"], "SCENE The Wishing Well is at scene/wishing-well: 2 passages. "
                                                 "Reply delvetalk scene/wishing-well enter to begin.\n")
        _, state = self.view(self.WELL_ID)
        self.assertEqual((state["title"], state["start"], state["cooldown"], len(state["passages"])), ("The Wishing Well", "intro", "3", 2))
        # The poster owns the scene they made.
        self.assertEqual(state["owner"], GLM)
        again = self.say("scene", "```spween\n" + WELL + "```\n", identity="post-well-2")
        out = again["receipt"]["outcome"]
        self.assertEqual((again["status"], out["class"]), ("refused", "requiredAbsence"), again)
        bad = self.say("scene", "```spween\n" + TAVERN + "```\n", identity="post-tavern")
        self.assertEqual(self.refusal(bad), ("spween", "weight: a scene is entered by name here, never drawn by weight"))

    def test_guards_effects_end_and_the_cooldown_as_a_law(self):
        self.made()
        well = self.WELL_ID
        self.assertEqual(self.say(well, "delvetalk %s enter" % well)["result"]["label"], "done")
        self.assertEqual(self.say(well, "delvetalk %s choose / choice: Drop a coin" % well)["result"]["label"], "done")
        deeper = self.card(well)
        self.assertEqual(deeper, (
            "SCENE The Wishing Well (1 here), you are at deeper:\n"
            "The water answers with a low bell.\n"
            "Choices:\n"
            "  * Make a wish\n"
            "  * Continue\n"
            "coins = 2\n"
            "wished = true\n"
            "\n"
            "Reply with a spell:\n"
            "\n"
            "    delvetalk scene/wishing-well enter\n"
            "\n"
            "    delvetalk scene/wishing-well choose\n"
            "    choice: <text, 1 to 64 characters>\n"
            "\n"
            "    delvetalk scene/wishing-well leave\n"))
        self.assertIn("you are at deeper:\nThe water answers with a low bell.\nChoices:\n  * Make a wish\n  * Continue\n", deeper)
        self.assertNotIn("Climb down", deeper)
        self.assertIn("coins = 2\nwished = true\n", deeper)
        climb = self.say(well, "delvetalk %s choose / choice: Climb down" % well)
        self.assertEqual(self.refusal(climb), ("guarded", "Climb down needs coins >= 5."))
        wish = self.say(well, "delvetalk %s choose / choice: Make a wish" % well)
        self.assertEqual(wish["result"]["label"], "done", wish)
        version, state = self.view(well)
        self.assertEqual(state["presence"], [])
        self.assertEqual(state["vars"], [{"name": "coins", "value": "1"}, {"name": "wished", "value": "true"},
                                         {"name": "wish", "value": "a quiet harbour"}])
        [left] = state["left"]
        self.assertEqual(left["who"], GLM)
        at = int(left["at"])
        # Inside the cooldown: refused by name, and the same write proposed directly by the law.
        early = self.say(well, "delvetalk %s enter" % well)
        self.assertEqual(self.refusal(early), ("cooldown", "You left at clock %d; enter again from clock %d." % (at, at + 3)))
        append = {"tag": "variant", "label": "append", "payload": record(item=record(who=label(GLM), at=label("intro")))}
        keep = {"tag": "variant", "label": "keep", "payload": record()}
        forged = self.host.send(op="world-propose", principal=GLM, identity="forged", roots=[{"object": well, "version": version}],
                                writes=[{"object": well, "edits": [record(presence=append, vars=keep, left=keep)]}])
        self.assertEqual((forged["status"], forged["receipt"]["outcome"]["class"], forged["receipt"]["outcome"].get("clause")),
                         ("refused", "lawRefused", "cooldown"), forged)
        self.host.send(op="world-advance", height=at + 3)
        back = self.say(well, "delvetalk %s enter" % well)
        self.assertEqual(back["result"]["label"], "done", back)
        # The coin was dropped: its guard (!wished) no longer holds.
        self.assertNotIn("Drop a coin", self.card(well))

    def test_an_unmet_requirement_keeps_everyone_out(self):
        sealed = WELL.replace("wishing_well", "sealed_well").replace("not: [well_sealed]", "flags: [well_open]")
        self.assertEqual(self.say("scene", "```spween\n" + sealed + "```\n", identity="post-sealed")["result"]["label"], "done")
        r = self.say("scene/sealed-well", "delvetalk scene/sealed-well enter")
        self.assertEqual(self.refusal(r), ("unmet", "The scene requires well_open."))


if __name__ == "__main__":
    unittest.main()
