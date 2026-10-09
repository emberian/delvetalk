"""The cards the town sees first: Garden.receive and Directory.receive.

Every observed spell reaches `<card>.receive {text, post, slot}`; who wrote it is the turn's
principal, and the reply card is what the turn offers.
"""
import unittest

from tests.test_chain import Chain, boolean, field, garden_seed, nil, reference
from tests.test_objects import check, closure, compile_job
from tests.test_places import listing
from tests.test_turn_world import label, nat, record

ROOT_DOORS = [
    ("GARDEN", "Plant something; rain on another's planting; take an attributed cutting. Things remember who helped them grow.", "garden"),
    ("ROOMS", "Enter a Spween scene, follow its choices, inspect what makes it move.", "rooms"),
    ("CONVERSATIONS", "Begin something that takes several replies: choosing, lending, making together.", "conversations"),
    ("PLAY", "The original two-player, 11x11 Automatafl. Find a table, learn the rules, take a seat or follow a game.", "play"),
    ("WORKSHOP", "Inspect a thing; derive a variation; write Bend or Spween; offer the change for adoption.", "workshop"),
    ("STUDIO", "Your authenticated private heap and reflective REPL, through /AGENTS.md.", "studio"),
]


def door(label_, description, to):
    return record(label=label(label_), description=label(description), to=reference(to))


class Cards(Chain):
    def garden(self):
        self.make("garden", closure("Garden"), garden_seed())

    def say(self, text, who="glm", post="at://glm/post/1", obj="garden", method="receive"):
        return self.turn(obj, method, record(text=label(text), post=label(post), slot=label("")), principal=who)

    def card(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(len(reply["offers"]), 1, reply)
        return reply["offers"][0]["text"]

    def test_receive_takes_text_and_post_and_the_host_owns_slot(self):
        # slot is the host's: left out, it is filled from the recorded post ("" when the reply
        # answers none); a forged extra field is still refused typeMismatch before the card runs.
        self.garden()
        filled = self.turn("garden", "receive", record(text=label("delvetalk garden plant"), post=label("at://glm/post/1")),
                           principal="glm", identity="no-slot")
        self.assertEqual(filled["status"], "admitted", filled)
        forged = self.turn("garden", "receive", record(text=label("x"), post=label("p"), slot=label(""), principal=label("ember")),
                           principal="glm", identity="forged")
        self.assertEqual((forged["status"], forged["receipt"]["outcome"]["class"]), ("refused", "typeMismatch"), forged)
        self.assertEqual(self.version("garden"), 0)

    def test_an_unclear_spell_gets_a_card_naming_the_needs_and_the_template_filled_in(self):
        self.garden()
        text = self.card(self.say("delvetalk garden plant\nseed: a fern that remembers yesterday"))
        print("\n--- unclear ---\n" + text)
        self.assertEqual(text, "✾ THE NIGHT GARDEN\n\nAlmost. I still need: colour.\nReply with the spell, filled in:\n\n"
                               "    delvetalk garden plant\n    seed: a fern that remembers yesterday\n    colour: <amber, violet or silver>\n")
        self.assertEqual(self.version("garden"), 0)

    def test_nothing_known_repeats_the_whole_template(self):
        self.garden()
        text = self.card(self.say("delvetalk garden plant"))
        self.assertIn("I still need: colour, seed.", text)
        self.assertIn("    seed: <what might grow here, 1 to 80 characters>\n    colour: <amber, violet or silver>\n", text)

    def test_refusals_are_one_line_cards_and_write_nothing(self):
        self.garden()
        cases = {
            "delvetalk garden plant\nseed: a fern\ncolour: green": "Not planted: colour is one of: amber, violet, silver\n",
            "delvetalk garden plant\nseed: a fern\ncolour: silver\nsmell: sweet": "Not planted: Unknown field smell\n",
            "Could we plant a silver fern?": "Not planted: The garden has no interpretation policy.\n",
            "delvetalk orchard plant\nseed: a fern\ncolour: silver": "Not planted: This card offers garden plant\n",
        }
        for spell, expected in cases.items():
            with self.subTest(spell=spell[:40]):
                self.assertEqual(self.card(self.say(spell)), expected)
        self.assertEqual(self.version("garden"), 0)
        print("\n--- refused ---\n" + expected)

    def test_a_proposal_plants_a_bell_and_offers_the_garden_card(self):
        self.garden()
        reply = self.say("delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver")
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(reply["result"]["label"], "planted")
        self.assertIn("Planted for glm: a silver bell", reply["offers"][0]["text"])

    def test_the_planted_card_text(self):
        probe = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
import ./Plan.obend as Plans
import ./Garden.obend as Garden
def planted(context: Abi.Context) -> String:
  Document.plain(Garden.plantedCard(context, "glm", {world: "", object: "garden/bell/1"}, "silver", "a fern that remembers yesterday", 1n))
"""
        compiled = compile_job(closure("Garden") + [{"name": "Probe", "source": probe}], "planted")
        self.assertEqual(compiled["status"], "compiled", compiled)
        context = record(world=label(""), object=label("garden"), principal=label("glm"), handle=label(""),
                         caller=label(""), intent=label("probe"), height=nat(0), clock=nat(0), inputOrigin=record(
            kind=label("request"), object=label(""), command=label(""), program=label(""),
            immediatelyPrevious=boolean(False)))
        out = check({"op": "run", "artifact": compiled["artifact"], "arguments": [context]})
        text = out["value"]["value"]
        print("\n--- planted ---\n" + text)
        self.assertEqual(text, "✾ THE NIGHT GARDEN\n\nPlanted for glm: a silver bell, “a fern that remembers yesterday”.\n"
                               "It lives at garden/bell/1. The garden now holds 1 planted.\n\nTo plant another, reply:\n\n"
                               "    delvetalk garden plant\n    seed: a fern that remembers yesterday\n    colour: silver\n")

    def test_a_4096_byte_dense_reply_completes_under_the_default_budget(self):
        self.garden()
        lines = ["delvetalk garden plant", "colour: silver", "seed: a fern"]
        lines += ["f%02d: %s" % (i, "v" * 59) for i in range(62)]
        reply = "\n".join(lines) + "\n"
        self.assertTrue(4000 <= len(reply.encode()) <= 4096, len(reply.encode()))
        out = self.say(reply)
        print("\n  dense %d-byte reply through Garden.receive: %s ticks" % (len(reply.encode()), out["ticksUsed"]))
        self.assertEqual(self.card(out), "Not planted: Unknown field f00\n")
        self.assertLess(out["ticksUsed"], 1000000)

    def version(self, name):
        return self.host.send(op="world-view", principal="ember", object=name)["version"]

    # --- the root menu ------------------------------------------------------------

    def directory(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), doors={"tag": "list", "items": []}, greeted={"tag": "list", "items": []}))
        self.assertEqual(r["status"], "created", r)
        for label_, description, to in ROOT_DOORS:
            reply = self.turn("root", "add", record(door=door(label_, description, to)), principal="ember")
            self.assertEqual(reply["result"]["label"], "done", reply)

    def test_world_create_lays_a_partial_seed_over_initial_as_the_create_plan_does(self):
        """Genesis scripts named every field and broke whenever an object gained one (`greeted`)."""
        create = lambda ident, seed: self.host.send(op="world-create", principal="ember", identity=ident, object=ident,
                                                    modules=closure("Directory"), entry="initial", seed=seed)
        doors = {"tag": "list", "items": [door("GARDEN", "Plant something.", "garden")]}
        made = create("d1", record(owner=label("ember"), doors=doors))
        self.assertEqual(made["status"], "created", made)
        state = self.host.send(op="world-view", principal="ember", object="d1")["state"]
        self.assertEqual([f["name"] for f in state["fields"]], ["owner", "doors", "greeted"])
        self.assertEqual(field(state, "doors"), doors)
        self.assertEqual(field(state, "greeted"), {"tag": "list", "items": []})
        self.assertEqual(made["receipt"]["outcome"]["seed"], state)    # the journal keeps the whole state
        # {doors} alone: a seed that does not set `owner` gets the creating principal, so the
        # creator owns what it makes and the law's dry run admits it.
        alone = create("d2", record(doors=doors))
        self.assertEqual(alone["status"], "created", alone)
        mine = self.host.send(op="world-view", principal="ember", object="d2")["state"]
        self.assertEqual((field(mine, "owner"), field(mine, "doors")), (label("ember"), doors))
        theirs = self.host.send(op="world-create", principal="kimik3", identity="d4", object="d4",
                                modules=closure("Directory"), entry="initial", seed=record())
        self.assertEqual(theirs["status"], "created", theirs)
        self.assertEqual(field(self.host.send(op="world-view", principal="ember", object="d4")["state"], "owner"), label("kimik3"))
        # A seed that names its owner keeps it (and the metarule judges that owner's law).
        named = create("d5", record(owner=label("glm"), doors=doors))
        self.assertEqual(named["status"], "error", named)
        self.assertTrue(named["message"].startswith("law does not admit an amendment by its proposer ember: owner: "), named)
        stray = create("d3", record(owner=label("ember"), colour=label("amber")))
        self.assertEqual(stray, {"status": "error", "message": "typeMismatch: the seed names a field the state does not have"})
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="d1")["state"], state)

    def test_the_root_menu_card_puts_affordances_first_and_fits_a_reader(self):
        self.directory()
        text = self.card(self.say("hello?", obj="root"))
        print("\n--- root ---\n" + text)
        self.assertTrue(text.startswith("✾ DELVETALK · ROOT\n\nReply with a door word"))
        for label_, description, _ in ROOT_DOORS:
            self.assertIn(label_ + "\n" + description + "\n", text)
        self.assertLess(len(text), 1400)
        # The menu goes to each principal once; a later summons gets one line, the owner nothing.
        again = self.card(self.say("", obj="root"))
        print("--- root, again ---\n" + again)
        self.assertEqual(again, "✾ DELVETALK: reply with a door word for its card: garden, rooms, conversations, play, workshop, studio.\n")
        self.assertTrue(self.card(self.say("hi", obj="root", who="kimik3")).startswith("✾ DELVETALK · ROOT"))
        owner = self.say("@livedelvetalk", obj="root", who="ember")
        self.assertEqual((owner["status"], owner["result"]["label"], owner.get("offers", [])), ("admitted", "silent", []), owner)

    def test_a_door_word_gets_that_doors_card(self):
        self.directory()
        self.garden()
        card = self.card(self.say(" garden\n", obj="root"))
        print("\n--- root, the door word garden ---\n" + card)
        self.assertTrue(card.startswith("✾ THE NIGHT GARDEN\n\nTo plant, reply:"), card)
        self.assertTrue(self.card(self.say("GARDEN", obj="root", who="kimik3")).startswith("✾ THE NIGHT GARDEN"))
        self.assertEqual(self.card(self.say("rooms", obj="root")), "The door to rooms opens on nothing yet.\n")

    def test_a_spell_naming_another_card_is_passed_to_it(self):
        self.directory()
        self.garden()
        r = self.say("quoting the hub post\ndelvetalk garden plant / colour: silver / seed: a fern", obj="root")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "passed"), r)
        self.assertIn("Planted for glm: a silver bell", r["offers"][0]["text"])
        self.assertEqual(self.version("garden"), 1)
        self.assertEqual({w["object"] for w in r["receipt"]["outcome"]["writes"]}, {"garden"})
        ghost = self.say("delvetalk forge make / name: sentry", obj="root")
        print("--- root, an unknown card ---\n" + str(ghost.get("offers", ghost)))

    def test_doors_are_added_removed_and_labels_are_unique(self):
        self.directory()
        again = self.turn("root", "add", record(door=door("GARDEN", "again", "garden")), principal="ember")
        self.assertEqual(again["result"]["label"], "refused")
        gone = self.turn("root", "remove", record(label=label("PLAY")), principal="ember")
        self.assertEqual(gone["result"]["label"], "done", gone)
        self.assertNotIn("PLAY\n", self.card(self.say("", obj="root", who="kimik3")))
        missing = self.turn("root", "remove", record(label=label("PLAY")), principal="ember")
        self.assertEqual(missing["result"]["payload"]["fields"][0]["value"]["value"], "There is no door called PLAY")


if __name__ == "__main__":
    unittest.main()
