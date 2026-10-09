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
                                                  planting=record(principal=label(GLM), intent=label("p"))))
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
        self.make("garden", closure("Garden"), record(policy=reference(""), confirm=boolean(True),
                                                      pending=listing([record(principal=label("glm"), spell=label(spell))])))
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
