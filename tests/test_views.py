"""Render with a point of view: the same state shows its owner, its parties and a stranger different
cards, and names people by handle.

Evidence for FOUNDATION §8 render (layer: objects).

Render with a point of view: render(state, context) is the
card as the reader in the context sees it. A member sees more than a stranger; the planter sees
"(yours)". The card a non-acting reply gets is the reader's, so these drive real world-turns
with an empty reply by different principals, and through world-card, which renders for its reader.

Refuted by: a stranger's card showing an Avatar's notes;
the planter's card lacking "(yours)"; a party's card lacking its countersign spell.
"""
import unittest

from tests import test_chain
from tests.test_rooms import avatar_seed
from tests.wire import label, record
from tests.bend import closure

GLM, KIM = "did:plc:glm", "did:plc:kimik3"


def heard(text=""):
    return record(text=label(text), post=label(""))


def silver():
    return {"tag": "variant", "label": "silver", "payload": record()}


class Views(test_chain.Chain):

    def card(self, name, principal):
        reply = self.turn(name, "receive", heard(), principal=principal)
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["offers"][0]["text"]

    def world_card(self, name, principal="ember"):
        r = self.host.send(op="world-card", principal=principal, object=name)
        self.assertEqual(r["status"], "card", r)
        return r["text"]

    def test_the_planter_sees_yours_and_a_stranger_is_offered_no_door(self):
        self.make("bell", closure("Bell"), record(colour=silver(), seed=label("a bell for lost moths"),
                                                  planting=label("p"), planter=label(GLM), planterHandle=label("")))
        mine, theirs = self.card("bell", GLM), self.card("bell", KIM)
        self.assertTrue(mine.startswith("A silver bell, planted by glm (yours): “a bell for lost moths” — silent.\n"), mine)
        self.assertTrue(theirs.startswith("A silver bell, planted by glm: “a bell for lost moths” — silent.\n"), theirs)
        self.assertIn("delvetalk bell door", mine)
        self.assertIn("delvetalk bell ring", theirs)
        self.assertNotIn("door", theirs)  # the usage lists only what inspect offers a stranger
        self.assertNotIn("(yours)", self.world_card("bell"))
        # world-card renders for its reader: the planter's card says so, a stranger's does not.
        self.assertIn("(yours)", self.world_card("bell", GLM))
        self.assertNotIn("(yours)", self.world_card("bell", KIM))

    def test_an_avatars_notes_are_its_principals(self):
        self.make(GLM, closure("Avatar"), avatar_seed("glm", "porch"))
        self.assertEqual(self.turn(GLM, "note", record(text=label("meet at the gate")), principal=KIM)["status"], "admitted")
        mine, theirs = self.card(GLM, GLM), self.card(GLM, KIM)
        self.assertIn("1 new since entry 0:\n", mine)
        self.assertIn("kimik3: meet at the gate\n", mine)
        self.assertNotIn("meet at the gate", theirs)
        self.assertIn("glm's avatar, in porch.\nIts book: delvetalk glm book\n1 note\n", theirs)


if __name__ == "__main__":
    unittest.main()
