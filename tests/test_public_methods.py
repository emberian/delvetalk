"""A method is public only when its package declares it (HOST-HANDOFF §5.3 "Declared methods").

Evidence for the authority model (layer: host).

Every definition whose first parameter is the State used to be callable by anyone. Now a
direct turn, a `call`, a `send`, a `run` or a delivery may name only a method the package
declares: the action of a form in `forms()`, a name `methods()` returns, a `views()` entry, or a
conventional name (`receive`, `render`, `set`, ...). Every other State-first definition is a
helper: refused class `noMethod` by name, absent from `world-inspect`'s methods and forms. No
delivery reaches a helper either: a supervisor's `ended` must be offered (test_supervisors).

Refuted by: a stranger declaring a winner with `Table.played`, or resetting a seat with
`Seat.nextRound`; a helper listed by
`world-inspect`; a bare package's undeclared method running.
"""
import json
import unittest

from tests.test_chain import Chain
from tests.test_reflection import Reflection
from tests.test_table import NORTH, OPENING, SOUTH
from tests.test_turn_world import FIXTURE_HEAD
from tests.wire import label, nat, record, reference
from tests.bend import closure, declared

STRANGER = "did:plc:stranger"


def refused_no_method(test, reply, method, obj):
    test.assertEqual(reply["status"], "refused", reply)
    outcome = reply["receipt"]["outcome"]
    test.assertEqual(outcome["class"], "noMethod", outcome)
    test.assertIn(method, outcome["reason"])
    test.assertIn(obj, outcome["reason"])


class Reproductions(Chain):
    """Three reproductions of an undeclared method run from outside, against world/objects."""

    def setUp(self):
        super().setUp()
        self.make("north", closure("Seat"), record(table=reference("table"), seat=nat(0), owner=label(NORTH), opponent=label(SOUTH), rival=reference("south")))
        self.make("south", closure("Seat"), record(table=reference("table"), seat=nat(1), owner=label(SOUTH), opponent=label(NORTH), rival=reference("north")))
        game = record(board=nat(int(OPENING["board"])), automaton=nat(OPENING["automaton"]), marks=nat(0), status=nat(0), winner=nat(0))
        r = self.host.send(op="world-create", principal="ember", identity="mk-table", object="table", modules=closure("Table"),
                           entry="initial", seed=record(owner=label("ember"), north=reference("north"), south=reference("south"), round=nat(0),
                                                        width=nat(11), height=nat(11), game=game))
        self.assertEqual(r["status"], "created", r)

    def test_a_stranger_cannot_declare_a_winner_with_played_or_reset_a_seat_with_next_round(self):
        result = record(board=nat(0), automaton=nat(0), marks=nat(0), status=nat(1), winner=nat(2))
        refused_no_method(self, self.turn("table", "played", result, principal=STRANGER), "played", "table")
        game = {f["name"]: f["value"] for f in [f for f in self.state("table")["fields"] if f["name"] == "game"][0]["value"]["fields"]}
        self.assertEqual(game["winner"], nat(0))
        refused_no_method(self, self.turn("north", "nextRound", principal=STRANGER), "nextRound", "north")
        # The declared `next` still runs, and still checks its caller.
        nxt = self.turn("north", "next", principal=STRANGER)
        self.assertEqual(nxt["status"], "admitted", nxt)
        self.assertEqual({f["name"]: f["value"]["value"] for f in nxt["result"]["payload"]["fields"]},
                         {"clause": "notTable", "reading": "Only the table moves the round."})

BARE = FIXTURE_HEAD + """def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  addSelf(context, 1n)
def poke(state: State, input: {target: String, method: String}, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Nat>({object: {world: "", object: input.target}, method: input.method, argument: Plans.nothing()}):
    case returned(_): 1n
    case refused(r): if r.clause == "noMethod" then 7n else 2n
    case _: 3n
def post(state: State, input: {target: String, method: String}, context: Abi.Context) -> Activity<Nat>:
  match world.send({object: {world: "", object: input.target}, method: input.method, argument: Plans.nothing()}):
    case delivery(_): 1n
    case refused(r): if r.clause == "noMethod" then 7n else 2n
    case _: 3n
"""


class Bare(Chain):
    """A package declaring neither `forms()` nor `methods()` exposes only the conventional names."""

    def setUp(self):
        super().setUp()
        plan = closure("World")
        self.make("bare", plan + [{"name": "Bare", "source": BARE}], record())
        self.make("caller", plan + [{"name": "Caller", "source": declared(BARE, "poke", "post")}], record())

    def test_an_undeclared_method_is_refused_by_name_to_a_turn_call_or_send_and_listed_nowhere(self):
        refused_no_method(self, self.turn("bare", "bump", principal=STRANGER), "bump", "bare")
        inspected = self.host.send(op="world-inspect", principal=STRANGER, object="bare", source=False)
        self.assertEqual([m["name"] for m in inspected["methods"]], [])
        self.assertNotIn("bump", json.dumps(inspected["forms"]))
        for method, target, want in (("poke", "bare", "7"), ("post", "bare", "7"), ("poke", "caller", "1")):  # 7: refused noMethod; 1: its own helper runs
            r = self.turn("caller", method, record(target=label(target), method=label("bump")))
            self.assertEqual((r["status"], r["result"]["value"]), ("admitted", want), (method, target, r))
        self.assertEqual(self.host.send(op="world-pending").get("count"), 0)

    def test_a_malformed_methods_declaration_refuses_the_package(self):
        source = BARE + "def methods() -> Nat:\n  1n\n"
        r = self.host.send(op="world-create", principal="ember", identity="mk-bad", object="bad",
                           modules=closure("World") + [{"name": "Bad", "source": source}], entry="initial", seed=record())
        self.assertNotEqual(r.get("status"), "created", r)
        self.assertIn("methods()", r.get("message", "") + str(r.get("receipt", "")), r)


if __name__ == "__main__":
    unittest.main()
