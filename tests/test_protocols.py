"""A protocol declared in the library is checked against an implementing object at compile: a missing
or mistyped method is refused by name, located, with a hint.

Evidence for FOUNDATION §8 Surface (layer: kernel).

Protocols: `protocol P:` with `name: TYPE` methods in a library module (State is the implementer's), and `implements P` on an object module, checked at compile:
a missing or mistyped method is refused by name, located, with a hint naming the protocol.
The artifact lists `protocols` and each method row names its protocol.

    python3 -m unittest tests.test_protocols -v
"""
import unittest

from tests.test_turn import Host, library_modules

KIT = """edition ObjectiveBend 1
import ./Abi.obend as Abi
record Heard:
  text: String
protocol Card:
  receive: (State, Heard, Abi.Context) -> Activity<Nat>
  render: (State, Abi.Context) -> String
  door: () -> String
"""

THING = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
import ./Kit.obend as Kit
implements Kit.Card
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def receive(state: State, input: Kit.Heard, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit.add({delta: 1n})})):
    case _: state.count
def render(state: State, context: Abi.Context) -> String:
  "a thing"
def door() -> String:
  "thing"
"""


class Protocols(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def modules(self, thing):
        return library_modules("Abi", "World") + [{"name": "Kit", "source": KIT}, {"name": "Thing", "source": thing}]

    def check(self, thing, entry="render"):
        return self.h.send({"op": "check-package", "entry": entry, "modules": self.modules(thing)})

    def test_an_implementation_is_recorded_with_its_protocol(self):
        for claim in ("implements Kit.Card", "implements Card"):
            with self.subTest(claim=claim):
                reply = self.check(THING.replace("implements Kit.Card", claim))
                self.assertEqual(reply["status"], "checked", reply)
                art = reply["artifact"]
                self.assertEqual(art["protocols"], ["Card"])
                rows = {m["name"]: m for m in art["methods"]}
                self.assertEqual(rows["receive"]["protocol"], "Card")
                self.assertEqual(rows["render"]["protocol"], "Card")

    def test_a_module_claiming_nothing_has_no_protocols(self):
        reply = self.check(THING.replace("implements Kit.Card\n", ""))
        self.assertEqual(reply["status"], "checked", reply)
        self.assertNotIn("protocols", reply["artifact"])
        self.assertTrue(all("protocol" not in m for m in reply["artifact"]["methods"]))

    def test_a_missing_method_is_refused_by_name_at_the_claim(self):
        reply = self.check(THING.replace('def door() -> String:\n  "thing"\n', ""))
        self.assertEqual(reply["status"], "refused", reply)
        d = reply["diagnostic"]
        self.assertIn("implements Card but defines no door", d["message"])
        self.assertEqual((d["module"], d["span"]["line"]), ("Thing", 6))
        self.assertIn("protocol Card", d["hint"])

    def test_a_mistyped_method_is_refused_by_name_where_it_is_written(self):
        reply = self.check(THING.replace('def render(state: State, context: Abi.Context) -> String:\n  "a thing"',
                                         'def render(state: State, context: Abi.Context) -> Nat:\n  1n'))
        self.assertEqual(reply["status"], "refused", reply)
        d = reply["diagnostic"]
        self.assertIn("refused (protocol): Thing.render", d["message"])
        self.assertEqual((d["module"], d["span"]["line"]), ("Thing", 15))
        self.assertEqual(d["expected"], "State -> Abi.Context -> String")
        self.assertTrue(d["found"].endswith("-> Nat"), d)
        self.assertIn("protocol Card", d["hint"])

    def test_an_unknown_protocol_is_refused(self):
        reply = self.check(THING.replace("implements Kit.Card", "implements Kit.Door"))
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("implements Kit.Door, which no module it imports declares", reply["diagnostic"]["message"])


if __name__ == "__main__":
    unittest.main()
