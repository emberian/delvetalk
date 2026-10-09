"""A layer over a real object (FOUNDATION section 13, row 3, `reprogram {mode: extend}`): Louder
over Bell redefines render and renderFor and keeps everything else, rain and receive included.

Refuted by: rain no longer appending after the layer, the card not changing, or the layer reaching
the bell without its law's admission."""
import unittest

from tests import test_chain
from tests.test_chain import nil
from tests.test_replay import get, items
from tests.test_turn_world import closure, label, record

LOUDER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
type State = Super.State
type Plan = Super.Plan
type Response = Super.Response
def renderFor(state: State, context: Abi.Context) -> Document.Document:
  Document.text(textConcat("LOUDER: ", textConcat(Document.plain(Super.renderFor(state, context)), "(and louder)\\n")))
def render(state: State) -> Document.Document:
  Document.text(textConcat("LOUDER: ", textConcat(Document.plain(Super.render(state)), "(and louder)\\n")))
"""


def silver():
    return {"tag": "variant", "label": "silver", "payload": record()}


class Louder(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-bell", object="bell", modules=closure("Bell"),
                           entry="initial", seed=record(colour=silver(), seed=label("moths"), rains=nil(), rung={"tag": "boolean", "value": False},
                                                        planting=record(principal=label("did:plc:glm"), intent=label("p")), observers=nil()))
        self.assertEqual(r["status"], "created", r)

    def extend(self, who="ember", ident="louder"):
        version = self.host.send(op="world-view", principal="ember", object="bell")["version"]
        return self.host.send(op="world-reprogram", principal=who, identity=ident, object="bell", version=version,
                              package=LOUDER, mode="extend")

    def test_louder_changes_the_card_and_keeps_rain(self):
        self.assertEqual(self.turn("bell", "rain", record(text=label("before")), principal="did:plc:kimik3")["status"], "admitted")
        r = self.extend()
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["receipt"]["outcome"]["reprograms"][0]["mode"], "extend")
        rained = self.turn("bell", "rain", record(text=label("after")), principal="did:plc:gemini")
        self.assertEqual(rained["status"], "admitted", rained)
        self.assertEqual([get(x, "text")["value"] for x in items(get(self.state("bell"), "rains"))], ["before", "after"])
        card = self.host.send(op="world-card", principal="ember", object="bell")
        print("\n--- louder bell ---\n" + card.get("text", str(card)))
        self.assertEqual(card["text"], "LOUDER: A silver bell planted by glm: moths (silent)\nkimik3: before\ngemini: after\n(and louder)\n")
        # The spell still rains: receive is the bell's own, unchanged by the layer.
        spelled = self.turn("bell", "receive", record(text=label("delvetalk bell rain\ntext: by spell"), post=label(""), slot=label("")), principal="did:plc:glm")
        self.assertEqual((spelled["status"], spelled["result"]["label"]), ("admitted", "done"), spelled)

    def test_a_stranger_cannot_layer_the_bell(self):
        r = self.extend(who="mallory", ident="evil")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "lawRefused"), r)


if __name__ == "__main__":
    unittest.main()
