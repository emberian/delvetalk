"""The garden and the commonplace answer spells with cards: needs named, refusals in one line, the
menu once per principal, door words, spells passed on.

Evidence for FOUNDATION §5 (layer: objects).

The cards the town sees first: the garden's receive (a record's) and the commonplace's receive.

Every observed spell reaches `<card>.receive {text, post}`; who wrote it is the turn's
principal, and the reply card is what the turn offers.
"""
import unittest

from deploy import genesis
from deploy.genesis import DOORS, STUDIO
from tests.test_chain import Chain, town_garden
from tests.wire import cast_refusal, field, result_label, label, listing, nat, record, reference
from tests.bend import closure

ROOT_DOORS = DOORS  # (label, object, [(spell, what comes back)])


def door(label_, to, examples=(), description=""):
    """A `Card.Doorway` as the commonplace cites it: its spells and `»` lines under the door's line."""
    return record(label=label(label_), to=reference(to), description=label(description),
                  examples=listing(record(example=label(e), comes=label(c)) for e, c in examples))


def commonplace(chain, policy="", doors=ROOT_DOORS, studio=True, owner="ember", **more):
    """The town's first card as genesis makes it: a Record the owner keeps, citing the doors, with the commonplace's body laid over it."""
    cites = [door(*d) for d in doors] + ([door(STUDIO[0], "", (), STUDIO[1])] if studio else [])
    r = chain.host.send(op="world-create", principal=owner, identity="mk-commonplace", object="commonplace",
                        modules=closure("Menu", "Mentions", "Policies", "Record"),  # the library, which the body imports from
                        entry="initial", law=genesis.RECORD_LAW,
                        seed=record(owner=label(owner), keeper=label(owner), keeperHandle=label("ember.delve.town"), head=label("THE COMMONPLACE"),
                                    policy=reference(policy), cites=listing(cites), **more))
    chain.assertEqual(r["status"], "created", r)
    r = chain.host.send(op="world-reprogram", principal=owner, identity="body-commonplace", object="commonplace", version=0,
                        package=genesis.body_of("commonplace"), mode="extend")
    chain.assertEqual(r["status"], "admitted", r)


class Cards(Chain):
    def garden(self):
        town_garden(self.host.send)

    def say(self, text, who="glm", post="at://glm/post/1", obj="garden", method="receive"):
        return self.turn(obj, method, record(text=label(text), post=label(post)), principal=who)

    def card(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(len(reply["offers"]), 1, reply)
        return reply["offers"][0]["text"]


    def test_a_misfit_spell_to_a_card_that_reads_no_words_is_the_hosts_badSpell_with_the_usage(self):
        """HOST-HANDOFF 5.153: only a card whose state names a policy hears a misfit; the garden, a bell
        and the tide name none, so each misfit is refused badSpell with its clause, reason and the
        card's usage, and nothing is written, whatever their `receive` takes."""
        self.garden()
        laid = self.version("garden")
        cases = {
            "delvetalk garden plant\nseed: a fern\ncolour: green": ("badValue", "colour is one of: amber, violet, silver"),
            "delvetalk orchard plant\nseed: a fern\ncolour: silver": ("otherCard", "There is no card orchard; the commonplace lists the doors."),
        }
        for spell, (clause, reason) in cases.items():
            with self.subTest(spell=spell[:40]):
                out = self.say(spell)["receipt"]["outcome"]
                self.assertEqual((out["class"], out["clause"], out["reason"]), ("badSpell", clause, reason), out)
                self.assertIn("delvetalk garden plant", out["hint"])
        self.assertEqual(self.version("garden"), laid)
        # A line whose name the form lacks ends the fields (the second playtest's D7): the spell above it runs.
        planted = self.say("delvetalk garden plant\nseed: a fern\ncolour: silver\nhob: still owed — a note for later")
        self.assertNotEqual(planted["receipt"]["outcome"]["writes"], [], planted)
        self.make("tide", closure("Tide"), record(gap=nat(1)))
        for card in ("garden/bell/1", "tide"):
            with self.subTest(card=card):
                out = self.say("delvetalk orchard rain\ntext: x", obj=card)["receipt"]["outcome"]
                self.assertEqual((out["class"], out["clause"]), ("badSpell", "otherCard"), out)


    def version(self, name):
        return self.host.send(op="world-view", principal="ember", object=name)["version"]

    # --- the root menu ------------------------------------------------------------

    def directory(self):
        commonplace(self)

    def test_world_create_lays_a_partial_seed_over_initial_as_the_create_plan_does(self):
        """Genesis scripts named every field and broke whenever an object gained one."""
        create = lambda ident, seed: self.host.send(op="world-create", principal="ember", identity=ident, object=ident,
                                                    modules=closure("Record"), entry="initial", seed=seed, law=genesis.RECORD_LAW)
        cites = listing([door("GARDEN", "garden", [], "Plant something.")])
        made = create("d1", record(owner=label("ember"), cites=cites))
        self.assertEqual(made["status"], "created", made)
        state = self.host.send(op="world-view", principal="ember", object="d1")["state"]
        names = [f["name"] for f in state["fields"]]
        self.assertEqual(names[-2:], ["tended", "tendedAt"])
        self.assertEqual(field(state, "cites"), cites)
        self.assertEqual(made["receipt"]["outcome"]["seed"], state)    # the journal keeps the whole state
        # {cites} alone: a seed that does not set `owner` gets the creating principal, so the
        # creator owns what it makes and the law's dry run admits it.
        alone = create("d2", record(cites=cites))
        self.assertEqual(alone["status"], "created", alone)
        mine = self.host.send(op="world-view", principal="ember", object="d2")["state"]
        self.assertEqual((field(mine, "owner"), field(mine, "cites")), (label("ember"), cites))
        theirs = self.host.send(op="world-create", principal="kimik3", identity="d4", object="d4",
                                modules=closure("Record"), entry="initial", seed=record(), law=genesis.RECORD_LAW)
        self.assertEqual(theirs["status"], "created", theirs)
        self.assertEqual(field(self.host.send(op="world-view", principal="ember", object="d4")["state"], "owner"), label("kimik3"))
        # A seed that names its owner keeps it (and the metarule judges that owner's law).
        named = create("d5", record(owner=label("glm"), cites=cites))
        self.assertEqual(named["status"], "error", named)
        self.assertTrue(named["message"].startswith("law does not admit an amendment by its proposer ember: owner: "), named)
        stray = create("d3", record(owner=label("ember"), colour=label("amber")))
        self.assertEqual(stray, {"status": "error", "message": "typeMismatch: the seed names a field the state does not have"})
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="d1")["state"], state)


    def test_a_spell_naming_another_card_is_passed_to_it(self):
        self.directory()
        self.garden()
        laid = self.version("garden")
        r = self.say("quoting the hub post\ndelvetalk garden plant / colour: silver / seed: a fern", obj="commonplace")
        # The host runs the spell on the card it names, as this turn: the result is the garden's.
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "made"), r)
        self.assertIn("Planted, glm: a silver bell", r["offers"][0]["text"])
        self.assertEqual(self.version("garden"), laid + 1)
        self.assertEqual({w["object"] for w in r["receipt"]["outcome"]["writes"]}, {"garden", "kind/bell"})
        # No card forge: with no policy the commonplace reads no words, so the misfit is the host's
        # badSpell (HOST-HANDOFF 5.153); with one, hob is shown it (test_policy).
        ghost = self.turn("commonplace", "receive", record(text=label("delvetalk forge make / name: sentry"), post=label("")), principal="glm")
        out = ghost["receipt"]["outcome"]
        self.assertEqual((ghost["status"], out["class"], out["clause"], out["reason"]),
                         ("refused", "badSpell", "otherCard", "There is no card forge; the commonplace lists the doors."), ghost)

    def test_doors_are_hung_removed_and_labels_are_unique(self):
        self.directory()
        again = self.turn("commonplace", "door", record(label=label("GARDEN"), to=label("garden")), principal="ember")
        self.assertEqual(result_label(again), "refused", again)
        stranger = self.turn("commonplace", "undoor", record(label=label("ROOMS")), principal="kimik3")
        self.assertEqual(result_label(stranger), "refused", stranger)
        gone = self.turn("commonplace", "undoor", record(label=label("ROOMS")), principal="ember")
        self.assertEqual(gone["result"]["label"], "done", gone)
        self.assertNotIn("ROOMS\n", self.card(self.say("", obj="commonplace", who="kimik3")))
        missing = self.turn("commonplace", "undoor", record(label=label("ROOMS")), principal="ember")
        self.assertEqual(cast_refusal(missing)[0], "noDoor", missing)


if __name__ == "__main__":
    unittest.main()
