"""A refused `call` carries the refusal's reading when the call site's result has the field (World's
`Returned.refused {clause, reading}`, rehearsal run 11 finding 3): the voiced reason the host would
journal, so a directory that hands a reply on can say why it was not taken.

Evidence for HOST-HANDOFF 5.77 (layer: host). Refuted by a refused call whose reading is empty or
another refusal's, or by a call site without the field that no longer hears `refused {clause}`.

    python3 -W error -m unittest tests.test_call_reading -v
"""
import unittest

from tests.test_chain import Chain
from tests.test_spell_turns import GARDEN
from tests.test_turn_world import ON_DISK, closure, declared, label, record

RETURNED = ("sum Returned<R>:\n  returned: {result: R}\n  denied: {}\n  refused: {clause: String}\n",
            "sum Returned<R>:\n  returned: {result: R}\n  denied: {}\n  refused: {clause: String, reading: String}\n")

RELAY = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def pass(state: State, input: {to: String, text: String}, context: Abi.Context) -> Activity<String>:
  match world.call::<Data>({object: {world: "", object: input.to}, method: "receive", argument: {text: input.text, post: ""}}):
    case returned(_): "returned"
    case refused(r): "{r.clause}|{r.reading}"
    case _: "other"
""", "pass")


class CallReading(Chain):
    def modules(self, name, source):
        with open(ON_DISK["World"], encoding="utf-8") as f:
            world = f.read()
        self.assertIn(RETURNED[1], world)   # world/lib/World.obend carries the reading
        seen, out = set(), []
        for dep in ("Abi", "List", "Form", "Plan", "World"):
            closure(dep, seen, out)
        return out + [{"name": name, "source": source}]

    def setUp(self):
        super().setUp()
        self.make("relay", self.modules("Relay", RELAY), record())
        self.make("garden", self.modules("Garden", declared(GARDEN)), record())

    def pass_(self, to, text):
        r = self.turn("relay", "pass", record(to=label(to), text=label(text)), principal="glm")
        self.assertEqual(r["status"], "admitted", r)
        return r["result"]["value"]

    def test_a_refused_spell_and_an_unknown_card_say_why(self):
        self.assertEqual(self.pass_("garden", "delvetalk garden plant\ncolour: gold\nseed: fern"),
                         "badValue|colour is one of: amber, violet, silver")
        self.assertEqual(self.pass_("forge", "delvetalk forge make"),
                         "unknownObject|no card forge that you may see; the directory lists the doors.")
        self.assertEqual(self.pass_("garden", "delvetalk garden plant\ncolour: amber\nseed: oak"), "returned")


if __name__ == "__main__":
    unittest.main()
