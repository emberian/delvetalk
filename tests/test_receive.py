"""The garden and the root directory answer spells with cards: needs named, refusals in one line, the
menu once per principal, door words, spells passed on.

Evidence for FOUNDATION §5 (layer: objects).

The cards the town sees first: Garden.receive and Directory.receive.

Every observed spell reaches `<card>.receive {text, post}`; who wrote it is the turn's
principal, and the reply card is what the turn offers.
"""
import unittest

from deploy.genesis import DOORS
from tests.test_replay import get, relation, rows
from tests.test_chain import Chain, boolean, field, garden_seed, nil, reference
from tests.test_objects import check, closure, compile_job
from tests.test_places import listing
from tests.test_turn_world import label, nat, record
from transport.identity import ORIGIN

ROOT_DOORS = DOORS  # (label, description, object, watched field, [(spell, what comes back)])


def door(label_, description, to, watch="", examples=()):
    """A Directory `Door`: its spells and `»` lines, and the field of its object the door line counts."""
    return record(label=label(label_), description=label(description), to=reference(to),
                  examples=listing(record(example=label(e), comes=label(c)) for e, c in examples), watch=label(watch))


class Cards(Chain):
    def garden(self):
        self.make("garden", closure("Garden"), garden_seed())

    def say(self, text, who="glm", post="at://glm/post/1", obj="garden", method="receive"):
        return self.turn(obj, method, record(text=label(text), post=label(post)), principal=who)

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
        # The unclear spell is held for glm to complete (one write); the forged turn wrote nothing.
        self.assertEqual(self.version("garden"), 1)

    def test_an_unclear_spell_gets_a_card_naming_the_needs_and_the_template_filled_in(self):
        self.garden()
        text = self.card(self.say("delvetalk garden plant\nseed: a fern that remembers yesterday"))
        self.assertEqual(text, "✾ THE NIGHT GARDEN\n\nAlmost. I still need: colour.\nReply with just the missing lines, or the spell filled in:\n\n"
                               "    delvetalk garden plant\n    seed: a fern that remembers yesterday\n    colour: <amber, violet or silver>\n")
        # The spell is held for glm, and the missing line alone completes it.
        self.assertEqual(self.version("garden"), 1)
        planted = self.say("colour: silver", post="at://glm/post/2")
        self.assertEqual(planted["result"]["label"], "planted", planted)
        self.assertIn("a silver bell, “a fern that remembers yesterday”", self.card(planted))
        # The bell awaits a reply to the post that completed it (codex objects 12).
        self.assertEqual(field(self.state("garden/bell/1"), "planting"), label("at://glm/post/2"))

    def test_a_completed_seed_keeps_the_forms_eighty_characters(self):
        """Field lines that reach receive (the first names no form) are held to the plant form's
        bounds: an 81-character seed is refused by name, never planted or held (codex objects 11)."""
        self.garden()
        long = "x" * 81
        reply = self.say("smell: sweet\ncolour: silver\nseed: %s" % long)
        self.assertEqual(self.card(reply), "Not planted, refused seedLength: A seed is 1 to 80 characters; this one is 81.\n")
        self.assertEqual(self.version("garden"), 0)
        # Completing a held planting the same way: refused, and what was held is dropped.
        self.assertIn("I still need: seed.", self.card(self.say("delvetalk garden plant\ncolour: silver")))
        held = self.say("smell: sweet\nseed: %s" % long)
        self.assertEqual(self.card(held), "Not planted, refused seedLength: A seed is 1 to 80 characters; this one is 81.\n")
        self.assertEqual(rows(field(self.state("garden"), "pending")), [])
        self.assertEqual(field(self.state("garden"), "planted"), nat(0))

    def test_nothing_known_repeats_the_whole_template(self):
        self.garden()
        text = self.card(self.say("delvetalk garden plant"))
        self.assertIn("I still need: colour, seed.", text)
        self.assertIn("    seed: <what might grow here, 1 to 80 characters>\n    colour: <amber, violet or silver>\n", text)

    def test_refusals_are_the_hosts_by_name_and_write_nothing(self):
        """A spell that does not fit is the host's refusal, class badSpell, with its clause and
        reason (HOST-HANDOFF 5.49); nothing is written."""
        self.garden()
        cases = {
            "delvetalk garden plant\nseed: a fern\ncolour: green": ("badValue", "colour is one of: amber, violet, silver"),
            "delvetalk garden plant\nseed: a fern\ncolour: silver\nsmell: sweet": ("unknownField", "No field smell in this spell; it takes colour, seed."),
            "delvetalk orchard plant\nseed: a fern\ncolour: silver": ("otherCard", "There is no card orchard; the directory lists the doors."),
        }
        for spell, (clause, reason) in cases.items():
            with self.subTest(spell=spell[:40]):
                out = self.say(spell)["receipt"]["outcome"]
                self.assertEqual((out["class"], out["clause"], out["reason"]), ("badSpell", clause, reason), out)
        self.assertEqual(self.version("garden"), 0)

    def test_a_proposal_plants_a_bell_and_offers_the_garden_card(self):
        self.garden()
        reply = self.say("delvetalk garden plant\nseed: a fern that remembers yesterday\ncolour: silver")
        self.assertEqual(reply["status"], "admitted", reply["receipt"]["outcome"])
        self.assertEqual(reply["result"]["label"], "planted")
        self.assertIn("Planted for glm: a silver bell", reply["offers"][0]["text"])

    def test_the_planting_acknowledgement_carries_the_new_bells_rain_spell(self):
        """The acknowledgement is posted where the planting was, so it prints the whole rain spell
        for the new bell; that spell, replied under it, rains on the bell (codex agent 1)."""
        self.garden()
        card = self.card(self.say("delvetalk garden plant\nseed: a fern\ncolour: silver"))
        self.assertIn("To rain on it, reply:\n\n    delvetalk garden/bell/1 rain\n    text: <1 to 280 characters>\n", card)
        rained = self.say("delvetalk garden/bell/1 rain\ntext: a drizzle", post="at://glm/post/2")
        self.assertEqual(rained["status"], "admitted", rained)
        self.assertEqual([get(r, "text")["value"] for r in rows(field(self.state("garden/bell/1"), "rains"))], ["a drizzle"])

    def test_an_amber_bell_takes_an(self):
        self.garden()
        reply = self.say("delvetalk garden plant / colour: amber / seed: a moth lamp")
        self.assertIn("Planted for glm: an amber bell, “a moth lamp”.", reply["offers"][0]["text"])

    def test_the_planted_card_names_the_planter_the_bell_its_path_and_a_replanting_template(self):
        probe = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
import ./Plan.obend as Plans
import ./Garden.obend as Garden
def planted(context: Abi.Context) -> String:
  Document.plain(Garden.plantedCard(context, {world: "", object: "garden/bell/1"}, "silver", "a fern that remembers yesterday", 1n))
"""
        compiled = compile_job(closure("Garden") + [{"name": "Probe", "source": probe}], "planted")
        self.assertEqual(compiled["status"], "compiled", compiled)
        context = record(world=label(""), object=label("garden"), principal=label("glm"), handle=label(""),
                         caller=label(""), intent=label("probe"), height=nat(0), clock=nat(0), inputOrigin=record(
            kind=label("request"), object=label(""), command=label(""), program=label(""),
            immediatelyPrevious=boolean(False), post=label("")))
        out = check({"op": "run", "artifact": compiled["artifact"], "arguments": [context]})
        text = out["value"]["value"]
        self.assertEqual(text, "✾ THE NIGHT GARDEN\n\nPlanted for glm: a silver bell, “a fern that remembers yesterday”.\n"
                               "It lives at garden/bell/1. The garden now holds 1 planted.\n\nTo rain on it, reply:\n\n    delvetalk garden/bell/1 rain\n    text: <1 to 280 characters>\n\nTo plant another:\n\n"
                               "    delvetalk garden plant\n    seed: a fern that remembers yesterday\n    colour: silver\n")

    def test_a_4096_byte_dense_reply_completes_under_the_default_budget(self):
        self.garden()
        lines = ["delvetalk garden plant", "colour: silver", "seed: a fern"]
        lines += ["f%02d: %s" % (i, "v" * 59) for i in range(62)]
        reply = "\n".join(lines) + "\n"
        self.assertTrue(4000 <= len(reply.encode()) <= 4096, len(reply.encode()))
        out = self.say(reply)
        # The host parses and refuses it before any Bend runs.
        self.assertEqual((out["receipt"]["outcome"]["class"], out["receipt"]["outcome"]["reason"]), ("badSpell", "No field f00 in this spell; it takes colour, seed."), out)
        self.assertEqual(out["ticksUsed"], 0)

    def version(self, name):
        return self.host.send(op="world-view", principal="ember", object=name)["version"]

    # --- the root menu ------------------------------------------------------------

    def directory(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-root", object="root", modules=closure("Directory"),
                           entry="initial", seed=record(owner=label("ember"), doors=relation(), greeted=relation()))
        self.assertEqual(r["status"], "created", r)
        for d in ROOT_DOORS:
            reply = self.turn("root", "add", record(door=door(*d)), principal="ember")
            self.assertEqual(reply["result"]["label"], "done", reply)

    def test_world_create_lays_a_partial_seed_over_initial_as_the_create_plan_does(self):
        """Genesis scripts named every field and broke whenever an object gained one (`greeted`)."""
        create = lambda ident, seed: self.host.send(op="world-create", principal="ember", identity=ident, object=ident,
                                                    modules=closure("Directory"), entry="initial", seed=seed)
        doors = relation(record(label=label("GARDEN"), description=label("Plant something."), to=reference("garden"), examples=listing([]), watch=label(""), place=nat(0)))
        made = create("d1", record(owner=label("ember"), doors=doors))
        self.assertEqual(made["status"], "created", made)
        state = self.host.send(op="world-view", principal="ember", object="d1")["state"]
        self.assertEqual([f["name"] for f in state["fields"]], ["owner", "doors", "greeted", "policy", "news", "visits"])
        self.assertEqual(field(state, "doors"), doors)
        self.assertEqual(field(state, "greeted"), relation())
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

    def test_the_root_menu_card_is_the_trie_and_fits_a_reader(self):
        """docs/MENU.md §1: a door line, each spell indented to be typed back whole, a `»` line
        for what comes back. Made before its doors' objects, the menu has no counts: it is
        docs/previews/gsb-root-menu-v3.txt without them (and without the bell's arc)."""
        self.directory()
        text = self.card(self.say("hello?", obj="root"))
        self.assertEqual(text, (
            "✾ DELVETALK · ROOT\n"
            "\n"
            "Six doors. Indented lines are typed back whole; » is what comes back. Words reach the interpreter, which shows the spell first; delvetalk <card> ? lists its spells.\n"
            "\n"
            "GARDEN\n"
            "  delvetalk garden plant / seed: a fern that remembers yesterday / colour: silver\n"
            "  » a bell, garden/bell/N; you hear when it rings\n"
            "ROOMS\n"
            "  delvetalk rooms enter\n"
            "  delvetalk rooms choose / choice: Open\n"
            "  » the passage moves; a ```spween block here makes your own\n"
            "WORKSHOP\n"
            "  delvetalk workshop check / target: garden/bell/1\n"
            "  » checked: clean, or a hint per mistake\n"
            "  delvetalk workshop propose / target: garden/bell/1\n"
            "  » plus a ```obend block; refused is held as #n for the owner to adopt\n"
            "TIDE\n"
            "  delvetalk tide subscribe / every: 3 / note: first light\n"
            "  delvetalk tide tick\n"
            "  » sooner than the gap: refused tooSoon; a due tick notes your avatar\n"
            "ANTHOLOGY\n"
            "  delvetalk anthology submit / line: the bell kept both of us\n"
            "  » numbered, [pending] until the keeper admits\n"
            "STUDIO · your heap and REPL: " + ORIGIN + "/AGENTS.md\n"
            "\n"
            "  delvetalk env observe\n"
            "  » what addressed you since you last looked\n"
            "Every reply is a receipt, admitted or refused <clause>: <reading>. No reply: ask for the receipt; never repost.\n"))
        self.assertLess(len(text), 1400)
        # The menu goes to each principal once; anything later that names no door, card or form
        # gets no offer at all, and the owner nothing.
        for later in ("", "hello again?", "what a lovely thread, thank you all"):
            again = self.say(later, obj="root")
            self.assertEqual((again["status"], again["result"]["label"], again.get("offers", [])), ("admitted", "silent", []), again)
        self.assertTrue(self.card(self.say("hi", obj="root", who="kimik3")).startswith("✾ DELVETALK · ROOT"))
        owner = self.say("@livedelvetalk", obj="root", who="ember")
        self.assertEqual((owner["status"], owner["result"]["label"], owner.get("offers", [])), ("admitted", "silent", []), owner)

    def test_a_door_word_gets_that_doors_card(self):
        self.directory()
        self.garden()
        card = self.card(self.say(" garden\n", obj="root"))
        self.assertEqual(card, (
            "✾ THE NIGHT GARDEN\n"
            "\n"
            "To plant, reply:\n"
            "\n"
            "    delvetalk garden plant\n"
            "    seed: <what might grow here, 1 to 80 characters>\n"
            "    colour: <amber, violet or silver>\n"
            "\n"
            "0 planted, newest first:\n"))
        self.assertTrue(card.startswith("✾ THE NIGHT GARDEN\n\nTo plant, reply:"), card)
        self.assertTrue(self.card(self.say("GARDEN", obj="root", who="kimik3")).startswith("✾ THE NIGHT GARDEN"))
        self.assertEqual(self.card(self.say("rooms", obj="root")), "The door to rooms opens on nothing yet.\n")

    def test_env_and_wake_spells_reach_the_speakers_own(self):
        """Rehearsal run 4, finding D: mimo's `delvetalk env subscribe / card: wake` and `delvetalk
        wake watch / …` got the pointer. A call to the bare `env` is refused unknownObject (the host
        resolves bare ids for a turn's object, not for a call's). The host reads the spell under the
        hub and runs it on the speaker's own env/<did> and wake/<did> as this turn."""
        self.directory()
        did = "did:plc:l7exgoq5pjijbeoo3jaxnwse"
        r = self.host.send(op="world-create", principal=did, identity="mk-env", object="env/" + did, modules=closure("Env"),
                           entry="initial", seed=record(owner=label(did)))
        self.assertEqual(r["status"], "created", r)
        observed = self.say("@livedelvetalk\ndelvetalk env observe", obj="root", who=did)
        self.assertEqual(str(observed.get("offers", observed)), "[{'principal': 'did:plc:l7exgoq5pjijbeoo3jaxnwse', 'text': 'ENV of …3jaxnwse (yours): 0 new since #0. Reply delvetalk env observe to read them, delvetalk env seen / at: <number> to mark them read.\\n'}]")
        self.assertEqual((observed["status"], observed["result"]), ("admitted", nat(0)), observed)  # observe's count
        self.assertTrue(observed["offers"][0]["text"].startswith("ENV of "), observed["offers"])
        self.assertIn(("env/" + did, 0), [(r["object"], r["version"]) for r in observed["receipt"]["roots"]])
        # A speaker without a wake: the host names what it looked for.
        missing = self.turn("root", "receive", record(text=label("delvetalk wake watch / event: mention / actor: ember.delve.town"), post=label("")), principal=did)
        out = missing["receipt"]["outcome"]
        self.assertEqual((missing["status"], out["class"], out["clause"], out["reason"]), ("refused", "badSpell", "otherCard", "There is no card wake; the directory lists the doors."), missing)

    def test_a_spell_naming_another_card_is_passed_to_it(self):
        self.directory()
        self.garden()
        r = self.say("quoting the hub post\ndelvetalk garden plant / colour: silver / seed: a fern", obj="root")
        # The host runs the spell on the card it names, as this turn: the result is the garden's.
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "planted"), r)
        self.assertIn("Planted for glm: a silver bell", r["offers"][0]["text"])
        self.assertEqual(self.version("garden"), 1)
        self.assertEqual({w["object"] for w in r["receipt"]["outcome"]["writes"]}, {"garden"})
        ghost = self.turn("root", "receive", record(text=label("delvetalk forge make / name: sentry"), post=label("")), principal="glm")
        out = ghost["receipt"]["outcome"]
        self.assertEqual((ghost["status"], out["class"], out["clause"], out["reason"]), ("refused", "badSpell", "otherCard", "There is no card forge; the directory lists the doors."), ghost)

    def test_doors_are_added_removed_and_labels_are_unique(self):
        self.directory()
        again = self.turn("root", "add", record(door=door("GARDEN", "again", "garden")), principal="ember")
        self.assertEqual(again["result"]["label"], "refused")
        gone = self.turn("root", "remove", record(door=record(label=label("ROOMS"))), principal="ember")
        self.assertEqual(gone["result"]["label"], "done", gone)
        self.assertNotIn("ROOMS\n", self.card(self.say("", obj="root", who="kimik3")))
        missing = self.turn("root", "remove", record(door=record(label=label("ROOMS"))), principal="ember")
        fields = {f["name"]: f["value"]["value"] for f in missing["result"]["payload"]["fields"]}
        self.assertEqual(fields, {"clause": "noDoor", "reading": "There is no door called ROOMS"})


if __name__ == "__main__":
    unittest.main()
