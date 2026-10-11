"""A turn runs against the durable store and commits once: receipts name roots, a retry returns the
same receipt, views are typed by the reader's authority.

Evidence for FOUNDATION §2 Turn (layer: host).

world-turn: activities run against the durable store and commit once.

Counter (tests/fixtures/objects) and Bell (world/objects) are real files (each exports `initial`); the other objects are fixtures that each isolate one rule.
"""
import unittest

from tests.host import HostCase
from tests.bend import closure, counter_modules, declared
from tests.wire import cid_of, label, nat, record

FIXTURE_HEAD = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 5n}
def addSelf(context: Abi.Context, n: Nat) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit.add({delta: n})})):
    case written(_): 1n
    case _: 0n
"""


def fixture(body, law=""):
    head = FIXTURE_HEAD.replace("def initial", law + "def initial", 1) if law else FIXTURE_HEAD
    return closure("World") + [{"name": "Fixture", "source": declared(head + body)}]


MONOTONE = fixture("""def dec(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit.set({value: 0n})})):
    case written(_): 0n
    case _: state.count
def inc(state: State, context: Abi.Context) -> Activity<Nat>:
  addSelf(context, 1n)
""", law="law counter: monotone(count)\n")

PROBES = fixture("""def peek(state: State, input: {target: String}, context: Abi.Context) -> Activity<Nat>:
  match world.view::<State>({object: {world: "", object: input.target}}):
    case viewed(v): v.state.count
    case _: 999n
def relay(state: State, input: {target: String, method: String}, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Nat>({object: {world: "", object: input.target}, method: input.method, argument: {}}):
    case returned(r): finish(context, r.result)
    case _: 997n
def finish(context: Abi.Context, result: Nat) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit.add({delta: 10n})})):
    case written(_): result
    case _: 996n
def grow(state: State, input: {by: Nat}, context: Abi.Context) -> State:
  {count: state.count + input.by}
""")


PRIVATE_PROBES = fixture("""def probe(state: State, input: {target: String}, context: Abi.Context) -> Activity<Nat>:
  match world.view::<State>({object: {world: "", object: input.target}}):
    case viewed(v): addSelf(context, v.state.count)
    case _: addSelf(context, 100n)
""")


class TurnWorld(HostCase):
    def create(self, obj, modules, count):
        r = self.host.send(op="world-create", principal="ember", identity="create-" + obj,
                           object=obj, modules=modules, entry="initial", seed=record(count=nat(count)))
        self.assertEqual(r["status"], "created", r)
        return r

    def turn(self, obj, method, argument=None, identity=None, principal="ember", reach=None, **limits):
        self.n = getattr(self, "n", 0) + 1
        request = dict(op="world-turn", principal=principal, object=obj, method=method,
                       argument=argument or record(), identity=identity or f"t{self.n}")
        if reach:
            request["reach"] = reach
        if limits:
            request["limits"] = limits
        return self.host.send(**request)

    def count(self, obj):
        v = self.host.send(op="world-view", principal="ember", object=obj)
        self.assertEqual(v["status"], "viewed", v)
        return v["version"], v["state"]["fields"][0]["value"]["value"]

    def height(self):
        return self.host.send(op="world-status")["height"]


class CounterTurns(TurnWorld):
    """Retry and duplicateIdentity on a turn are test_properties (RandomHour)."""

    def test_the_receipt_names_its_root_and_ticks_and_unknown_object_method_and_budget_are_refused(self):
        self.create("c1", counter_modules(), 4)
        read = cid_of(self.host.send(op="world-view", principal="ember", object="c1")["state"])
        r = self.turn("c1", "bump")
        # The root names the version the turn read; that state's CID is read from the journal.
        self.assertEqual(r["receipt"]["roots"], [{"object": "c1", "version": 0}])
        self.assertEqual(self.host.send(op="world-state-cid", principal="ember", object="c1", version=0)["cid"], read)
        self.assertEqual((r["result"], r["receipt"]["outcome"]["writes"][0]["version"]), (nat(5), 1))
        self.assertGreater(r["ticksUsed"], 0)
        self.assertEqual(self.turn("ghost", "bump")["receipt"]["outcome"]["class"], "unknownObject")
        h = self.height()
        r = self.turn("c1", "nosuchmethod")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], self.height()), ("refused", "noMethod", h + 1))
        out = self.turn("c1", "bump", ticks="10")["receipt"]["outcome"]
        self.assertEqual((out["class"], out["reason"]), ("budget", "the turn ran out of ticks; make it smaller, or send it again later."))
        self.assertEqual(self.count("c1"), (1, "5"))
        # The default budget is the kernel cap, and a request cannot exceed it.
        self.assertEqual(self.turn("c1", "bump", ticks="1000001")["status"], "error")
        self.assertEqual(self.turn("c1", "bump", ticks="1000000")["status"], "admitted")

    def test_monotone_law_refuses_the_decrement_and_leaves_state_unchanged(self):
        self.create("m", MONOTONE, 5)
        r = self.turn("m", "dec")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["clause"]), ("refused", "lawRefused", "counter"))
        self.assertEqual(self.count("m"), (0, "5"))
        self.assertEqual(self.turn("m", "inc")["status"], "admitted")
        self.assertEqual(self.count("m"), (1, "6"))


class Plans(TurnWorld):
    def setUp(self):
        super().setUp()
        self.create("a", PROBES, 1)
        self.create("b", counter_modules(), 7)

    def test_a_view_records_its_root_and_a_call_commits_callee_and_caller_in_one_entry(self):
        r = self.turn("a", "peek", record(target=label("b")))
        self.assertEqual((r["result"], [x["object"] for x in r["receipt"]["roots"]]), (nat(7), ["a", "b"]))
        self.assertEqual(self.turn("a", "peek", record(target=label("ghost")))["result"], nat(999))
        h = self.height()
        r = self.turn("a", "relay", record(target=label("b"), method=label("bump")))
        self.assertEqual((r["status"], r["result"], self.height()), ("admitted", nat(8), h + 1))
        self.assertEqual([w["object"] for w in r["receipt"]["outcome"]["writes"]], ["b", "a"])
        self.assertEqual((self.count("a"), self.count("b")), ((1, "11"), (1, "8")))
        # A pure method commits its result as a set of every field.
        self.assertEqual(self.turn("a", "grow", record(by=nat(4)))["status"], "admitted")
        self.assertEqual(self.count("a"), (2, "15"))

    def test_a_failing_callee_write_refuses_the_whole_turn(self):
        self.create("m", MONOTONE, 5)
        r = self.turn("a", "relay", record(target=label("m"), method=label("dec")))
        self.assertEqual(r["receipt"]["outcome"]["clause"], "counter")
        self.assertEqual((self.count("a"), self.count("m")), ((0, "1"), (0, "5")))


NAMES_SOURCE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  names: Lists.List<String>
def initial() -> State:
  {names: Lists.List::<String>.nil()}
def add(state: State, input: {text: String}, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {names: Plans.Entries::<String, String>.append({item: input.text})})):
    case written(_): 1n
    case _: 0n
def drop(state: State, input: {text: String}, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {names: Plans.Entries::<String, String>.removeItem({item: input.text})})):
    case written(_): 1n
    case _: 0n
def fix(state: State, input: {item: String, text: String}, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {names: Plans.Entries::<String, String>.amendItem({item: input.item, change: input.text})})):
    case written(_): 1n
    case _: 0n
""")


def names_modules():
    return closure("List", "World") + [{"name": "Names", "source": NAMES_SOURCE}]


def list_items(state):
    names = [f["value"] for f in state["fields"] if f["name"] == "names"][0]
    return [item["value"] for item in names["items"]]


class ListEdits(TurnWorld):
    def test_append_amend_and_remove_by_item_refuse_an_absent_one_and_replay(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk", object="n",
                           modules=names_modules(), entry="initial", seed=record(names={"tag": "list", "items": []}))
        self.assertEqual(r["status"], "created", r)
        for text in ("one", "two", "three", "four"):
            self.assertEqual(self.turn("n", "add", record(text=label(text)))["status"], "admitted")
        view = lambda: self.host.send(op="world-view", principal="e", object="n")
        self.assertEqual(self.turn("n", "fix", record(item=label("two"), text=label("TWO")))["status"], "admitted")
        self.assertEqual(self.turn("n", "drop", record(text=label("three")))["status"], "admitted")
        self.assertEqual(self.turn("n", "drop", record(text=label("one")))["status"], "admitted")
        self.assertEqual(list_items(view()["state"]), ["TWO", "four"])
        version = view()["version"]
        for method, arg in (("drop", record(text=label("one"))), ("fix", record(item=label("other"), text=label("x")))):
            self.assertEqual(self.turn("n", method, arg)["receipt"]["outcome"]["class"], "absentItem", method)
        self.assertEqual(view()["version"], version)
        before = view()
        self.reopen()
        self.assertEqual(view(), before)


class ReadPolicy(TurnWorld):
    def setUp(self):
        super().setUp()
        self.create("a", PRIVATE_PROBES, 1)
        r = self.host.send(op="world-create", principal="ember", identity="mk-priv", object="priv",
                           modules=counter_modules(), entry="initial", seed=record(count=nat(7)),
                           read={"principals": ["ember"]})
        self.assertEqual(r["status"], "created", r)

    def view(self, who, obj="priv"):
        return self.host.send(op="world-view", principal=who, object=obj)

    def test_a_private_object_is_viewed_by_its_creator_denied_to_a_stranger_across_restart(self):
        self.assertEqual(self.view("ember")["status"], "viewed")
        self.assertEqual(self.view("stranger"), {"status": "denied", "object": "priv"})
        self.assertEqual(self.view("stranger", "a")["status"], "viewed")  # default is public
        r = self.host.send(op="world-create", principal="ember", identity="bad", object="p2", modules=counter_modules(),
                           entry="initial", seed=record(count=nat(0)), read={"principals": "ember"})
        self.assertEqual(r["status"], "error")
        self.reopen()
        self.assertEqual((self.view("stranger")["status"], self.view("ember")["status"]), ("denied", "viewed"))

    def test_an_in_turn_view_is_denied_without_a_root_to_a_stranger_and_rooted_for_its_reader(self):
        r = self.turn("a", "probe", record(target=label("priv")), principal="stranger")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual([x["object"] for x in r["receipt"]["roots"]], ["a"])
        self.assertEqual((self.count("a"), self.count("priv")), ((1, "101"), (0, "7")))
        r = self.turn("a", "probe", record(target=label("priv")), principal="ember")
        self.assertEqual([x["object"] for x in r["receipt"]["roots"]], ["a", "priv"])
        self.assertEqual(self.count("a"), (2, "108"))


if __name__ == "__main__":
    unittest.main()
