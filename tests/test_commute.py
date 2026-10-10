"""Commutative edits (keep, add, append) commit against a moved root and are judged on the state as
it is now; any other change of a moved root is stale.

Evidence for FOUNDATION §2 Turn, §8 (layer: host).

Commutative edits commit against moved roots, and list items
addressed by their canonical bytes.

A root whose every change in the turn is `keep`, `add` or `append` need only be a version the
object had: the changes re-apply on the state as it is now and the law judges them there. Any
other change of a moved root is `staleRoot`, as before.

    python3 -W error -m unittest tests.test_commute -v
"""
import json
import unittest

from tests.test_chain import field
from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record
from tests.test_world import COUNTER, BOUNDED, WorldCase, add, put, root, seed, write
from tests.test_turn_world import declared

BELL = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
record State:
  count: Nat
  rains: Lists.List<String>
record Edits:
  count: Plans.Edit<Nat, Nat>
  rains: Plans.Entries<String, String>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
law cap: new.count <= 3
def initial() -> State:
  {count: 0n, rains: Lists.List::<String>.nil({})}
def keepRains() -> Plans.Entries<String, String>:
  Plans.Entries::<String, String>.keep({})
def write(context: Abi.Context, edits: Edits) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: edits})):
    case _: 0n
def rain(state: State, input: {text: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  write(context, {count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), rains: Plans.Entries::<String, String>.append({item: input.text})})
def strike(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.await({slot: {principal: "ann", intent: "go"}, patience: 50n})):
    case _: write(context, {count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), rains: Plans.Entries::<String, String>.append({item: "struck"})})
def strikeSet(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.await({slot: {principal: "ann", intent: "go"}, patience: 50n})):
    case _: write(context, {count: Plans.Edit::<Nat, Nat>.set({value: state.count + 1n}), rains: keepRains()})
def drop(state: State, input: {text: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  write(context, {count: Plans.Edit::<Nat, Nat>.keep({}), rains: Plans.Entries::<String, String>.removeItem({item: input.text})})
def fix(state: State, input: {text: String, to: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  write(context, {count: Plans.Edit::<Nat, Nat>.keep({}), rains: Plans.Entries::<String, String>.amendItem({item: input.text, change: input.to})})
""")


def items(state):
    return [x["value"] for x in field(state, "rains")["items"]]


class Moved(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("bell", BELL, record(count=nat(0), rains={"tag": "list", "items": []}))

    def bell(self):
        s = self.state("bell")
        return field(s, "count")["value"], items(s)

    def rain(self, text, principal, identity=None):
        r = self.turn("bell", "rain", record(text=label(text)), principal=principal, identity=identity)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_a_suspended_strike_appends_after_two_rains_moved_the_bell(self):
        s = self.turn("bell", "strike", principal="gemini", identity="strike")
        self.assertEqual(s["status"], "suspended", s)
        self.rain("drip", "kim")
        settled = self.rain("drop", "ann", identity="go")
        [resumed] = settled["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        entry = resumed["receipt"]
        # The root keeps the version the strike read; that (since moved) state's CID is the created seed's.
        self.assertEqual(entry["roots"], [{"object": "bell", "version": 0}])
        self.assertEqual(self.host.send(op="world-state-cid", principal="ann", object="bell", version=0)["status"], "stateCid")
        self.assertEqual(entry["outcome"]["writes"][0]["version"], 3)
        self.assertEqual(self.bell(), ("3", ["drip", "drop", "struck"]))
        # The entry replays: the same rule judges it again on reopen.
        self.reopen()
        self.assertEqual(self.bell(), ("3", ["drip", "drop", "struck"]))

    def test_a_moved_root_changed_by_set_is_refused_stale(self):
        s = self.turn("bell", "strikeSet", principal="gemini", identity="strike")
        self.assertEqual(s["status"], "suspended", s)
        self.rain("drip", "kim")
        [resumed] = self.rain("drop", "ann", identity="go")["resumed"]
        # The resumption is refused staleRoot (journaled, transient) and the turn re-run once at once
        # from its request, on the bell as it is now.
        self.assertIn("rerunOf", resumed)
        with open(self.path) as f:
            refused = [e for e in map(json.loads, f.read().splitlines()) if e["hash"] == resumed["rerunOf"]][0]
        self.assertEqual((refused["outcome"]["class"], refused["outcome"]["object"]), ("staleRoot", "bell"))
        self.assertEqual((resumed["status"], resumed["receipt"].get("rerun")), ("admitted", True), resumed)

    def test_the_law_judges_the_commuted_write_on_the_state_as_it_is_now(self):
        s = self.turn("bell", "strike", principal="gemini", identity="strike")
        self.rain("a", "kim")
        self.rain("b", "kim")
        [resumed] = self.rain("c", "ann", identity="go")["resumed"]
        out = resumed["receipt"]["outcome"]
        # On the state it read the strike would make count 1; on the state now, 4 > cap 3.
        self.assertEqual((resumed["status"], out["class"], out.get("clause")), ("refused", "lawRefused", "cap"), resumed)
        self.assertEqual(self.bell(), ("3", ["a", "b", "c"]))

    def test_items_are_amended_and_removed_by_their_bytes_not_their_index(self):
        for t in ("a", "b", "a"):
            self.rain(t, "kim")
        r = self.turn("bell", "fix", record(text=label("a"), to=label("z")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.bell()[1], ["z", "b", "a"])
        self.assertEqual(r["receipt"]["outcome"]["writes"][0]["edits"][0]["fields"][1]["value"]["label"], "amendItem")
        self.assertEqual(self.turn("bell", "drop", record(text=label("b")))["status"], "admitted")
        self.assertEqual(self.bell()[1], ["z", "a"])
        gone = self.turn("bell", "drop", record(text=label("b")))
        self.assertEqual((gone["status"], gone["receipt"]["outcome"]["class"]), ("refused", "absentItem"), gone)
        self.reopen()
        self.assertEqual(self.bell()[1], ["z", "a"])


class Proposals(WorldCase):
    def setUp(self):
        super().setUp()
        self.create()

    def test_two_adds_against_the_same_root_both_commit(self):
        self.assertEqual(self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])["status"], "admitted")
        r = self.propose("p2", [root("c1", 0)], [write("c1", add("count", 2))])
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["receipt"]["roots"], [root("c1", 0)])
        self.assertEqual(self.view()["state"], seed(3))

    def test_a_set_against_a_moved_root_is_stale_and_a_future_version_is_stale(self):
        self.propose("p1", [root("c1", 0)], [write("c1", add("count", 1))])
        r = self.propose("p2", [root("c1", 0)], [write("c1", put("name", label("x")))])
        self.assertEqual(r["receipt"]["outcome"]["class"], "staleRoot")
        future = self.propose("p3", [root("c1", 5)], [write("c1", add("count", 1))])
        self.assertEqual(future["receipt"]["outcome"]["class"], "staleRoot")

    def test_a_moved_root_that_is_only_read_is_stale(self):
        self.create("c2")
        self.propose("p1", [root("c2", 0)], [write("c2", add("count", 1))])
        r = self.propose("p2", [root("c1", 0), root("c2", 0)], [write("c1", add("count", 1))])
        self.assertEqual((r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["object"]), ("staleRoot", "c2"))

    def test_a_commuted_add_is_judged_on_the_current_state(self):
        self.create("b", source=BOUNDED)
        self.propose("p1", [root("b", 0)], [write("b", add("count", 4))])
        r = self.propose("p2", [root("b", 0)], [write("b", add("count", 2))])
        self.assertEqual((r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["clause"]), ("lawRefused", "ceiling"))


if __name__ == "__main__":
    unittest.main()
