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
import ./World.obend as World
record State:
  count: Nat
law small: new.count <= 100
def initial() -> State:
  {count: 0n}
def add(context: Abi.Context, n: Nat) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: n})})):
    case _: n
def bump(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<Nat>:
  add(context, input.n)
def poke(state: State, context: Abi.Context) -> Activity<Nat>:
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
import ./World.obend as World
record State:
  open: Nat
def initial() -> State:
  {open: 0n}
def open(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {open: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case _: 1n
""")

SPIN = GUARD.replace("""def law(old: State, new: State, request: Abi.Request) -> Abi.Verdict:
  if request.method""", """def spin(n: Nat) -> Bool:
  spin(n + 1n)
def law(old: State, new: State, request: Abi.Request) -> Abi.Verdict:
  if spin(0n) then Abi.Verdict.admitted({}) else if request.method""")

PLAIN = declared(GUARD[:GUARD.index("def opened")], "bump", "poke")


READING = PLAIN.replace("law small: new.count <= 100\n", "law small: new.count <= 100\nsum Verdict:\n  admitted: {}\n  refused: {clause: String, reading: String}\n") + """def law(old: State, new: State, request: Abi.Request) -> Verdict:
  if new.count > old.count + 2n then Verdict.refused({clause: "tooMuch", reading: "at most two at a time"}) else Verdict.refused({clause: "quiet", reading: ""})
"""


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

    def test_a_bend_law_is_given_no_object_its_subject_may_not_view(self):
        # codex host 3: a law reading a private object would let its verdict disclose that state.
        self.make("vault", GATE, record(open=nat(0)), read={"principals": ["ember"]})
        self.make("v", GUARD.replace('"gate"', '"vault"'), record(count=nat(0)))
        self.assertEqual(self.turn("vault", "open")["status"], "admitted")
        r = self.turn("v", "bump", record(n=nat(1)), principal="bob")
        self.assertEqual((r["status"], self.clause(r)), ("refused", "lawReads"), r)
        self.assertEqual(self.turn("v", "bump", record(n=nat(1)))["status"], "admitted")

    def test_a_law_reading_too_many_objects_is_refused_capacity_and_the_journal_replays(self):
        # codex host 4: 64 law reads beside the object's own root made an admitted entry of 65 roots,
        # which replay's root bound refuses: the journal would not reopen.
        names = [f"o{i}" for i in range(64)]
        for n in names:
            self.make(n, GATE, record(open=nat(0)))
        listed = "Lists.List::<String>.nil({})"
        for n in reversed(names):
            listed = 'Lists.List::<String>.cons({head: "%s", tail: %s})' % (n, listed)
        wide = GUARD.replace('Lists.List::<String>.cons({head: "gate", tail: Lists.List::<String>.nil({})})', listed).replace(
            "if opened(request.reads) then", "if true then")
        self.assertNotEqual(wide, GUARD)
        self.make("wide", wide, record(count=nat(0)))
        r = self.turn("wide", "bump", record(n=nat(1)))
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "capacity"), r)
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="wide")["version"], 0)

    def test_a_bend_laws_reading_is_the_refusals_reason(self):
        # WORLD-REVIEW finding 8: `refused {clause, reading}` reaches the receipt and the public projection.
        self.make("r", READING, record(count=nat(0)))
        r = self.turn("r", "bump", record(n=nat(3)), principal="mallory")
        outcome = r["receipt"]["outcome"]
        self.assertEqual((outcome["clause"], outcome["reason"]), ("tooMuch", "refused tooMuch: at most two at a time"), r)
        public = self.host.send(op="world-receipt", principal="ember", identity=r["receipt"]["identity"]["intent"], of="mallory")
        self.assertIn("at most two at a time", str(public), public)
        quiet = self.turn("r", "bump", record(n=nat(1)))["receipt"]["outcome"]
        self.assertEqual((quiet["clause"], quiet.get("reason")), ("quiet", None), quiet)

    def test_an_exhausted_law_refuses_budget(self):
        self.make("s", SPIN, record(count=nat(0)))
        r = self.turn("s", "bump", record(n=nat(1)))
        self.assertEqual((r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["reason"]), ("budget", "the turn ran out of law ticks; make it smaller, or send it again later."), r)

    def test_an_exhausted_law_reads_is_transient_budget(self):
        # codex host 14: a lawReads() out of ticks bound the identity as a permanent lawRefused.
        spinning = GUARD.replace("""def lawReads() -> Lists.List<String>:
  Lists.List::<String>.cons""", """def spun(n: Nat) -> Bool:
  spun(n + 1n)
def lawReads() -> Lists.List<String>:
  if spun(0n) then Lists.List::<String>.nil({}) else Lists.List::<String>.cons""")
        self.assertNotEqual(spinning, GUARD)
        self.make("sr", spinning, record(count=nat(0)))
        r = self.turn("sr", "bump", record(n=nat(1)))
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "budget"), r)

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
import ./World.obend as World
record State:
  owner: String
  count: Nat
law owner "only the owner may count": not (request.kind == 0) or request.subject == new.owner
law small: new.count <= 100
def initial() -> State:
  {owner: "", count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {owner: Plans.Edit::<String, {}>.keep({}), count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
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

    def test_inspect_answers_each_clause_with_its_reading(self):
        # docs/VOICE.md: the library's `law {card}` page reads world-inspect's clauses and readings, the
        # package's law as well as an amended one.
        laws = self.host.send(op="world-inspect", principal="kim", object="r", source=False)["laws"]
        self.assertEqual([(l["name"], l.get("reading")) for l in laws], [("owner", "only the owner may count"), ("small", None)])
        self.assertTrue(all(l["clause"] for l in laws), laws)
        self.host.send(op="world-amend", principal="ember", identity="a9", object="r", version=0,
                       law='law owner "ask ember": request.subject == new.owner\nlaw small: new.count <= 5')
        laws = self.host.send(op="world-inspect", principal="kim", object="r", source=False)["laws"]
        self.assertEqual([(l["name"], l.get("reading"), l["clause"]) for l in laws],
                         [("owner", "ask ember", "request.subject == new.owner"), ("small", None, "new.count <= 5")])

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


class LawAtCreation(Reflection):
    """`world-create {law}` sets the object's law text at creation, in `world-amend`'s grammar with its
    readings; a malformed law is refused by name and creates nothing; replay agrees."""

    def setUp(self):
        super().setUp()
        self.open_library()

    def test_a_created_law_holds_from_the_start_and_replays(self):
        law = 'law cap "the count stays under three": new.count <= 2\nlaw owner: request.kind == 0 or request.subject == "ember"'
        r = self.host.send(op="world-create", principal="ember", identity="mk", object="g", source=PLAIN, entry="initial",
                           seed=record(), law=law)
        self.assertEqual((r["status"], r["receipt"]["outcome"]["law"]), ("created", law), r)
        for i in range(2):
            self.assertEqual(self.turn("g", "poke", identity=f"b{i}")["status"], "admitted")
        refused = self.turn("g", "poke", identity="b2")["receipt"]["outcome"]
        self.assertEqual((refused["clause"], refused["reason"]), ("cap", "refused cap: the count stays under three"), refused)
        self.reopen()
        self.assertIn("new.count <= 2", self.host.send(op="world-inspect", principal="ember", object="g", source=False)["law"])
        bad = self.host.send(op="world-create", principal="ember", identity="mk2", object="h", source=PLAIN, entry="initial",
                             seed=record(), law="law broken: new.count <<< 2")
        self.assertEqual(bad["status"], "error", bad)
        self.assertTrue(bad["message"].startswith("law syntax: "), bad)
        self.assertNotEqual(self.host.send(op="world-view", principal="ember", object="h").get("status"), "viewed")


PROPOSED = PLAIN.replace("law small: new.count <= 100\n", "law small: new.count <= 100\nlaw owner: request.kind == 0 or request.subject == \"ember\"\n")


class Proposed(Reflection):
    """A state write no method of the object made (a `world-propose`, a reprogram's migration) is judged
    `request.kind == 3`, proposed: a law that admits `request.kind == 0` admits only the object's own
    method writes (codex objects 1-8; the root's decision)."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("p", PROPOSED, record(count=nat(0)))

    def propose(self, who, identity, n=7):
        version = self.host.send(op="world-view", principal="ember", object="p")["version"]
        edit = {"tag": "variant", "label": "set", "payload": record(value=nat(n))}
        return self.host.send(op="world-propose", principal=who, identity=identity, roots=[{"object": "p", "version": version}],
                              writes=[{"object": "p", "edits": [record(count=edit)]}])

    def test_a_strangers_proposal_is_not_the_objects_own_write(self):
        self.assertEqual(self.turn("p", "bump", record(n=nat(1)), principal="kim")["status"], "admitted")
        r = self.propose("kim", "k1")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out.get("clause")), ("refused", "lawRefused", "owner"), r)
        mine = self.propose("ember", "e1")
        self.assertEqual(mine["status"], "admitted", mine)
        self.assertEqual(mine["receipt"]["outcome"]["writes"][0]["kinds"], [3])
        self.assertEqual(field(self.state("p"), "count")["value"], "7")
        self.reopen()
        self.assertEqual(field(self.state("p"), "count")["value"], "7")
        kinds = self.host.send(op="world-inspect", principal="kim", object="p")["requestKinds"]
        self.assertEqual(kinds, {"write": 0, "reprogram": 1, "amend": 2, "proposed": 3})

    def test_a_law_naming_kind_three_judges_proposals_and_migrations(self):
        a = self.host.send(op="world-amend", principal="ember", identity="a1", object="p", version=0,
                           law='law owner: request.kind == 0 or request.subject == "ember"\nlaw proposals: request.kind == 3 implies new.count <= 5')
        self.assertEqual(a["status"], "admitted", a)
        self.assertEqual(self.propose("ember", "e2", n=9)["receipt"]["outcome"].get("clause"), "proposals")
        self.assertEqual(self.propose("ember", "e3", n=4)["status"], "admitted")
        self.assertEqual(self.turn("p", "bump", record(n=nat(2)))["status"], "admitted")
        version = self.host.send(op="world-view", principal="ember", object="p")["version"]
        moved = PROPOSED + "def migrate(old: State) -> State:\n  {count: 50n}\n"
        r = self.host.send(op="world-reprogram", principal="ember", identity="r1", object="p", version=version,
                           package=moved, migration="migrate")
        self.assertEqual((r["status"], r["receipt"]["outcome"].get("clause")), ("refused", "proposals"), r)
        r = self.host.send(op="world-reprogram", principal="ember", identity="r2", object="p", version=version,
                           package=PROPOSED + "def migrate(old: State) -> State:\n  {count: 5n}\n", migration="migrate")
        self.assertEqual(r["status"], "admitted", r)


if __name__ == "__main__":
    unittest.main()
