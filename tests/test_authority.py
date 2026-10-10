"""A write changes only the running object; a change to another object is a call its own law judges,
and the law sees who called.

Evidence for FOUNDATION §3, §4 (layer: host).

The authority model: a write changes only the running object, cross-object change is
a call judged by the callee's own law, and the law sees who called.

Each case is named by the defect that would make it fail. The fixture object `Ledger`
has one method per behaviour; the laws are inserted before `def initial` per test.
"""
import json
import unittest

from tests.test_replay import relation
from tests.test_chain import field, nil, reference
from tests.test_turn_world import TurnWorld, closure, label, nat, record
from tests.test_turn_world import declared

LEDGER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Variant.obend as Variant
record Out:
  text: String
  n: Nat
record Arg:
  n: Nat
record State:
  count: Nat
  lastBy: String
  entries: Lists.List<String>
  planting: String
record Edits:
  count: Plans.Edit<Nat, Nat>
  lastBy: Plans.Edit<String, {}>
  entries: Plans.Entries<String, String>
  planting: Plans.Edit<String, {}>
type Plan = Variant.Plan<Edits>
type Response = Variant.Response<State, Out>
def initial() -> State:
  {count: 0n, lastBy: "", entries: Lists.List::<String>.nil(), planting: ""}
def keep() -> Edits:
  {count: Plans.Edit::<Nat, Nat>.keep({}), lastBy: Plans.Edit::<String, {}>.keep({}), entries: Plans.Entries::<String, String>.keep({}), planting: Plans.Edit::<String, {}>.keep({})}
def out(text: String, n: Nat) -> Out:
  {text: text, n: n}
def commit(context: Abi.Context, edits: Edits, text: String) -> Activity<Plan, Response, Out>:
  match perform(Plan.write({object: Plans.self(context), edits: edits})):
    case written(_): out(text, 1n)
    case refused(r): out(r.clause, 0n)
    case _: out("unanswered", 0n)
def bumped() -> Edits:
  extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Out>:
  commit(context, bumped(), "bumped")
def stamp(state: State, input: {who: String}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  commit(context, extend(keep(), {lastBy: Plans.Edit::<String, {}>.set({value: input.who})}), "stamped")
def append(state: State, input: {item: String}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  commit(context, extend(keep(), {entries: Plans.Entries::<String, String>.append({item: input.item})}), "appended")
def amendOne(state: State, input: {old: String, item: String}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  commit(context, extend(keep(), {entries: Plans.Entries::<String, String>.amendItem({item: input.old, change: input.item})}), "amended")
def removeOne(state: State, input: {item: String}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  commit(context, extend(keep(), {entries: Plans.Entries::<String, String>.removeItem({item: input.item})}), "removed")
def plant(state: State, input: {value: String}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  commit(context, extend(keep(), {planting: Plans.Edit::<String, {}>.set({value: input.value})}), "planted")
def who(state: State, context: Abi.Context) -> Activity<Plan, Response, Out>:
  match perform(Plan.view({object: Plans.self(context)})):
    case _: out(context.caller, 0n)
def facts(state: State, context: Abi.Context) -> Activity<Plan, Response, Out>:
  match perform(Plan.view({object: Plans.self(context)})):
    case _: out(context.intent, context.height)
def meddle(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  match perform(Plan.write({object: {world: "", object: input.target}, edits: bumped()})):
    case refused(r): commit(context, bumped(), r.clause)
    case _: commit(context, bumped(), "meddled")
def tamper(state: State, context: Abi.Context) -> Activity<Plan, Response, Out>:
  match perform(Plan.write({object: {world: "", object: context.caller}, edits: bumped()})):
    case refused(r): out(r.clause, 0n)
    case _: out("rewrote its caller", 1n)
def relay(state: State, input: {target: String, method: String}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  match perform(Plan.call({object: {world: "", object: input.target}, method: input.method, argument: Data.of::<Arg>({n: 0n})})):
    case returned(r): commit(context, bumped(), r.result.text)
    case _: out("unanswered", 0n)
def dive(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  match perform(Plan.write({object: Plans.self(context), edits: bumped()})):
    case _: deeper(input.n, context)
def deeper(n: Nat, context: Abi.Context) -> Activity<Plan, Response, Out>:
  if n == 0n then out("bottom", 0n) else down(n, context)
def down(n: Nat, context: Abi.Context) -> Activity<Plan, Response, Out>:
  match perform(Plan.call({object: Plans.self(context), method: "dive", argument: Data.of::<Arg>({n: n - 1n})})):
    case returned(r): out(r.result.text, 1n)
    case _: out("unanswered", 0n)
def grow(state: State, input: {n: Nat, source: String}, context: Abi.Context) -> Activity<Plan, Response, Out>:
  match perform(Plan.write({object: Plans.self(context), edits: extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: input.n})})})):
    case _: swap(context, input.source)
def swap(context: Abi.Context, source: String) -> Activity<Plan, Response, Out>:
  match perform(Plan.reprogram({object: Plans.self(context), package: source, migration: ""})):
    case reprogrammed(_): out("reprogrammed", 1n)
    case refused(r): out(r.clause, 0n)
    case _: out("unanswered", 0n)
""")


def ledger(law="", comment=""):
    source = LEDGER.replace("def initial", law + "def initial", 1) if law else LEDGER
    return source + comment


def modules(law="", comment=""):
    return closure("Variant") + [{"name": "Ledger", "source": ledger(law, comment)}]


def seed(count=0, last_by="ember", entries=None, planting=""):
    return record(count=nat(count), lastBy=label(last_by), entries=entries or nil(), planting=label(planting))


def items(*texts):
    return {"tag": "list", "items": [label(text) for text in texts]}


def text_of(result):
    return [f["value"]["value"] for f in result["fields"] if f["name"] == "text"][0]


class Authority(TurnWorld):
    def state(self, name):
        view = self.host.send(op="world-view", principal="ember", object=name)
        self.assertEqual(view["status"], "viewed", view)
        return view["state"]

    def ledger(self, name, law="", **seed_fields):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=modules(law), entry="initial", seed=seed(**seed_fields))
        self.assertEqual(r["status"], "created", r)

    def count(self, name):
        return field(self.state(name), "count")["value"]

    def version(self, name):
        return self.host.send(op="world-view", principal="ember", object=name)["version"]

    def outcome(self, r):
        return r["receipt"]["outcome"]

    def last_entry(self):
        status = self.host.send(op="world-status")["height"]
        with open(self.path) as handle:
            return json.loads(handle.read().splitlines()[status - 1])


class WriteIsSelfOnly(Authority):
    def setUp(self):
        super().setUp()
        self.ledger("a")
        self.ledger("b")

    def test_a_method_that_writes_another_object_gets_notSelf_and_the_turn_still_commits_its_own_write(self):
        r = self.turn("a", "meddle", record(target=label("b")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(text_of(r["result"]), "notSelf")
        self.assertEqual((self.count("a"), self.version("a")), ("1", 1))
        self.assertEqual((self.count("b"), self.version("b")), ("0", 0))

    def test_a_callee_cannot_rewrite_its_caller(self):
        r = self.turn("a", "relay", record(target=label("b"), method=label("tamper")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(text_of(r["result"]), "notSelf")
        # Only the caller's own write landed; the callee wrote nothing at all.
        self.assertEqual((self.count("a"), self.version("a")), ("1", 1))
        self.assertEqual(self.version("b"), 0)

    def test_a_callee_writes_itself_and_the_journal_names_who_called(self):
        r = self.turn("a", "relay", record(target=label("b"), method=label("bump")))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual((self.count("a"), self.count("b")), ("1", "1"))
        writes = {w["object"]: w for w in self.outcome(r)["writes"]}
        self.assertEqual(writes["b"]["callers"], ["a"])
        self.assertEqual(writes["a"]["callers"], [""])
        self.assertEqual(writes["b"]["kinds"], [0])

    def test_the_call_depth_cap_refuses_a_200_deep_dive_and_commits_nothing(self):
        before = self.host.send(op="world-status")["height"]
        r = self.turn("a", "dive", record(n=nat(200)))
        out = self.outcome(r)
        self.assertEqual((r["status"], out["class"], out["reason"]), ("refused", "evaluation", "call depth exceeded"))
        self.assertEqual((self.count("a"), self.version("a")), ("0", 0))
        self.assertEqual(self.host.send(op="world-status")["height"], before + 1)

    def test_a_dive_within_the_cap_commits_every_level_as_one_version(self):
        r = self.turn("a", "dive", record(n=nat(3)))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual((self.count("a"), self.version("a")), ("4", 1))
        self.assertEqual(self.outcome(r)["writes"][0]["callers"], ["", "a", "a", "a"])


class LawsOnWho(Authority):
    def test_directory_remove_by_a_stranger_is_refused_by_the_directorys_law(self):
        door = record(label=label("garden"), description=label("a garden"), to=reference("garden"))
        r = self.host.send(op="world-create", principal="ember", identity="mk-dir", object="dir",
                           modules=closure("Directory"), entry="initial",
                           seed=record(owner=label("ember"), doors=relation(), greeted=relation()))
        self.assertEqual(r["status"], "created", r)
        self.assertEqual(self.turn("dir", "add", record(door=door))["status"], "admitted")
        version = self.version("dir")
        stranger = self.turn("dir", "remove", record(door=record(label=label("garden"))), principal="kim")
        self.assertEqual((stranger["status"], self.outcome(stranger)["class"], self.outcome(stranger)["clause"]),
                         ("refused", "lawRefused", "owner"))
        self.assertEqual(self.version("dir"), version)
        owner = self.turn("dir", "remove", record(door=record(label=label("garden"))))
        self.assertEqual(owner["status"], "admitted", owner)
        self.assertEqual(self.version("dir"), version + 1)

    def test_a_law_on_the_author_admits_the_principal_and_refuses_another_name(self):
        self.ledger("a", "law author: new.lastBy == request.subject\n")
        ok = self.turn("a", "stamp", record(who=label("ember")))
        self.assertEqual(ok["status"], "admitted", ok)
        forged = self.turn("a", "stamp", record(who=label("kim")))
        self.assertEqual((forged["status"], self.outcome(forged)["clause"]), ("refused", "author"))
        by_kim = self.turn("a", "stamp", record(who=label("kim")), principal="kim")
        self.assertEqual(by_kim["status"], "admitted", by_kim)
        self.assertEqual(field(self.state("a"), "lastBy"), label("kim"))

    def test_append_only_admits_an_append_and_refuses_an_amend_and_a_remove(self):
        self.ledger("a", "law grow: appendOnly(entries)\n", entries=items("x"))
        self.assertEqual(self.turn("a", "append", record(item=label("y")))["status"], "admitted")
        amend = self.turn("a", "amendOne", record(old=label("x"), item=label("z")))
        self.assertEqual((amend["status"], self.outcome(amend)["clause"]), ("refused", "grow"))
        remove = self.turn("a", "removeOne", record(item=label("x")))
        self.assertEqual((remove["status"], self.outcome(remove)["clause"]), ("refused", "grow"))
        self.assertEqual(self.version("a"), 1)
        self.assertEqual(self.state("a")["fields"][2]["value"], items("x", "y"))

    def test_unchanged_refuses_a_set_of_that_field_and_admits_the_others(self):
        self.ledger("a", "law fixed: unchanged(planting)\n", planting="oak")
        refused = self.turn("a", "plant", record(value=label("elm")))
        self.assertEqual((refused["status"], self.outcome(refused)["clause"]), ("refused", "fixed"))
        self.assertEqual(field(self.state("a"), "planting"), label("oak"))
        self.assertEqual(self.turn("a", "bump")["status"], "admitted")

    def test_request_caller_is_the_calling_objects_id_in_a_call_and_empty_in_a_direct_turn(self):
        law = 'law only: request.kind == 0 implies request.caller == "garden"\n'
        self.ledger("garden")
        self.ledger("bell", law)
        direct = self.turn("bell", "bump")
        self.assertEqual((direct["status"], self.outcome(direct)["clause"]), ("refused", "only"))
        via = self.turn("garden", "relay", record(target=label("bell"), method=label("bump")))
        self.assertEqual(via["status"], "admitted", via)
        self.assertEqual(self.count("bell"), "1")
        # A client cannot name a caller: a direct proposal is caller-less too.
        proposed = self.host.send(op="world-propose", principal="ember", identity="p-bell",
                                  roots=[{"object": "bell", "version": self.version("bell")}],
                                  writes=[{"object": "bell", "edits": {"tag": "record", "fields": [
                                      {"name": "count", "value": {"tag": "variant", "label": "add", "payload": record(delta=nat(1))}}]}}])
        self.assertEqual((proposed["status"], self.outcome(proposed)["clause"]), ("refused", "only"))
        forged = dict(object="bell", edits={"tag": "record", "fields": []}, callers=["garden"])
        r = self.host.send(op="world-propose", principal="ember", identity="p-forged",
                           roots=[{"object": "bell", "version": 1}], writes=[forged])
        self.assertEqual((r["status"], self.outcome(r)["clause"]), ("refused", "only"))

    def test_context_names_the_caller_the_intent_and_the_height(self):
        self.ledger("a")
        self.ledger("b")
        direct = self.turn("a", "who")
        self.assertEqual(text_of(direct["result"]), "")
        r = self.turn("a", "facts", identity="the-intent")
        self.assertEqual(text_of(r["result"]), "the-intent")
        height = [f["value"]["value"] for f in r["result"]["fields"] if f["name"] == "n"][0]
        self.assertEqual(height, str(r["receipt"]["height"] - 1))
        via = self.turn("a", "relay", record(target=label("b"), method=label("who")))
        self.assertEqual(text_of(via["result"]), "a")

    def test_a_bundled_reprogram_and_write_are_judged_for_both_kinds(self):
        law = "law strictWrites: request.kind == 0 implies new.count <= 3\n"
        self.ledger("a", law)
        v2 = ledger(law, "# v2\n")
        small = self.turn("a", "grow", record(n=nat(2), source=label(v2)))
        self.assertEqual(small["status"], "admitted", small)
        self.assertEqual(text_of(small["result"]), "reprogrammed")
        self.assertEqual(self.outcome(small)["reprograms"][0]["object"], "a")
        big = self.turn("a", "grow", record(n=nat(9), source=label(ledger(law, "# v3\n"))))
        out = self.outcome(big)
        self.assertEqual((big["status"], out["class"], out["clause"]), ("refused", "lawRefused", "strictWrites"))
        self.assertEqual(self.count("a"), "2")


class Clauses(Authority):
    def setUp(self):
        super().setUp()
        self.ledger("a", entries=items("x"))

    def edit(self, kind, field_name="count", **payload):
        return {"tag": "record", "fields": [{"name": field_name, "value": {
            "tag": "variant", "label": kind, "payload": record(**payload)}}]}

    def propose(self, identity, edits):
        return self.host.send(op="world-propose", principal="ember", identity=identity,
                              roots=[{"object": "a", "version": self.version("a")}],
                              writes=[{"object": "a", "edits": edits}])

    def test_an_absent_item_is_absentItem(self):
        r = self.turn("a", "amendOne", record(old=label("nobody"), item=label("q")))
        self.assertEqual((r["status"], self.outcome(r)["class"]), ("refused", "absentItem"))
        r = self.turn("a", "removeOne", record(item=label("nobody")))
        self.assertEqual(self.outcome(r)["class"], "absentItem")
        self.assertEqual(self.version("a"), 0)

    def test_state_beyond_its_byte_limit_is_capacity(self):
        r = self.turn("a", "append", record(item=label("x" * 300000)))
        self.assertEqual((r["status"], self.outcome(r)["class"]), ("refused", "capacity"))

    def test_an_edit_the_field_cannot_take_is_typeMismatch(self):
        r = self.propose("add-to-text", self.edit("add", "lastBy", delta=nat(1)))
        self.assertEqual((r["status"], self.outcome(r)["class"]), ("refused", "typeMismatch"))
        r = self.propose("append-to-nat", self.edit("append", "count", item=label("x")))
        self.assertEqual(self.outcome(r)["class"], "typeMismatch")

    def test_a_write_naming_an_object_it_never_rooted_is_not_a_receipt(self):
        r = self.host.send(op="world-propose", principal="ember", identity="blind",
                           roots=[], writes=[{"object": "a", "edits": self.edit("add", delta=nat(1))}])
        self.assertEqual(r["status"], "error")


class HostAssignsTheTurn(Authority):
    def setUp(self):
        super().setUp()
        self.ledger("a")

    def test_a_client_supplied_turn_is_refused_by_name_on_propose_amend_and_reprogram(self):
        height = self.host.send(op="world-status")["height"]
        root = [{"object": "a", "version": 0}]
        replies = [
            self.host.send(op="world-propose", principal="ember", identity="t1", roots=root, writes=[], turn=7),
            self.host.send(op="world-amend", principal="ember", identity="t2", object="a", version=0,
                           law="law open: request.kind == 0", turn=7),
            self.host.send(op="world-reprogram", principal="ember", identity="t3", object="a", version=0,
                           package=ledger("", "# v2\n"), turn=7)]
        for r in replies:
            self.assertEqual(r["status"], "error", r)
            self.assertIn("turn is assigned by the host", r["message"])
        self.assertEqual(self.host.send(op="world-status")["height"], height)

    def test_the_turn_a_law_sees_is_the_height_of_its_entry(self):
        self.ledger("t", "law early: request.turn <= 3\n")
        ok = self.turn("t", "bump")
        self.assertEqual(ok["status"], "admitted", ok)
        self.assertEqual(self.last_entry()["turn"], self.last_entry()["height"])
        late = self.turn("t", "bump")
        self.assertEqual((late["status"], self.outcome(late)["clause"]), ("refused", "early"))


class Restart(Authority):
    def test_restart_replays_callers_kinds_laws_and_the_state_they_produced(self):
        law = 'law only: request.kind == 0 implies request.caller == "garden"\n'
        self.ledger("garden")
        self.ledger("bell", law)
        self.ledger("mine", "law strictWrites: request.kind == 0 implies new.count <= 3\n")
        self.assertEqual(self.turn("garden", "relay", record(target=label("bell"), method=label("bump")))["status"], "admitted")
        self.assertEqual(self.turn("mine", "grow", record(n=nat(2), source=label(ledger(
            "law strictWrites: request.kind == 0 implies new.count <= 3\n", "# v2\n"))))["status"], "admitted")
        self.assertEqual(self.turn("garden", "dive", record(n=nat(3)))["status"], "admitted")
        before = {n: self.host.send(op="world-view", principal="ember", object=n) for n in ("garden", "bell", "mine")}
        height = self.host.send(op="world-status")["height"]
        self.reopen()
        self.assertEqual(self.host.send(op="world-status")["height"], height)
        for n, view in before.items():
            self.assertEqual(self.host.send(op="world-view", principal="ember", object=n), view)
        # The restored law still judges the caller.
        direct = self.turn("bell", "bump")
        self.assertEqual(self.outcome(direct)["clause"], "only")
        # The callers are in the journal, inside the entry hash.
        with open(self.path) as handle:
            lines = handle.read().splitlines()
        self.assertTrue(any('"callers":["garden"]' in line for line in lines))


if __name__ == "__main__":
    unittest.main()
