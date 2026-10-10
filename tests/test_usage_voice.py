"""Usage and hints speak as the speaker does (rehearsal run 11 findings 5 and 6): a card resolved for
the speaker (`env`) is named as they wrote it, never `env/<did>`; a bad value is a blank in the hint,
not repeated; an unknown card from a card without spells points to the directory; usage lists only
the methods the speaker's law admits; a `views()` entry is read, not cast, so it is no spell.

Evidence for HOST-HANDOFF 5.80 (layer: host). Refuted by a hint naming `env/<did>`, repeating a
value it refused, saying a card "takes no spells" for an unknown card, listing a method the law
refuses the speaker, or listing a view.

    python3 -W error -m unittest tests.test_usage_voice -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.test_spell_turns import GARDEN
from tests.test_turn_world import label, record, declared

DID = "did:plc:aaaaaaaaaaaaaaaaaaaaaaa1"

# An Env-like card: `tune` for anyone, `reset` only for its owner (a clause that reads no state),
# and a derived view `count`.
ENV = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./World.obend as World
record State:
  n: Nat
record Binding:
  name: String
  value: String
law reset "only ember resets it": (request.method == "reset") implies (request.subject == "ember")
def initial() -> State:
  {n: 0n}
def tune(state: State, input: {level: Nat}, context: Abi.Context) -> Activity<Nat>:
  1n
def reset(state: State, input: {to: Nat}, context: Abi.Context) -> Activity<Nat>:
  2n
def count(state: State) -> Nat:
  state.n
def views() -> Lists.List<String>:
  Lists.List::<String>.cons({head: "count", tail: Lists.List::<String>.nil()})
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  3n
""", "tune", "reset")

DIRECTORY = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./World.obend as World
record State:
  n: Nat
record Binding:
  name: String
  value: String
def initial() -> State:
  {n: 0n}
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  0n
""", "receive")


class UsageVoice(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        for name, source in ((f"env/{DID}", ENV), ("garden", declared(GARDEN)), ("root", DIRECTORY)):
            r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                               modules=[{"name": "Probe", "source": source}], entry="initial", seed=record())
            self.assertEqual(r["status"], "created", r)

    def say(self, card, text, principal=DID, identity=None):
        return self.turn(card, "receive", record(text=label(text), post=label("")), principal=principal, identity=identity)

    def test_a_resolved_card_is_named_as_the_speaker_wrote_it(self):
        out = self.say("root", "delvetalk env nope", identity="n1")["receipt"]["outcome"]
        self.assertEqual((out["clause"], out["reason"]), ("noAction", "env has no spell nope; it has these:"), out)
        self.assertIn("delvetalk env tune\nlevel: <a number from 0 to 1000000000>", out["hint"])
        self.assertNotIn(DID, out["hint"] + out["reason"])

    def test_usage_lists_what_the_law_admits_the_speaker(self):
        usage = self.say("root", "delvetalk env ?")
        self.assertEqual(usage["status"], "usage", usage)
        self.assertIn("delvetalk env tune", usage["text"])
        self.assertNotIn("reset", usage["text"])

    def test_a_bad_value_is_a_blank_and_an_unknown_card_points_to_the_directory(self):
        out = self.say("garden", "delvetalk garden plant\ncolour: gold\nseed: fern", identity="b1")["receipt"]["outcome"]
        self.assertEqual(out["clause"], "badValue", out)
        self.assertIn("colour: <amber, violet, silver>", out["hint"])
        self.assertIn("seed: fern", out["hint"])
        self.assertNotIn("gold", out["hint"])
        out = self.say("root", "delvetalk forge make", identity="f1")["receipt"]["outcome"]
        self.assertEqual((out["clause"], out["hint"]), ("otherCard", "no card named forge; reply to the directory for the doors"), out)


if __name__ == "__main__":
    unittest.main()
