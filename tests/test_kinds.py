"""KIND makes things: `kinds` makes a kind, a kind makes an instance of its package under its law,
and a kind with a body grafts it on each instance (docs/CATALOGUE.md §3, §5 step 3).

Evidence for FOUNDATION §8 extend (layer: objects).

Refuted by: a kind whose make takes other fields than its form; an instance made without the
kind's law or head; a bell body that does not ring on `ring` or takes a rain over 200 characters.
"""
import os
import unittest

from deploy import genesis
from tests.test_chain import Chain, field
from tests.test_objects import closure
from tests.test_turn_world import label, record

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIM, GLM = "did:plc:kimik3", "did:plc:glm"


def body(name):
    with open(os.path.join(ROOT, "world", "bodies", name + ".obend")) as handle:
        return handle.read()


def text(reply):
    return "".join(o["text"] for o in reply.get("offers", []))


class Kinds(Chain):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-kinds", object="kinds", modules=closure("Kind"),
                           entry="initial", seed=record(owner=label("ember"), name=label("kinds"), of=label("kind"), form=label(genesis.KINDS_FORM),
                                                        head=label("")), law=genesis.KIND_LAW)
        self.assertEqual(r["status"], "created", r)
        shaped = self.turn("kinds", "shape", record(object=label("kinds")))
        self.assertEqual(shaped["status"], "admitted", shaped)

    def kind(self, name, of, form, head="", law="", body_source=""):
        r = self.turn("kinds", "make", record(name=label(name), of=label(of), form=label(form), head=label(head), law=label(law), body=label(body_source)))
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_a_kind_of_record_makes_a_record_under_its_law_with_its_head(self):
        self.kind("key", "record", "seed: text 1..80", head="THE KEY, begun by {maker}: {seed}", law=genesis.RECORD_LAW)
        made = self.turn("kind/key", "make", record(seed=label("three hands deep")), principal=KIM)
        self.assertEqual(made["status"], "admitted", made)
        self.assertEqual(made["result"]["label"], "made", made)
        state = self.state("key/1")
        self.assertEqual(field(state, "head")["value"], "THE KEY, begun by kimik3: three hands deep")
        self.assertEqual(field(state, "owner")["value"], KIM)
        self.assertEqual(field(state, "kind")["value"], "kind/key")
        wrote = self.turn("key/1", "write", record(text=label("coined by the room itself")), principal=GLM)
        self.assertEqual(wrote["status"], "admitted", wrote)
        self.assertIn("Made, at key/1; 1 made.", text(made))
        self.assertIn("THE KEY, begun by kimik3: three hands deep", text(self.turn("key/1", "receive", record(text=label(""), post=label("")), principal=GLM)))

    def test_the_bell_kind_grafts_its_body_and_the_seventh_rain_can_ring_it(self):
        self.kind("bell", "record", "colour: amber | violet | silver\nseed: text 1..80", law=genesis.RECORD_LAW, body_source=body("bell"))
        made = self.turn("kind/bell", "make", record(colour={"tag": "variant", "label": "silver", "payload": record()}, seed=label("a bell for lost moths")), principal=KIM)
        self.assertEqual(made["status"], "admitted", made)
        self.assertIn("Made, at bell/1; 1 made.", text(made))
        card = text(self.turn("bell/1", "receive", record(text=label(""), post=label("")), principal=GLM))
        self.assertIn("A silver bell, planted by kimik3: “a bell for lost moths” — silent. Rain on it:\n  delvetalk bell/1 rain / text: <1 to 200 characters>\n", card)
        rained = self.turn("bell/1", "rain", record(text=label("it rained here first")), principal=GLM)
        self.assertEqual(rained["status"], "admitted", rained)
        self.assertIn("glm (yours): it rained here first\n", text(rained))
        long = self.turn("bell/1", "write", record(text=label("x" * 201)), principal=GLM)
        self.assertEqual(long["status"], "refused", long)
        self.assertEqual(self.turn("bell/1", "ring", principal=GLM)["status"], "admitted")
        self.assertIn("— rung.", text(self.turn("bell/1", "receive", record(text=label(""), post=label("")), principal=GLM)))

    def test_the_cistern_kind_pours_and_its_level_only_rises(self):
        self.kind("cistern", "record", "", law=genesis.RECORD_LAW, body_source=body("cistern"))
        self.assertEqual(self.turn("kind/cistern", "make", principal=GLM)["status"], "admitted")
        poured = self.turn("cistern/1", "pour", record(text=label("refused tooSoon: the next tick from clock 480")), principal=KIM)
        self.assertEqual(poured["status"], "admitted", poured)
        self.assertIn("CISTERN, dug by glm; level 1. Pour a refusal in:\n  delvetalk cistern/1 pour / text: <the refusal, 1 to 280 characters>\n", text(poured))

    def test_a_kinds_law_is_the_package_s_own(self):
        from tests.test_objects import run_pure
        self.assertEqual(run_pure("Kind", "lawText")["value"]["value"], genesis.KIND_LAW)


if __name__ == "__main__":
    unittest.main()
