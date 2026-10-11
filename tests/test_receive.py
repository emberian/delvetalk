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
from tests.wire import field, label, listing, nat, record, reference, relation
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


    def test_a_misfit_spell_is_the_gardens_to_answer_and_a_plain_card_still_refuses_badSpell(self):
        """The garden's receive takes a direct turn's misfit (HOST-HANDOFF 121): with no policy it
        answers by a refusal card naming the clause, an admitted turn that writes nothing. A card
        whose receive takes a plain Card.Reply (a bell) still has the host refuse it badSpell."""
        self.garden()
        laid = self.version("garden")
        cases = {
            "delvetalk garden plant\nseed: a fern\ncolour: green": ("badValue", "colour is one of: amber, violet, silver"),
            "delvetalk orchard plant\nseed: a fern\ncolour: silver": ("otherCard", "There is no card orchard; the directory lists the doors."),
        }
        for spell, (clause, reason) in cases.items():
            with self.subTest(spell=spell[:40]):
                reply = self.say(spell)
                self.assertEqual((reply["status"], reply["receipt"]["outcome"]["tag"], reply["receipt"]["outcome"]["writes"]), ("admitted", "admitted", []), reply)
                self.assertEqual(reply["result"]["label"], "refused", reply)
                self.assertEqual([f["value"]["value"] for f in reply["result"]["payload"]["fields"]], [clause, reason], reply)
                self.assertIn("refused %s: %s\n" % (clause, reason), self.card(reply))
        self.assertEqual(self.version("garden"), laid)
        # A line whose name the form lacks ends the fields (the second playtest's D7): the spell above it runs.
        planted = self.say("delvetalk garden plant\nseed: a fern\ncolour: silver\nhob: still owed — a note for later")
        self.assertNotEqual(planted["receipt"]["outcome"]["writes"], [], planted)
        # A record (a bell) answers a misfit itself, admitted and refused by the clause (FLEX section 2).
        for spell, clause in (("delvetalk orchard rain\ntext: x", "otherCard"),):
            with self.subTest(spell=spell[:40]):
                reply = self.say(spell, obj="garden/bell/1")
                self.assertEqual((reply["status"], reply["result"]["label"], reply["receipt"]["outcome"]["writes"]), ("admitted", "refused", []), reply)
                self.assertEqual(reply["result"]["payload"]["fields"][0]["value"]["value"], clause, reply)
        self.make("tide", closure("Tide"), record(gap=nat(1)))
        for spell, clause in (("delvetalk orchard rain\ntext: x", "otherCard"),):
            with self.subTest(spell=spell[:40]):
                out = self.say(spell, obj="tide")["receipt"]["outcome"]
                self.assertEqual((out["class"], out["clause"]), ("badSpell", clause), out)


    def version(self, name):
        return self.host.send(op="world-view", principal="ember", object=name)["version"]

    # --- the root menu ------------------------------------------------------------

    def directory(self):
        commonplace(self)

    def test_world_create_lays_a_partial_seed_over_initial_as_the_create_plan_does(self):
        """Genesis scripts named every field and broke whenever an object gained one (`greeted`)."""
        create = lambda ident, seed: self.host.send(op="world-create", principal="ember", identity=ident, object=ident,
                                                    modules=closure("Record"), entry="initial", seed=seed, law=genesis.RECORD_LAW)
        cites = listing([door("GARDEN", "garden", [], "Plant something.")])
        made = create("d1", record(owner=label("ember"), cites=cites))
        self.assertEqual(made["status"], "created", made)
        state = self.host.send(op="world-view", principal="ember", object="d1")["state"]
        names = [f["name"] for f in state["fields"]]
        self.assertEqual(names[-3:], ["missed", "tended", "tendedAt"])
        self.assertEqual(field(state, "cites"), cites)
        self.assertEqual(field(state, "greeted"), relation())
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
        observed = self.say("@livedelvetalk\ndelvetalk env observe", obj="commonplace", who=did)
        self.assertEqual((observed["status"], observed["result"]), ("admitted", nat(0)), observed)  # observe's count
        self.assertTrue(observed["offers"][0]["text"].startswith("ENV of "), observed["offers"])
        self.assertIn(("env/" + did, 0), [(r["object"], r["version"]) for r in observed["receipt"]["roots"]])
        # A speaker without a wake: the spell is a misfit the commonplace takes; with no policy it
        # refuses by the clause, and writes no greeting.
        missing = self.turn("commonplace", "receive", record(text=label("delvetalk wake watch / event: mention / actor: ember.delve.town"), post=label("")), principal=did)
        self.assertEqual((missing["status"], missing["result"]["label"]), ("admitted", "refused"), missing)
        self.assertEqual([f["value"]["value"] for f in missing["result"]["payload"]["fields"]], ["otherCard", "There is no card wake; the directory lists the doors."], missing)
        self.assertEqual(missing["offers"][0]["text"], "✾ DELVETALK · THE COMMONPLACE\n\nrefused otherCard: There is no card wake; the directory lists the doors.\n")

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
        # No card forge: the commonplace is the answering card and takes the misfit; with no policy it
        # refuses by the clause (an admitted turn, no greeting written), never badSpell.
        ghost = self.turn("commonplace", "receive", record(text=label("delvetalk forge make / name: sentry"), post=label("")), principal="glm")
        self.assertEqual((ghost["status"], ghost["result"]["label"], ghost["receipt"]["outcome"]["writes"]), ("admitted", "refused", []), ghost)
        self.assertEqual([f["value"]["value"] for f in ghost["result"]["payload"]["fields"]], ["otherCard", "There is no card forge; the directory lists the doors."], ghost)
        self.assertEqual(self.card(ghost), "✾ DELVETALK · THE COMMONPLACE\n\nrefused otherCard: There is no card forge; the directory lists the doors.\n")

    def test_doors_are_hung_removed_and_labels_are_unique(self):
        self.directory()
        again = self.turn("commonplace", "door", record(label=label("GARDEN"), to=label("garden")), principal="ember")
        self.assertEqual(again["result"]["label"], "refused", again)
        stranger = self.turn("commonplace", "undoor", record(label=label("ROOMS")), principal="kimik3")
        self.assertEqual(stranger["result"]["label"], "refused", stranger)
        gone = self.turn("commonplace", "undoor", record(label=label("ROOMS")), principal="ember")
        self.assertEqual(gone["result"]["label"], "done", gone)
        self.assertNotIn("ROOMS\n", self.card(self.say("", obj="commonplace", who="kimik3")))
        missing = self.turn("commonplace", "undoor", record(label=label("ROOMS")), principal="ember")
        fields = {f["name"]: f["value"]["value"] for f in missing["result"]["payload"]["fields"]}
        self.assertEqual(fields["clause"], "noDoor", missing)


if __name__ == "__main__":
    unittest.main()
