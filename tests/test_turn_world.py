"""world-turn: activities run against the durable store and commit once.

Counter and Bell are the real world/objects files (each exports `initial`); the other objects are fixtures that each isolate one rule.
"""
import json
import os
import re
import subprocess
import tempfile
import time
import unittest

from tests import host
from tests.host import Host, HostCase

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BINARY = host.binary()
IMPORT = re.compile(r"^import \./(\w+)\.obend", re.M)


def modules_on_disk():
    found = {}
    for sub in ("lib", "objects"):
        for directory, _, files in os.walk(os.path.join(ROOT, "world", sub)):
            for name in files:
                if name.endswith(".obend"):
                    found[name[:-6]] = os.path.join(directory, name)
    return found


ON_DISK = modules_on_disk()


def closure(name, seen=None, out=None, override=None):
    """Module `name` and its imports, imports first; `override` replaces a source."""
    seen = set() if seen is None else seen
    out = [] if out is None else out
    if name in seen:
        return out
    seen.add(name)
    if override and name in override:
        source = override[name]
    else:
        with open(ON_DISK[name]) as handle:
            source = handle.read()
    for dep in IMPORT.findall(source):
        closure(dep, seen, out, override)
    out.append({"name": name, "source": source})
    return out


def counter_modules():
    return closure("Counter")


FIXTURE_HEAD = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits, {}>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {count: 5n}
def addSelf(context: Abi.Context, n: Nat) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: n})}})):
    case written(_): 1n
    case _: 0n
"""


def fixture(body, law=""):
    head = FIXTURE_HEAD.replace("def initial", law + "def initial", 1) if law else FIXTURE_HEAD
    return closure("Plan") + [{"name": "Fixture", "source": head + body}]


MONOTONE = fixture("""def dec(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.set({value: 0n})}})):
    case written(_): 0n
    case _: state.count
def inc(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  addSelf(context, 1n)
""", law="law counter: monotone(count)\n")

PROBES = fixture("""def sneak(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: {world: "", object: input.target}, edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case refused(_): addSelf(context, 1n)
    case _: 99n
def peek(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.view({object: {world: "", object: input.target}})):
    case viewed(v): v.state.count
    case _: 999n
def peekThenWrite(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.view({object: {world: "", object: input.target}})):
    case viewed(v): other(input.target, v.state.count)
    case _: 999n
def other(target: String, seen: Nat) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: {world: "", object: target}, edits: {count: Plans.Edit::<Nat, Nat>.add({delta: seen})}})):
    case written(_): seen
    case _: 998n
def relay(state: State, input: {target: String, method: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.call({object: {world: "", object: input.target}, method: input.method, argument: {}})):
    case returned(r): finish(context, r.result)
    case _: 997n
def finish(context: Abi.Context, result: Nat) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 10n})}})):
    case written(_): result
    case _: 996n
sum Odd:
  shout: {text: String}
def shout(state: State, input: {target: String}, context: Abi.Context) -> Activity<Odd, Response, Nat>:
  match perform(Odd.shout({text: "b"})):
    case _: 0n
def grow(state: State, input: {by: Nat}, context: Abi.Context) -> State:
  {count: state.count + input.by}
""")


PRIVATE_PROBES = fixture("""def probe(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.view({object: {world: "", object: input.target}})):
    case viewed(v): addSelf(context, v.state.count)
    case _: addSelf(context, 100n)
""")


def nat(n):
    return {"tag": "natural", "value": str(n)}


def record(**fields):
    return {"tag": "record", "fields": [{"name": k, "value": v} for k, v in fields.items()]}


def label(s):
    return {"tag": "label", "value": s}


class TurnWorld(HostCase):
    def create(self, obj, modules, count):
        r = self.host.send(op="world-create", principal="ember", identity="create-" + obj,
                           object=obj, modules=modules, entry="initial", seed=record(count=nat(count)))
        self.assertEqual(r["status"], "created", r)
        return r

    def turn(self, obj, method, argument=None, identity=None, principal="ember", **limits):
        self.n = getattr(self, "n", 0) + 1
        request = dict(op="world-turn", principal=principal, object=obj, method=method,
                       argument=argument or record(), identity=identity or f"t{self.n}")
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
    def test_bump_three_times_leaves_count_three_at_version_three(self):
        self.create("c1", counter_modules(), 0)
        for _ in range(3):
            r = self.turn("c1", "bump")
            self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.count("c1"), (3, "3"))

    def test_the_receipt_lists_the_object_as_first_root_and_reports_ticks(self):
        self.create("c1", counter_modules(), 4)
        r = self.turn("c1", "bump")
        self.assertEqual(r["receipt"]["roots"], [{"object": "c1", "version": 0}])
        self.assertEqual(r["result"], nat(5))
        self.assertGreater(r["ticksUsed"], 0)
        self.assertEqual(r["receipt"]["outcome"]["writes"][0]["version"], 1)

    def test_retry_of_the_same_identity_returns_the_same_receipt_and_no_second_bump(self):
        self.create("c1", counter_modules(), 0)
        first = self.turn("c1", "bump", identity="once")
        h = self.height()
        again = self.turn("c1", "bump", identity="once")
        self.assertEqual(again, first)
        self.assertEqual(self.height(), h)
        self.assertEqual(self.count("c1"), (1, "1"))

    def test_same_identity_for_another_turn_is_duplicate_identity_and_writes_nothing(self):
        self.create("c1", counter_modules(), 0)
        self.turn("c1", "bump", identity="once")
        h = self.height()
        r = self.host.send(op="world-turn", principal="ember", object="c1", method="bump",
                           argument=record(x=nat(1)), identity="once")
        self.assertEqual((r["status"], r["class"]), ("refused", "duplicateIdentity"))
        self.assertEqual(self.height(), h)

    def test_unknown_object_is_refused_by_class_and_unknown_method_is_a_request_error(self):
        self.create("c1", counter_modules(), 0)
        r = self.turn("ghost", "bump")
        self.assertEqual(r["receipt"]["outcome"]["class"], "unknownObject")
        h = self.height()
        r = self.turn("c1", "nosuchmethod")
        self.assertEqual(r["status"], "error")
        self.assertEqual(self.height(), h)

    def test_restart_replays_to_the_same_view_and_receipts(self):
        self.create("c1", counter_modules(), 0)
        receipts = [self.turn("c1", "bump", identity=f"r{i}") for i in range(3)]
        before = self.count("c1")
        self.reopen()
        self.assertEqual(self.count("c1"), before)
        again = self.host.send(op="world-turn", principal="ember", object="c1", method="bump",
                               argument=record(), identity="r1")
        self.assertEqual(again, receipts[1])
        nxt = self.turn("c1", "bump")
        self.assertEqual(nxt["status"], "admitted")
        self.assertEqual(self.count("c1"), (4, "4"))

    def test_a_ten_tick_budget_is_refused_as_budget_naming_the_resource(self):
        self.create("c1", counter_modules(), 0)
        r = self.turn("c1", "bump", ticks="10")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["reason"]), ("refused", "budget", "ticks"))
        self.assertEqual(self.count("c1"), (0, "0"))


class Ticks(TurnWorld):
    def test_the_default_turn_budget_is_the_kernel_cap_and_a_request_cannot_exceed_it(self):
        self.create("c1", counter_modules(), 0)
        self.assertEqual(self.turn("c1", "bump")["status"], "admitted")
        r = self.turn("c1", "bump", ticks="1000001")
        self.assertEqual(r["status"], "error")
        self.assertEqual(self.turn("c1", "bump", ticks="1000000")["status"], "admitted")


class Laws(TurnWorld):
    def test_monotone_law_refuses_the_decrement_and_leaves_state_unchanged(self):
        self.create("m", MONOTONE, 5)
        r = self.turn("m", "dec")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["clause"]), ("refused", "lawRefused", "counter"))
        self.assertEqual(self.count("m"), (0, "5"))
        ok = self.turn("m", "inc")
        self.assertEqual(ok["status"], "admitted")
        self.assertEqual(self.count("m"), (1, "6"))


class Plans(TurnWorld):
    def setUp(self):
        super().setUp()
        self.create("a", PROBES, 1)
        self.create("b", counter_modules(), 7)

    def target(self, name):
        return record(target=label(name))

    def test_view_of_another_object_records_it_as_a_root_and_returns_its_state(self):
        r = self.turn("a", "peek", self.target("b"))
        self.assertEqual(r["result"], nat(7))
        self.assertEqual([x["object"] for x in r["receipt"]["roots"]], ["a", "b"])

    def test_view_of_an_unknown_object_is_answered_denied(self):
        r = self.turn("a", "peek", self.target("ghost"))
        self.assertEqual(r["result"], nat(999))

    def test_a_write_without_a_view_is_answered_refused_in_turn_and_the_turn_still_commits(self):
        r = self.turn("a", "sneak", self.target("b"))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)))
        self.assertEqual(self.count("b"), (0, "7"))
        self.assertEqual(self.count("a"), (1, "2"))

    def test_a_viewed_object_still_cannot_be_written_by_another(self):
        r = self.turn("a", "peekThenWrite", self.target("b"))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(998)))
        self.assertEqual(self.count("b"), (0, "7"))

    def test_call_commits_the_callee_and_the_caller_atomically_in_one_entry(self):
        h = self.height()
        r = self.turn("a", "relay", record(target=label("b"), method=label("bump")))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(8)))
        self.assertEqual(self.height(), h + 1)
        self.assertEqual([w["object"] for w in r["receipt"]["outcome"]["writes"]], ["b", "a"])
        self.assertEqual((self.count("a"), self.count("b")), ((1, "11"), (1, "8")))

    def test_a_failing_callee_write_refuses_the_whole_turn(self):
        self.create("m", MONOTONE, 5)
        # The callee's law refuses its decrement; nothing of the caller may land either.
        r = self.turn("a", "relay", record(target=label("m"), method=label("dec")))
        self.assertEqual(r["receipt"]["outcome"]["clause"], "counter")
        self.assertEqual((self.count("a"), self.count("m")), ((0, "1"), (0, "5")))

    def test_an_unsupported_plan_refuses_the_turn_by_name_and_admits_nothing(self):
        r = self.turn("a", "shout", self.target("b"))
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["reason"]),
                         ("refused", "evaluation", "plan not supported: shout"))
        self.assertEqual((self.count("a"), self.count("b")), ((0, "1"), (0, "7")))

    def test_a_pure_method_commits_its_result_as_a_set_of_every_field(self):
        r = self.turn("a", "grow", record(by=nat(4)))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.count("a"), (1, "5"))


NAMES_SOURCE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
record State:
  names: Lists.List<String>
record Edits:
  names: Plans.Entries<String, String>
type Plan = Plans.Plan<Edits, {}>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {names: Lists.List::<String>.nil()}
def add(state: State, input: {text: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {names: Plans.Entries::<String, String>.append({item: input.text})}})):
    case written(_): 1n
    case _: 0n
def drop(state: State, input: {index: Nat}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {names: Plans.Entries::<String, String>.remove({index: input.index})}})):
    case written(_): 1n
    case _: 0n
def fix(state: State, input: {index: Nat, text: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {names: Plans.Entries::<String, String>.amend({index: input.index, change: input.text})}})):
    case written(_): 1n
    case _: 0n
"""


def names_modules():
    modules = closure("List") + [m for m in closure("Plan") if m["name"] != "List"]
    seen, out = set(), []
    for m in modules:
        if m["name"] not in seen:
            seen.add(m["name"])
            out.append(m)
    return out + [{"name": "Names", "source": NAMES_SOURCE}]


def list_items(state):
    names = [f["value"] for f in state["fields"] if f["name"] == "names"][0]
    out = []
    while names["label"] == "cons":
        f = {x["name"]: x["value"] for x in names["payload"]["fields"]}
        out.append(f["head"]["value"])
        names = f["tail"]
    return out


class ListEdits(TurnWorld):
    def test_append_then_amend_on_a_list_field_read_back_in_order_and_replayed(self):
        empty = {"tag": "record", "fields": []}
        seed = record(names={"tag": "variant", "label": "nil", "payload": empty})
        r = self.host.send(op="world-create", principal="ember", identity="mk", object="n",
                           modules=names_modules(), entry="initial", seed=seed)
        self.assertEqual(r["status"], "created", r)
        for text in ("one", "two", "three"):
            r = self.turn("n", "add", record(text=label(text)))
            self.assertEqual(r["status"], "admitted", r)
        r = self.turn("n", "fix", record(index=nat(1), text=label("TWO")))
        self.assertEqual(r["status"], "admitted", r)
        view = lambda: self.host.send(op="world-view", principal="e", object="n")["state"]
        self.assertEqual(list_items(view()), ["one", "TWO", "three"])
        before = view()
        self.reopen()
        self.assertEqual(view(), before)

    def test_remove_deletes_the_element_at_the_index_refuses_past_the_end_and_replays(self):
        empty = {"tag": "record", "fields": []}
        self.host.send(op="world-create", principal="ember", identity="mk", object="n",
                       modules=names_modules(), entry="initial",
                       seed=record(names={"tag": "variant", "label": "nil", "payload": empty}))
        for text in ("one", "two", "three"):
            self.turn("n", "add", record(text=label(text)))
        view = lambda: self.host.send(op="world-view", principal="e", object="n")
        self.assertEqual(self.turn("n", "drop", record(index=nat(1)))["status"], "admitted")
        self.assertEqual(list_items(view()["state"]), ["one", "three"])
        self.assertEqual(self.turn("n", "drop", record(index=nat(0)))["status"], "admitted")
        self.assertEqual(list_items(view()["state"]), ["three"])
        version = view()["version"]
        r = self.turn("n", "drop", record(index=nat(1)))
        self.assertEqual(r["receipt"]["outcome"]["class"], "outOfRange")
        self.assertEqual(view()["version"], version)
        before = view()
        self.reopen()
        self.assertEqual(view(), before)

    def test_amend_past_the_end_is_refused_and_changes_nothing(self):
        empty = {"tag": "record", "fields": []}
        self.host.send(op="world-create", principal="ember", identity="mk", object="n",
                       modules=names_modules(), entry="initial",
                       seed=record(names={"tag": "variant", "label": "nil", "payload": empty}))
        self.turn("n", "add", record(text=label("only")))
        r = self.turn("n", "fix", record(index=nat(5), text=label("x")))
        self.assertEqual(r["receipt"]["outcome"]["class"], "outOfRange")
        self.assertEqual(self.host.send(op="world-view", principal="e", object="n")["version"], 1)


class BellList(TurnWorld):
    def test_two_rains_append_in_order_to_the_cons_list_and_replay_to_the_same_state(self):
        modules = closure("Bell")
        empty = {"tag": "record", "fields": []}
        seed = record(planter=label("glm"), colour={"tag": "variant", "label": "silver", "payload": empty},
                      seed=label("s"), rains={"tag": "variant", "label": "nil", "payload": empty},
                      rung={"tag": "boolean", "value": False},
                      door=record(world=label(""), object=label("")), lastDelivery=label(""),
                      planting=record(principal=label(""), intent=label("")))
        r = self.host.send(op="world-create", principal="ember", identity="mk", object="bell",
                           modules=modules, entry="initial", seed=seed)
        self.assertEqual(r["status"], "created", r)
        for who, text in (("kimik3", "one"), ("gemini", "two")):
            r = self.turn("bell", "rain", record(author=label(who), text=label(text)))
            self.assertEqual(r["status"], "admitted", r)
        before = self.host.send(op="world-view", principal="e", object="bell")["state"]

        def authors(state):
            rains = [f["value"] for f in state["fields"] if f["name"] == "rains"][0]
            out = []
            while rains["label"] == "cons":
                f = {x["name"]: x["value"] for x in rains["payload"]["fields"]}
                out.append({x["name"]: x["value"]["value"] for x in f["head"]["fields"]}["author"])
                rains = f["tail"]
            return out
        self.assertEqual(authors(before), ["kimik3", "gemini"])
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="e", object="bell")["state"], before)


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

    def test_a_private_object_is_viewed_by_its_creator_and_denied_to_a_stranger(self):
        self.assertEqual(self.view("ember")["status"], "viewed")
        d = self.view("stranger")
        self.assertEqual(d, {"status": "denied", "object": "priv"})
        self.assertEqual(self.view("stranger", "a")["status"], "viewed")  # default is public

    def test_a_denied_in_turn_view_records_no_root_and_the_turn_still_commits(self):
        r = self.turn("a", "probe", record(target=label("priv")), principal="stranger")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual([x["object"] for x in r["receipt"]["roots"]], ["a"])
        self.assertEqual(self.count("a"), (1, "101"))
        self.assertEqual(self.count("priv"), (0, "7"))

    def test_a_permitted_principal_view_in_turn_records_the_root_and_sees_the_state(self):
        r = self.turn("a", "probe", record(target=label("priv")), principal="ember")
        self.assertEqual([x["object"] for x in r["receipt"]["roots"]], ["a", "priv"])
        self.assertEqual(self.count("a"), (1, "8"))

    def test_the_policy_survives_a_restart(self):
        self.reopen()
        self.assertEqual(self.view("stranger")["status"], "denied")
        self.assertEqual(self.view("ember")["status"], "viewed")

    def test_a_malformed_policy_refuses_creation(self):
        r = self.host.send(op="world-create", principal="ember", identity="bad", object="p2",
                           modules=counter_modules(), entry="initial", seed=record(count=nat(0)),
                           read={"principals": "ember"})
        self.assertEqual(r["status"], "error")


class Maximum(TurnWorld):
    def test_two_hundred_bumps_in_one_process_then_replay(self):
        self.create("c1", counter_modules(), 0)
        t0 = time.time()
        for i in range(200):
            r = self.turn("c1", "bump", identity=f"b{i}")
            self.assertEqual(r["status"], "admitted", r)
        took = time.time() - t0
        self.assertEqual(self.count("c1"), (200, "200"))
        head = self.host.send(op="world-status")["head"]
        t1 = time.time()
        self.reopen()
        replay = time.time() - t1
        print(f"\n  200 bumps {took:.2f}s, reopen {replay:.2f}s")
        self.assertLess(took, 5.0)
        self.assertEqual(self.host.send(op="world-status")["head"], head)
        self.assertEqual(self.count("c1"), (200, "200"))


if __name__ == "__main__":
    unittest.main()
