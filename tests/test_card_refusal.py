"""A card's own refusal refuses its turn (playtest 2's D6; KERNEL-HANDOFF section 26).

`refuse(line)` takes any String the card computes. The turn is refused with class `cardRefused`,
the clause and reading parsed from `refused <clause>: <reading>` (else clause `card` and the line
whole), the object the card that refused; nothing of the turn is kept, and a stranger sees only
the class. A reading past `maxRefusalBytes` is kept to the whole characters within it.

    python3 -W error -m unittest tests.test_card_refusal -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.wire import field, nat, record
from tests.bend import declared

CARD = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  owner: String
  count: Nat
def initial() -> State:
  {owner: "Kestrel", count: 0n}
def bump(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<Nat>:
  match world.write({count: Plans.Edit::<Nat, Nat>.add({delta: input.n})}):
    case _: if input.n > 3n then refuse("refused tooMany: {state.owner} allows 3: not {natText(input.n)}") else input.n
def plain(state: State, context: Abi.Context) -> Activity<Nat>:
  refuse("no, just no")
def long(state: State, context: Abi.Context) -> Activity<Nat>:
  refuse("refused long: LONG")
def relay(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Nat>({object: {world: "", object: "counter"}, method: "bump", argument: input}):
    case returned(r): r.result
    case _: 0n
""".replace("LONG", "é" * 2100))


class CardRefusal(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("counter", CARD, record())
        self.make("relay", CARD, record())

    def outcome(self, r):
        return r["receipt"]["outcome"]

    def test_a_computed_refusal_refuses_the_turn_with_its_clause_and_reading(self):
        r = self.turn("counter", "bump", record(n=nat(5)))
        out = self.outcome(r)
        self.assertEqual((r["status"], out["class"], out["clause"], out["object"]), ("refused", "cardRefused", "tooMany", "counter"), r)
        # The reading is computed from the state (the host names the creating principal its owner).
        self.assertEqual(out["reading"], "ember allows 3: not 5")
        self.assertEqual(out["reason"], "refused tooMany: ember allows 3: not 5")
        # Nothing of the turn is kept: the write before the refusal is gone, and nothing is offered.
        self.assertNotIn("offers", r["receipt"])
        self.assertEqual(field(self.state("counter"), "count")["value"], "0")
        admitted = self.turn("counter", "bump", record(n=nat(2)))
        self.assertEqual(admitted["status"], "admitted", admitted)
        self.assertEqual(field(self.state("counter"), "count")["value"], "2")

    def test_a_line_of_another_shape_is_the_card_clause_with_the_line_whole(self):
        out = self.outcome(self.turn("counter", "plain"))
        self.assertEqual((out["class"], out["clause"], out["reading"], out["reason"]),
                         ("cardRefused", "card", "no, just no", "refused card: no, just no"))

    def test_a_callee_refusal_refuses_the_turn_naming_the_card_that_refused(self):
        out = self.outcome(self.turn("relay", "relay", record(n=nat(9))))
        self.assertEqual((out["class"], out["clause"], out["object"]), ("cardRefused", "tooMany", "counter"), out)

    def test_a_reading_past_its_bound_is_kept_to_the_characters_within_it(self):
        out = self.outcome(self.turn("counter", "long"))
        self.assertEqual((out["class"], out["clause"], out["object"]), ("cardRefused", "long", "counter"), out)
        self.assertEqual(out["reading"], "é" * 2048 + "…")

    def test_a_stranger_sees_the_class_not_the_reading(self):
        r = self.turn("counter", "bump", record(n=nat(5)))
        seen = self.host.send(op="world-entry", principal="stranger", hash=r["receipt"]["hash"])
        text = str(seen)
        self.assertIn("cardRefused", text)
        self.assertNotIn("allows 3", text)
        self.reopen()
        self.assertEqual(field(self.state("counter"), "count")["value"], "0")


if __name__ == "__main__":
    unittest.main()
