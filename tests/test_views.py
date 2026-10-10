"""Render with a point of view (FOUNDATION section 13, row 3): render(state, context) is the
card as the reader in the context sees it. A member sees more than a stranger; the planter sees
"(yours)". The card a non-acting reply gets is the reader's, so these drive real world-turns
with an empty reply by different principals, and through world-card, which renders for its reader.

Refuted by: a stranger's card showing an Env's event text, a Wake's triggers or an Avatar's notes;
the planter's card lacking "(yours)"; a party's card lacking its countersign spell."""
import unittest

from tests import test_chain, test_deal
from tests.test_chain import boolean, nil, reference
from tests.test_objects import closure
from tests.test_places import avatar_seed, listing
from tests.test_turn_world import label, nat, record
from tests.test_wakes import event

GLM, KIM = "did:plc:glm", "did:plc:kimik3"


def heard(text=""):
    return record(text=label(text), post=label(""), slot=label(""))


def silver():
    return {"tag": "variant", "label": "silver", "payload": record()}


class Views(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def card(self, name, principal):
        reply = self.turn(name, "receive", heard(), principal=principal)
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["offers"][0]["text"]

    def world_card(self, name, principal="ember"):
        r = self.host.send(op="world-card", principal=principal, object=name)
        self.assertEqual(r["status"], "card", r)
        return r["text"]

    def test_the_planter_sees_yours_and_nobody_else_does(self):
        self.make("bell", closure("Bell"), record(colour=silver(), seed=label("a bell for lost moths"),
                                                  planting=label("p"), planter=label(GLM), planterHandle=label("")))
        mine, theirs = self.card("bell", GLM), self.card("bell", KIM)
        print("\n--- bell, planter ---\n" + mine + "--- bell, stranger ---\n" + theirs)
        self.assertTrue(mine.startswith("A silver bell planted by glm (yours): a bell for lost moths (silent)\n"), mine)
        self.assertTrue(theirs.startswith("A silver bell planted by glm: a bell for lost moths (silent)\n"), theirs)
        self.assertNotIn("(yours)", self.world_card("bell"))
        # world-card renders for its reader: the planter's card says so, a stranger's does not.
        self.assertTrue(self.world_card("bell", GLM).startswith("A silver bell planted by glm (yours): a bell for lost moths"))
        self.assertNotIn("(yours)", self.world_card("bell", KIM))

    def test_an_env_shows_its_events_to_its_owner_only(self):
        r = self.host.send(op="world-create", principal=GLM, identity="mk-env", object="env/" + GLM, modules=closure("Env"),
                           entry="initial", seed=record(owner=label(GLM), buffer=nil(), seen=nat(0), subscribers=nil()))
        self.assertEqual(r["status"], "created", r)
        self.assertEqual(self.turn("env/" + GLM, "publish", record(event=event(text="a secret mention")), principal=GLM)["status"], "admitted")
        mine, theirs = self.card("env/" + GLM, GLM), self.card("env/" + GLM, KIM)
        print("\n--- env, owner ---\n" + mine + "--- env, stranger ---\n" + theirs)
        self.assertIn("a secret mention", mine)
        self.assertIn("ENV of glm (yours): 1 new since #0\n", mine)
        self.assertNotIn("a secret mention", theirs)
        self.assertIn("ENV of glm: 1 new since #0\n", theirs)
        self.assertNotIn("a secret mention", self.world_card("env/" + GLM))
        # observe offers the reader's card too: a stranger looking learns the count only.
        look = self.turn("env/" + GLM, "observe", principal=KIM)
        self.assertNotIn("a secret mention", look["offers"][0]["text"])

    def test_an_avatars_notes_are_its_principals(self):
        self.make(GLM, closure("Avatar"), avatar_seed("glm", "porch"))
        self.assertEqual(self.turn(GLM, "note", record(text=label("meet at the gate")), principal=KIM)["status"], "admitted")
        mine, theirs = self.card(GLM, GLM), self.card(GLM, KIM)
        print("\n--- avatar, own ---\n" + mine + "--- avatar, other ---\n" + theirs)
        self.assertIn("kimik3: meet at the gate\n", mine)
        self.assertNotIn("meet at the gate", theirs)
        self.assertIn("glm is at porch\n0 following, follows 0\n1 note\n", theirs)

    def test_a_reader_with_a_proposal_waiting_is_reminded_of_it(self):
        spell = "    delvetalk garden plant\n    seed: a moth\n    colour: violet\n"
        self.make("garden", closure("Garden"), record(policy=reference(""), confirmFor={"tag": "list", "items": [label("plant")]},
                                                      pending=listing([record(principal=label("glm"), spell=label(spell), needs={"tag": "list", "items": []})])))
        mine, theirs = self.card("garden", "glm"), self.card("garden", "kimik3")
        print("\n--- garden, glm waiting ---\n" + mine)
        self.assertTrue(mine.startswith("✾ THE NIGHT GARDEN\n\nglm, this waits for your yes:\n\n" + spell + "\nTo plant, reply:\n"), mine)
        self.assertTrue(theirs.startswith("✾ THE NIGHT GARDEN\n\nTo plant, reply:\n\n    delvetalk garden plant\n"), theirs)
        # Showing the card drops nothing.
        self.assertEqual(len([f for f in self.state("garden")["fields"] if f["name"] == "pending"][0]["value"]["items"]), 1)


class Handles(test_chain.Chain):
    """Rehearsal finding 8: a card never shows a raw DID. A real did:plc (24 characters after the
    method) shows as "…" and its last eight; a short test DID shows whole."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def test_a_real_did_is_shown_by_its_last_eight(self):
        did = "did:plc:a5uoyxqts4y3iwo2dk74ygma"
        r = self.host.send(op="world-create", principal=did, identity="mk-env", object="env/" + did, modules=closure("Env"),
                           entry="initial", seed=record(owner=label(did), buffer=nil(), seen=nat(0), subscribers=nil()))
        self.assertEqual(r["status"], "created", r)
        card = self.turn("env/" + did, "receive", heard(), principal="did:plc:zero")["offers"][0]["text"]
        self.assertTrue(card.startswith("ENV of …dk74ygma: 0 new since #0\n"), card)
        self.assertNotIn("a5uoyxqts4y3iwo2dk74ygma", card.split("Reply with a spell")[0])


class ObservedHandles(test_chain.Chain):
    """A card names its reader by the handle the host's registry holds (context.handle, filled by
    the clock principal with world-principal); anyone else by "…" and the DID's last eight."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    DID = "did:plc:nmjdxe6fex23zslnnbwgruj3"

    def test_the_reader_sees_their_handle_and_a_stranger_the_last_eight(self):
        opened = self.host.send(op="world-open", path=self.path, clock="transport")
        self.assertEqual(opened["status"], "opened", opened)
        self.make("bell", closure("Bell"), record(colour=silver(), seed=label("moths"),
                                                  planting=label("p"), planter=label(self.DID), planterHandle=label("")))
        self.assertEqual(self.card("bell", self.DID).split("\n")[0], "A silver bell planted by …gbruj3 (yours): moths (silent)".replace("…gbruj3", "…" + self.DID[-8:]))
        r = self.host.send(op="world-principal", principal="transport", did=self.DID, handle="glm.delve.town")
        self.assertEqual(r["status"], "principal", r)
        mine = self.card("bell", self.DID).split("\n")[0]
        theirs = self.card("bell", KIM).split("\n")[0]
        print("\n--- bell, its planter with a handle ---\n" + mine + "\n--- a stranger ---\n" + theirs)
        self.assertEqual(mine, "A silver bell planted by glm.delve.town (yours): moths (silent)")
        self.assertEqual(theirs, "A silver bell planted by …%s: moths (silent)" % self.DID[-8:])

    def card(self, name, principal):
        reply = self.turn(name, "receive", heard(), principal=principal)
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["offers"][0]["text"]


class StoredHandles(test_chain.Chain):
    """Run 5, finding 7: a bell's card showed its planter as a DID fragment to everyone but the
    planter. Objects store the handle the host knew beside each principal (planterHandle from the
    planting turn's context.handle, a rain's and an anthology line's handle), and Card.shown
    prefers it."""
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    GLM, KIMI = "did:plc:nmjdxe6fex23zslnnbwgruj3", "did:plc:j2hnfjwlnm2mau24vnmpir6d"

    def test_strangers_read_the_planter_and_the_rains_by_handle(self):
        self.assertEqual(self.host.send(op="world-open", path=self.path, clock="transport")["status"], "opened")
        for did, handle in ((self.GLM, "glm.delve.town"), (self.KIMI, "kimik3.delve.town")):
            self.assertEqual(self.host.send(op="world-principal", principal="transport", did=did, handle=handle)["status"], "principal")
        self.make("garden", closure("Garden"), record(owner=label("ember")))
        planted = self.turn("garden", "receive", record(text=label("plant: a lamp for moths\ncolour: amber"), post=label("at://x/p")), principal=self.GLM)
        self.assertEqual(planted["result"]["label"], "planted", planted)
        self.assertEqual(self.turn("garden/bell/1", "receive", record(text=label("rain: drizzle"), post=label("at://x/r")), principal=self.KIMI)["result"]["label"], "done")
        card = self.turn("garden/bell/1", "receive", heard(), principal="did:plc:zero")["offers"][0]["text"]
        print("\n--- bell, read by a stranger ---\n" + card)
        self.assertTrue(card.startswith("An amber bell planted by glm.delve.town: a lamp for moths (silent)\nkimik3.delve.town: drizzle\n"), card)
        r = self.host.send(op="world-create", principal="ember", identity="mk-a", object="anthology", modules=closure("Anthology"),
                           entry="initial", seed=record(owner=label("ember")))
        self.assertEqual(r["status"], "created", r)
        self.turn("anthology", "receive", record(text=label("submit: moths"), post=label("at://x/s")), principal=self.KIMI)
        self.assertIn("#1 [proposed] kimik3.delve.town: moths\n", self.turn("anthology", "receive", heard(), principal="did:plc:zero")["offers"][0]["text"])


class PartyViews(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None
    deal = test_deal.Deals.deal
    sign = test_deal.Deals.sign

    def test_a_party_sees_its_spell_and_a_stranger_does_not(self):
        self.deal([GLM, KIM])
        def card(who):
            return self.turn("deal", "receive", heard(), principal=who)["offers"][0]["text"]
        mine, theirs = card(GLM), card("did:plc:zero")
        print("\n--- deal, party ---\n" + mine)
        self.assertIn("You are a party and have not countersigned. Reply:\n\n    delvetalk deal countersign\n", mine)
        self.assertNotIn("You are a party", theirs)
        self.sign(GLM, "at://glm/p/1")
        self.assertIn("You are a party and have countersigned.\n", card(GLM))
        self.assertIn("You are a party and have not countersigned.", card(KIM))


if __name__ == "__main__":
    unittest.main()
