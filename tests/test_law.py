"""The two-tier law: the Bend predicate judges after the law text admits, reads the roots it
declares, runs under its own budget, and can never seal out a reprogram or amendment.

Evidence for FOUNDATION §4 (layer: host).

The two-tier law: after the law text admits an ordinary write, the
package's Bend `law(old, new, request)` judges it under `Bounds.lawTicks`, reading the objects
`lawReads()` names as roots. Reprograms and amendments are the law text's alone.

    python3 -W error -m unittest tests.test_law -v
"""
import json
import unittest

from tests.test_chain import field
from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record, declared

GUARD = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
law small: new.count <= 100
def initial() -> State:
  {count: 0n}
def add(context: Abi.Context, n: Nat) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: n})}})):
    case _: n
def bump(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  add(context, input.n)
def poke(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  add(context, 1n)
def opened(reads: Lists.List<Abi.Read>) -> Bool:
  match reads:
    case nil(_): false
    case cons(c): c.head.object == "gate" && c.head.version > 0n
def law(old: State, new: State, request: Abi.Request) -> Abi.Verdict:
  if request.method == "poke" then Abi.Verdict.refused({clause: "method", reading: "no poking"}) else if request.context.principal == "mallory" then Abi.Verdict.refused({clause: "principal", reading: "not mallory"}) else if new.count > old.count + 2n then Abi.Verdict.refused({clause: "tooMuch", reading: "two at most"}) else if opened(request.reads) then Abi.Verdict.admitted({}) else Abi.Verdict.refused({clause: "closed", reading: "the gate is closed"})
def lawReads() -> Lists.List<String>:
  Lists.List::<String>.cons({head: "gate", tail: Lists.List::<String>.nil({})})
""")

GATE = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  open: Nat
record Edits:
  open: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {open: 0n}
def open(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {open: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case _: 1n
""")

SPIN = GUARD.replace("""def law(old: State, new: State, request: Abi.Request) -> Abi.Verdict:
  if request.method""", """def spin(n: Nat) -> Bool:
  spin(n + 1n)
def law(old: State, new: State, request: Abi.Request) -> Abi.Verdict:
  if spin(0n) then Abi.Verdict.admitted({}) else if request.method""")

PLAIN = declared(GUARD[:GUARD.index("def opened")], "bump", "poke")


class TwoTier(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("gate", GATE, record(open=nat(0)))
        self.make("g", GUARD, record(count=nat(0)))

    def count(self):
        return field(self.state("g"), "count")["value"]

    def clause(self, r):
        return r["receipt"]["outcome"].get("clause", r["receipt"]["outcome"]["class"]) if r["status"] == "refused" else r["status"]

    def bump(self, n, **kw):
        return self.turn("g", "bump", record(n=nat(n)), **kw)

    def test_the_bend_law_judges_after_the_text_and_reads_its_roots(self):
        self.assertEqual(self.clause(self.bump(1)), "closed")
        self.assertEqual(self.turn("gate", "open")["status"], "admitted")
        r = self.bump(2)
        self.assertEqual(r["status"], "admitted", r)
        self.assertIn(("gate", 1), [(x["object"], x["version"]) for x in r["receipt"]["roots"]])
        self.assertEqual(r["receipt"]["outcome"]["writes"][0]["arguments"], [record(n=nat(2))])
        self.assertEqual(self.clause(self.bump(3)), "tooMuch")
        self.assertEqual(self.clause(self.turn("g", "poke")), "method")
        self.assertEqual(self.clause(self.bump(1, principal="mallory")), "principal")
        # The text is judged first.
        self.assertEqual(self.clause(self.bump(200)), "small")
        self.assertEqual(self.count(), "2")
        self.reopen()
        self.assertEqual(self.count(), "2")
        self.assertEqual(self.bump(1)["status"], "admitted")

    def test_an_exhausted_law_refuses_budget(self):
        self.make("s", SPIN, record(count=nat(0)))
        r = self.turn("s", "bump", record(n=nat(1)))
        self.assertEqual((r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["reason"]), ("budget", "law ticks"), r)

    def test_a_law_refusing_every_write_cannot_seal_out_reprogram_or_amend(self):
        version = self.host.send(op="world-view", principal="ember", object="g")["version"]
        amended = self.host.send(op="world-amend", principal="ember", identity="a1", object="g", version=version,
                                 law='law owner: request.kind == 0 or request.subject == "ember"')
        self.assertEqual(amended["status"], "admitted", amended)
        r = self.host.send(op="world-reprogram", principal="ember", identity="r1", object="g", version=version + 1,
                           package=PLAIN)
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.bump(50)["status"], "admitted")
        self.assertEqual(self.count(), "50")
        inspected = self.host.send(op="world-inspect", principal="ember", object="g")
        self.assertNotIn("lawReads", {m["name"] for m in inspected["methods"]})


READ = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  owner: String
  count: Nat
record Edits:
  owner: Plans.Edit<String, {}>
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
law owner "only the owner may count": not (request.kind == 0) or request.subject == new.owner
law small: new.count <= 100
def initial() -> State:
  {owner: "", count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {owner: Plans.Edit::<String, {}>.keep({}), count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case _: 1n
""")

SAID = "refused owner: only the owner may count"


class Readings(Reflection):
    """A refusal by a law clause the package gave a reading says `refused NAME: reading` in the receipt and
    in its public projection; refuted if the reading is lost, shown for another clause, or outlives an
    amendment of its clause."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("r", READ, record())

    def refused(self, identity):
        r = self.turn("r", "bump", principal="kim", identity=identity)
        self.assertEqual((r["status"], r["receipt"]["outcome"]["clause"]), ("refused", "owner"), r)
        return r

    def test_the_receipt_and_the_public_projection_quote_the_reading(self):
        r = self.refused("k1")
        self.assertEqual(r["receipt"]["outcome"]["reason"], SAID)
        self.assertEqual(r["public"]["reason"], SAID)
        seen = self.host.send(op="world-receipt", principal="ember", identity="k1", of="kim")
        self.assertEqual((seen["status"], seen["reason"]), ("refused", SAID), seen)
        self.assertEqual(self.turn("r", "bump")["status"], "admitted")

    def test_a_clause_without_a_reading_says_only_its_name(self):
        self.host.send(op="world-amend", principal="ember", identity="a1", object="r", version=0,
                       law='law owner: request.subject == new.owner\nlaw small: new.count <= 100')
        r = self.refused("k2")
        self.assertNotIn("reason", r["receipt"]["outcome"])

    def test_an_amendment_may_carry_readings_and_a_refusal_quotes_the_new_one(self):
        text = 'law owner "only the keeper may count: ask ember": request.subject == new.owner\nlaw small "at most five": new.count <= 5'
        a = self.host.send(op="world-amend", principal="ember", identity="a2", object="r", version=0, law=text)
        self.assertEqual(a["status"], "admitted", a)
        self.assertEqual(self.host.send(op="world-inspect", principal="ember", object="r")["law"], text)
        r = self.refused("k5")
        self.assertEqual((r["receipt"]["outcome"]["reason"], r["public"]["reason"]),
                         ("refused owner: only the keeper may count: ask ember",) * 2, r)
        self.reopen()
        self.assertEqual(self.refused("k6")["receipt"]["outcome"]["reason"], "refused owner: only the keeper may count: ask ember")

    def test_a_malformed_reading_is_law_syntax(self):
        a = self.host.send(op="world-amend", principal="ember", identity="a3", object="r", version=0,
                           law='law owner "unterminated: request.subject == new.owner')
        self.assertEqual((a["status"], a["receipt"]["outcome"]["clause"]), ("refused", "law syntax"), a)

    def test_an_amendment_that_keeps_the_clause_keeps_its_reading_and_a_snapshot_keeps_it(self):
        a = self.host.send(op="world-amend", principal="ember", identity="a1", object="r", version=0,
                           law='law owner: (not (request.kind == 0)) or (request.subject == new.owner)\nlaw small: new.count <= 5')
        self.assertEqual(a["status"], "admitted", a)
        self.assertEqual(self.refused("k3")["receipt"]["outcome"]["reason"], SAID)
        self.assertIn("height", self.host.send(op="world-snapshot"))
        self.reopen()
        self.assertEqual(self.refused("k4")["receipt"]["outcome"]["reason"], SAID)


if __name__ == "__main__":
    unittest.main()
