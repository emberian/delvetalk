"""The garden and the root directory answer spells with cards: needs named, refusals in one line, the
menu once per principal, door words, spells passed on.

Evidence for FOUNDATION §5 (layer: objects).

The cards the town sees first: Garden.receive and Directory.receive.

Every observed spell reaches `<card>.receive {text, post}`; who wrote it is the turn's
principal, and the reply card is what the turn offers.
"""
import unittest

from deploy.genesis import DOORS
from tests.test_chain import Chain, garden_seed, town_kinds
from tests.wire import field, label, listing, nat, record, reference, relation, rows
from tests.bend import closure

ROOT_DOORS = DOORS  # (label, description, object, watched field, [(spell, what comes back)])


def door(label_, description, to, watch="", examples=()):
    """A Directory `Door`: its spells and `»` lines, and the field of its object the door line counts."""
    return record(label=label(label_), description=label(description), to=reference(to),
                  examples=listing(record(example=label(e), comes=label(c)) for e, c in examples), watch=label(watch))


class Cards(Chain):
    def garden(self):
        self.make("garden", closure("Garden"), garden_seed())
        town_kinds(self.host.send)

    def say(self, text, who="glm", post="at://glm/post/1", obj="garden", method="receive"):
        return self.turn(obj, method, record(text=label(text), post=label(post)), principal=who)

    def card(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(len(reply["offers"]), 1, reply)
        return reply["offers"][0]["text"]


    def test_a_completed_seed_keeps_the_forms_eighty_characters(self):
        """Completing a held planting is held to the plant form's bounds: an 81-character seed is
        refused by name and what was held is dropped (codex objects 11; the direct 81-character
        planting is test_scenarios.Garden)."""
        self.garden()
        long = "x" * 81
        # Completing a held planting the same way: refused, and what was held is dropped.
        self.assertIn("I still need: seed.", self.card(self.say("delvetalk garden plant\ncolour: silver")))
        held = self.say("smell: sweet\nseed: %s" % long)
        self.assertEqual(self.card(held), "Not planted, refused seedLength: A seed is 1 to 80 characters; this one is 81.\n")
        self.assertEqual(rows(field(self.state("garden"), "pending")), [])
        self.assertEqual(field(self.state("garden"), "planted"), nat(0))


    def test_a_misfit_spell_is_the_gardens_to_answer_and_a_plain_card_still_refuses_badSpell(self):
        """The garden's receive takes a direct turn's misfit (HOST-HANDOFF 121): with no policy it
        answers by a refusal card naming the clause, an admitted turn that writes nothing. A card
        whose receive takes a plain Card.Reply (a bell) still has the host refuse it badSpell."""
        self.garden()
        cases = {
            "delvetalk garden plant\nseed: a fern\ncolour: green": ("badValue", "colour is one of: amber, violet, silver"),
            "delvetalk garden plant\nseed: a fern\ncolour: silver\nsmell: sweet": ("unknownField", "No field smell in this spell; it takes colour, seed."),
            "delvetalk orchard plant\nseed: a fern\ncolour: silver": ("otherCard", "There is no card orchard; the directory lists the doors."),
        }
        for spell, (clause, reason) in cases.items():
            with self.subTest(spell=spell[:40]):
                reply = self.say(spell)
                self.assertEqual((reply["status"], reply["receipt"]["outcome"]["tag"], reply["receipt"]["outcome"]["writes"]), ("admitted", "admitted", []), reply)
                self.assertEqual(reply["result"]["label"], "refused", reply)
                self.assertEqual([f["value"]["value"] for f in reply["result"]["payload"]["fields"]], [clause, reason], reply)
                self.assertIn("refused %s: %s\n" % (clause, reason), self.card(reply))
        self.assertEqual(self.version("garden"), 0)
        self.say("delvetalk garden plant\nseed: a fern\ncolour: silver")
        for spell, clause in (("delvetalk garden/bell/1 rain\ntext: x\nsmell: sweet", "unknownField"), ("delvetalk orchard rain\ntext: x", "otherCard")):
            with self.subTest(spell=spell[:40]):
                out = self.say(spell, obj="garden/bell/1")["receipt"]["outcome"]
                self.assertEqual((out["class"], out["clause"]), ("badSpell", clause), out)


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
        self.assertEqual([f["name"] for f in state["fields"]], ["owner", "doors", "greeted", "policy", "news", "visits", "missed"])
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
        self.assertEqual((observed["status"], observed["result"]), ("admitted", nat(0)), observed)  # observe's count
        self.assertTrue(observed["offers"][0]["text"].startswith("ENV of "), observed["offers"])
        self.assertIn(("env/" + did, 0), [(r["object"], r["version"]) for r in observed["receipt"]["roots"]])
        # A speaker without a wake: the spell is a misfit the directory takes; with no policy it
        # refuses by the clause, and writes no greeting.
        missing = self.turn("root", "receive", record(text=label("delvetalk wake watch / event: mention / actor: ember.delve.town"), post=label("")), principal=did)
        self.assertEqual((missing["status"], missing["result"]["label"]), ("admitted", "refused"), missing)
        self.assertEqual([f["value"]["value"] for f in missing["result"]["payload"]["fields"]], ["otherCard", "There is no card wake; the directory lists the doors."], missing)
        self.assertEqual(missing["offers"][0]["text"], "✾ DELVETALK · ROOT\n\nrefused otherCard: There is no card wake; the directory lists the doors.\n")

    def test_a_spell_naming_another_card_is_passed_to_it(self):
        self.directory()
        self.garden()
        r = self.say("quoting the hub post\ndelvetalk garden plant / colour: silver / seed: a fern", obj="root")
        # The host runs the spell on the card it names, as this turn: the result is the garden's.
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "planted"), r)
        self.assertIn("Planted, glm: a silver bell", r["offers"][0]["text"])
        self.assertEqual(self.version("garden"), 1)
        self.assertEqual({w["object"] for w in r["receipt"]["outcome"]["writes"]}, {"garden", "kind/bell"})
        # No card forge: the directory is the answering card and takes the misfit; with no policy it
        # refuses by the clause (an admitted turn, no greeting written), never badSpell.
        ghost = self.turn("root", "receive", record(text=label("delvetalk forge make / name: sentry"), post=label("")), principal="glm")
        self.assertEqual((ghost["status"], ghost["result"]["label"], ghost["receipt"]["outcome"]["writes"]), ("admitted", "refused", []), ghost)
        self.assertEqual([f["value"]["value"] for f in ghost["result"]["payload"]["fields"]], ["otherCard", "There is no card forge; the directory lists the doors."], ghost)
        self.assertEqual(self.card(ghost), "✾ DELVETALK · ROOT\n\nrefused otherCard: There is no card forge; the directory lists the doors.\n")

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
