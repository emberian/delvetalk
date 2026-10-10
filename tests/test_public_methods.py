"""A method is public only when its package declares it (HOST-HANDOFF 5.62; WORLD-REVIEW finding 1).

Evidence for the authority model (layer: host).

Every definition whose first parameter is the State used to be callable by anyone. Now a
direct turn, a `call`, a `send`, a `run` or a delivery may name only a method the package
declares: the action of a form in `forms()`, a name `methods()` returns, a `views()` entry, or a
conventional name (`receive`, `render`, `set`, ...). Every other State-first definition is a
helper: refused class `noMethod` by name, absent from `world-inspect`'s methods and forms. A
change is still delivered to the receiver its subscriber named, helper or not.

Refuted by: a stranger declaring a winner with `Table.played`, resetting a seat with
`Seat.nextRound` or keeping an appointment early with `Appointment.due`; a helper listed by
`world-inspect`; a bare package's undeclared method running; a change not reaching a helper
receiver; a direct turn reaching that receiver.
"""
import json
import re
import unittest

from tests.test_chain import Chain, reference
from tests.test_changes import Receivers
from tests.test_objects import closure
from tests.test_reflection import Reflection
from tests.test_table import NORTH, OPENING, SOUTH
from tests.test_turn_world import FIXTURE_HEAD, label, nat, record
from tests.test_places import avatar_seed

KIM = "did:plc:kimik3"
STRANGER = "did:plc:stranger"


def refused_no_method(test, reply, method, obj):
    test.assertEqual(reply["status"], "refused", reply)
    outcome = reply["receipt"]["outcome"]
    test.assertEqual(outcome["class"], "noMethod", outcome)
    test.assertIn(method, outcome["reason"])
    test.assertIn(obj, outcome["reason"])


class Reproductions(Chain):
    """The three reproductions of WORLD-REVIEW finding 1, against world/objects."""

    def setUp(self):
        super().setUp()
        self.make("north", closure("Seat"), record(table=reference("table"), seat=nat(0), owner=label(NORTH), opponent=label(SOUTH), rival=reference("south")))
        self.make("south", closure("Seat"), record(table=reference("table"), seat=nat(1), owner=label(SOUTH), opponent=label(NORTH), rival=reference("north")))
        game = record(board=nat(int(OPENING["board"])), automaton=nat(OPENING["automaton"]), marks=nat(0), status=nat(0), winner=nat(0))
        r = self.host.send(op="world-create", principal="ember", identity="mk-table", object="table", modules=closure("Table"),
                           entry="initial", seed=record(owner=label("ember"), north=reference("north"), south=reference("south"), round=nat(0),
                                                        width=nat(11), height=nat(11), game=game))
        self.assertEqual(r["status"], "created", r)

    def test_a_stranger_cannot_declare_a_winner_with_played(self):
        result = record(board=nat(0), automaton=nat(0), marks=nat(0), status=nat(1), winner=nat(2))
        refused_no_method(self, self.turn("table", "played", result, principal=STRANGER), "played", "table")
        game = {f["name"]: f["value"] for f in [f for f in self.state("table")["fields"] if f["name"] == "game"][0]["value"]["fields"]}
        self.assertEqual(game["winner"], nat(0))

    def test_a_stranger_cannot_reset_a_seat_with_next_round(self):
        refused_no_method(self, self.turn("north", "nextRound", principal=STRANGER), "nextRound", "north")
        # The declared `next` still runs, and still checks its caller.
        nxt = self.turn("north", "next", principal=STRANGER)
        self.assertEqual(nxt["status"], "admitted", nxt)
        self.assertEqual(nxt["result"]["payload"]["fields"][0]["value"]["value"], "Only the table moves the round.")

    def test_the_table_still_calls_next_and_nobody_sees_the_helpers(self):
        inspected = self.host.send(op="world-inspect", principal=STRANGER, object="table", source=False)
        names = [m["name"] for m in inspected["methods"]]
        self.assertIn("resolve", names)
        for helper in ("played", "advanced", "north", "south"):
            self.assertNotIn(helper, names)
        listed = self.host.send(op="world-objects", principal=STRANGER, methods=True)
        self.assertNotIn("played", listed["methods"]["table"])
        self.assertIn("resolve", listed["methods"]["table"])


class Appointments(Chain):

    def setUp(self):
        super().setUp()
        self.make("book", closure("Appointments"), record())
        self.make(KIM, closure("Avatar"), avatar_seed("kimik3", "porch"))

    def test_a_stranger_cannot_keep_an_appointment_early_with_due(self):
        r = self.turn("book", "receive", record(text=label("delvetalk book book\ntopic: tea\nto: %s\nafter: 50" % KIM),
                                                post=label("at://p")), principal="glm")
        self.assertEqual(r["status"], "admitted", r)
        refused_no_method(self, self.turn("book/1", "due", principal=STRANGER), "due", "book/1")
        status = [f["value"] for f in self.state("book/1")["fields"] if f["name"] == "status"][0]
        self.assertEqual(status["label"], "booked")


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
        from tests.test_turn_world import closure as world_closure, declared
        plan = world_closure("World")
        self.make("bare", plan + [{"name": "Bare", "source": BARE}], record())
        self.make("caller", plan + [{"name": "Caller", "source": declared(BARE, "poke", "post")}], record())

    def test_an_undeclared_method_is_refused_by_name_and_listed_nowhere(self):
        refused_no_method(self, self.turn("bare", "bump", principal=STRANGER), "bump", "bare")
        inspected = self.host.send(op="world-inspect", principal=STRANGER, object="bare", source=False)
        self.assertEqual([m["name"] for m in inspected["methods"]], [])
        self.assertNotIn("bump", json.dumps(inspected["forms"]))

    def test_a_call_or_send_naming_a_helper_is_refused_no_method(self):
        poked = self.turn("caller", "poke", record(target=label("bare"), method=label("bump")))
        self.assertEqual((poked["status"], poked["result"]["value"]), ("admitted", "7"), poked)
        posted = self.turn("caller", "post", record(target=label("bare"), method=label("bump")))
        self.assertEqual((posted["status"], posted["result"]["value"]), ("admitted", "7"), posted)
        self.assertEqual(self.host.send(op="world-pending").get("count"), 0)

    def test_an_object_may_call_its_own_helper(self):
        own = self.turn("caller", "poke", record(target=label("caller"), method=label("bump")))
        self.assertEqual((own["status"], own["result"]["value"]), ("admitted", "1"), own)

    def test_a_malformed_methods_declaration_refuses_the_package(self):
        from tests.test_turn_world import closure as world_closure
        source = BARE + "def methods() -> Nat:\n  1n\n"
        r = self.host.send(op="world-create", principal="ember", identity="mk-bad", object="bad",
                           modules=world_closure("World") + [{"name": "Bad", "source": source}], entry="initial", seed=record())
        self.assertNotEqual(r.get("status"), "created", r)
        self.assertIn("methods()", r.get("message", "") + str(r.get("receipt", "")), r)


HELPER_RECEIVER_METHODS = """def methods() -> Lists.List<String>:
  Lists.List::<String>.cons({head: "watch", tail: Lists.List::<String>.nil({})})
"""


class HelperReceivers(Reflection):
    """A change goes to the receiver its subscriber named even when that is a helper; nobody else
    may turn it."""

    setUp = Receivers.setUp
    make2 = Receivers.make2
    get = Receivers.get

    def test_a_change_reaches_a_helper_receiver_that_no_turn_may_name(self):
        from tests.test_changes import RECEIVER
        bare = re.sub(r"\ndef methods\(\)[^\n]*\n  [^\n]*", "", RECEIVER)
        self.make2("q", bare.rstrip("\n") + "\n" + HELPER_RECEIVER_METHODS)
        r = self.turn("q", "watch", record(target=label("bell"), field=label("rung"), method=label("rung")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.turn("bell", "ring", record())["status"], "admitted")
        self.assertEqual(self.get("q", "heard"), nat(1))
        refused_no_method(self, self.turn("q", "rung", record(object=reference("bell"), field=label("rung"), version=nat(9),
                                                                inserted={"tag": "list", "items": []},
                                                                retracted={"tag": "list", "items": []}), principal=STRANGER), "rung", "q")
        self.assertEqual(self.get("q", "heard"), nat(1))


del Receivers

if __name__ == "__main__":
    unittest.main()
