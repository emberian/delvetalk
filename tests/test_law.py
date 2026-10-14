"""The two-tier law: the Bend predicate judges after the law text admits, reads the roots it
declares, runs under its own budget, and can never seal out a reprogram or amendment.

Evidence for FOUNDATION §4 (layer: host).

The two-tier law: after the law text admits an ordinary write, the
package's Bend `law(old, new, request)` judges it under `Bounds.lawTicks`, reading the objects
`lawReads()` names as roots. Reprograms and amendments are the law text's alone.

    python3 -W error -m unittest tests.test_law -v
"""
import os
import unittest

from tests.test_reflection import Reflection
from tests.wire import field, label, nat, record
from tests.bend import closure, declared

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


    def test_an_exhausted_law_or_law_reads_refuses_transient_budget(self):
        # codex host 14: a lawReads() out of ticks bound the identity as a permanent lawRefused.
        self.make("s", SPIN, record(count=nat(0)))
        r = self.turn("s", "bump", record(n=nat(1)))
        self.assertEqual((r["receipt"]["outcome"]["class"], r["receipt"]["outcome"]["reason"]), ("budget", "the turn ran out of law ticks judging s's law; the same spell runs out the same way: make that part do less, or split it across turns."), r)
        spinning = GUARD.replace("def lawReads() -> Lists.List<String>:\n  Lists.List::<String>.cons",
                                 "def spun(n: Nat) -> Bool:\n  spun(n + 1n)\ndef lawReads() -> Lists.List<String>:\n"
                                 "  if spun(0n) then Lists.List::<String>.nil({}) else Lists.List::<String>.cons")
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


    def test_an_amendment_may_carry_readings_and_a_refusal_quotes_the_new_one(self):
        a = self.host.send(op="world-amend", principal="ember", identity="a3", object="r", version=0,
                           law='law owner "unterminated: request.subject == new.owner')
        self.assertEqual((a["status"], a["receipt"]["outcome"]["clause"]), ("refused", "law syntax"), a)
        text = 'law owner "only the keeper may count: ask ember": request.subject == new.owner\nlaw small "at most five": new.count <= 5'
        a = self.host.send(op="world-amend", principal="ember", identity="a2", object="r", version=0, law=text)
        self.assertEqual(a["status"], "admitted", a)
        self.assertEqual(self.host.send(op="world-inspect", principal="ember", object="r")["law"], text)
        r = self.refused("k5")
        self.assertEqual((r["receipt"]["outcome"]["reason"], r["public"]["reason"]),
                         ("refused owner: only the keeper may count: ask ember",) * 2, r)
        self.assertEqual((r["receipt"]["outcome"]["reading"], r["public"]["reading"]), ("only the keeper may count: ask ember",) * 2, r)
        self.reopen()
        self.assertEqual(self.refused("k6")["receipt"]["outcome"]["reason"], "refused owner: only the keeper may count: ask ember")

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
        refused = self.turn("g", "poke", identity="b2")
        out = refused["receipt"]["outcome"]
        self.assertEqual((out["clause"], out["reading"], out["reason"]), ("cap", "the count stays under three", "refused cap: the count stays under three"), out)
        self.assertEqual((refused["public"]["reading"], refused["public"]["reason"]), (out["reading"], out["reason"]), refused)
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
        self.assertEqual(kinds, {"write": 0, "reprogram": 1, "amend": 2, "proposed": 3, "rule": 4})

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


class CreatedReadings(Reflection):
    """Rehearsal run 12: a law given to a turn's `create` was journaled without its readings, so a full
    replay lost them (refusals and `inspect` bare) and a snapshot written live disagreed with replay."""
    LAW = 'law cap "at most two": request.method == "bump2" implies new.count <= 2'

    def refused(self):
        r = self.turn("made", "bump2", record(n=nat(3)))
        self.assertEqual(r["status"], "refused", r)
        laws = self.host.send(op="world-inspect", principal="ember", object="made")["laws"]
        return r["receipt"]["outcome"]["reason"], [(x["name"], x["reading"]) for x in laws]

    def test_a_creators_readings_survive_a_reopen_and_the_snapshot_is_replays(self):
        from tests.test_reflection import PROBE
        maker = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
def initial() -> State:
  {n: 0n}
def make(state: State, context: Abi.Context) -> Activity<String>:
  match world.create({package: "Probe", seed: Data.of::<{count: Nat}>({count: 0n}), law: "%s", requireAbsent: {world: "", object: "made"}}):
    case created(_): "made"
    case refused(r): r.reading
""" % self.LAW.replace('"', '\\"'), "make")
        mods = closure(*("Abi", "List", "Form", "Plan", "World"))
        r = self.host.send(op="world-create", principal="ember", identity="mk-maker", object="maker",
                           modules=mods + [{"name": "Probe", "source": PROBE}, {"name": "Maker", "source": maker}],
                           entry="initial", seed=record(n=nat(0)))
        self.assertEqual(r["status"], "created", r)
        made = self.turn("maker", "make")
        self.assertEqual((made["status"], made["result"]), ("admitted", {"tag": "label", "value": "made"}), made)
        live = self.refused()
        self.assertIn("at most two", live[0])
        self.assertEqual(live[1], [("cap", "at most two")])
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        verified = self.host.send(op="world-open", path=self.path, verify=True)
        self.assertEqual(verified["status"], "opened", verified)
        self.assertEqual(self.refused(), live)
        # Replay from the first entry: no snapshot to stand on.
        self.release()
        for name in os.listdir(os.path.dirname(self.path)):
            if ".snapshot." in name:
                os.remove(os.path.join(os.path.dirname(self.path), name))
        self.host = self.spawn()
        self.assertEqual(self.host.send(op="world-open", path=self.path)["status"], "opened")
        self.assertEqual(self.refused(), live)


class Alive(Reflection):
    """LAW §4 A, E, H with METAPHYSICS's `alive` clause over a real object: a thing answers while tended
    within 1440 minutes of the world clock; `tend` is always admitted and writes the clock it read."""
    LAW = 'law alive "answers while tended within 1440 entries": request.method == "tend" or request.clock <= old.tended + 1440\n'
    THING = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  tended: Nat
  rains: Nat
def initial() -> State:
  {tended: 0n, rains: 0n}
def rain(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {rains: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case _: state.rains + 1n
def tend(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {tended: Plans.Edit::<Nat, Nat>.set({value: context.clock})})):
    case _: context.clock
""", "rain", "tend")

    def test_alive_admits_within_the_window_and_a_tend_always_and_refuses_past_it(self):
        self.open_library()
        self.make("fern", self.THING + self.LAW, record(tended=nat(0), rains=nat(0)))
        self.assertEqual(self.turn("fern", "rain")["status"], "admitted")
        self.assertEqual(self.host.send(op="world-advance", principal="transport", height=1440)["status"], "advanced")
        self.assertEqual(self.turn("fern", "rain")["status"], "admitted")                 # at the edge: 1440 <= 0 + 1440
        self.host.send(op="world-advance", principal="transport", height=1500)
        late = self.turn("fern", "rain")
        out = late["receipt"]["outcome"]
        self.assertEqual((late["status"], out["clause"]), ("refused", "alive"), late)
        self.assertIn("answers while tended within 1440 entries", out["reason"])
        tend = self.turn("fern", "tend")
        self.assertEqual((tend["status"], tend["result"]), ("admitted", nat(1500)), tend)
        self.assertEqual(self.turn("fern", "rain")["status"], "admitted")
        self.reopen()
        self.assertEqual(field(self.state("fern"), "rains"), nat(3))


KIND_LAW = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  law: String
def initial() -> State:
  {law: ""}
def setLaw(state: State, input: {law: String}, context: Abi.Context) -> Activity<String>:
  match world.write(extend(keep(), {law: Plans.Edit::<String, {}>.set({value: input.law})})):
    case _: input.law
""", "setLaw")


class Atoms(Reflection):
    """LAW §4 B, C, D, F over real objects (KERNEL-HANDOFF §11): `under "O"` judges a write by the
    `law` text O holds now, read as a root and only by a subject who may view O; a missing citation is
    refused at creation; `changed(...) by`, a cited relation's membership and a filtered count judge rows."""
    OWNER = 'law owner: request.kind == 0 or request.subject == "ember"\n'

    def setUp(self):
        super().setUp()
        self.open_library()

    def create(self, name, source, law, seed=None, **extra):
        return self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name, source=source,
                              entry="initial", seed=seed or record(), law=law, **extra)

    def test_under_judges_by_the_cited_law_as_it_stands_and_reads_it_as_a_root(self):
        self.assertEqual(self.create("kind/x", KIND_LAW, self.OWNER, record(law=label('law small "two at most": new.count <= 2')))["status"], "created")
        made = self.create("g", PLAIN, 'law kind "as its kind says": under "kind/x"\n' + self.OWNER)
        self.assertEqual(made["status"], "created", made)
        self.assertEqual(self.host.send(op="world-inspect", principal="ember", object="g")["cites"], ["kind/x"])
        for i in range(2):
            ok = self.turn("g", "poke", identity=f"p{i}")
            self.assertEqual(ok["status"], "admitted", ok)
        self.assertIn({"object": "kind/x", "version": 0}, ok["receipt"]["roots"])
        refused = self.turn("g", "poke", identity="p2")
        # The refusal names the kind's clause that failed, with the kind's reading, not the wrapper `kind`.
        outcome = refused["receipt"]["outcome"]
        self.assertEqual((refused["status"], outcome["clause"], outcome["reason"]), ("refused", "small", "refused small: two at most"), refused)
        # The kind's law changes, and its instances are judged by the new one.
        self.assertEqual(self.turn("kind/x", "setLaw", record(law=label("law small: new.count <= 3")))["status"], "admitted")
        self.assertEqual(self.turn("g", "poke", identity="p3")["status"], "admitted")
        self.reopen()
        self.assertEqual(field(self.state("g"), "count"), nat(3))
        # A citation of nothing is refused at creation, by name.
        bad = self.create("h", PLAIN, 'law kind: under "kind/none"\n' + self.OWNER)
        self.assertEqual(bad["status"], "error", bad)
        self.assertIn("under: no object kind/none", bad["message"])

    def test_a_cited_object_its_subject_may_not_view_refuses_the_write(self):
        self.assertEqual(self.create("kind/p", KIND_LAW, self.OWNER, record(law=label("law small: new.count <= 9")),
                                     read={"principals": ["ember"]})["status"], "created")
        self.assertEqual(self.create("g", PLAIN, 'law kind: under "kind/p"\n' + self.OWNER)["status"], "created")
        self.assertEqual(self.turn("g", "poke", identity="mine")["status"], "admitted")
        theirs = self.turn("g", "poke", identity="theirs", principal="kim")
        self.assertEqual((theirs["status"], theirs["receipt"]["outcome"]["clause"]), ("refused", "lawReads"), theirs)

    def test_rows_changed_by_whom_a_cited_roster_and_a_quorum(self):
        from tests.test_relation import PACKAGE as RAINS, rain, relation
        rains = RAINS.replace("LIMIT", "0n")
        # Each clause leaves an amendment to the owner (the metarule judges the law at creation).
        law = ('law mine "a writer changes only their own rows": request.kind == 2 or changed(new.rains.author) by request.subject\n'
               'law listed: request.kind == 2 or request.subject in "roster".rains.author\n'
               'law quorum: count(new.rains) <= count(new.rains where author == "ember") + 2\n' + self.OWNER)
        self.assertEqual(self.create("roster", rains, self.OWNER, record(rains=relation(rain("ann", 1, "in"), rain("kim", 1, "in"))))["status"], "created")
        made = self.create("b", rains, law, record(rains=relation(rain("ember", 0, "seed"))))
        self.assertEqual(made["status"], "created", made)
        put = lambda who, author, at: self.turn("b", "insert", rain(author, at, "x"), principal=who)
        clause = lambda r: (r["status"], r["receipt"]["outcome"].get("clause"))
        self.assertEqual(clause(put("ann", "ann", 1)), ("admitted", None))
        self.assertEqual(clause(put("ann", "kim", 2)), ("refused", "mine"))
        self.assertEqual(clause(put("eve", "eve", 3)), ("refused", "listed"))
        self.assertEqual(clause(put("kim", "kim", 4)), ("admitted", None))
        self.assertEqual(clause(put("kim", "kim", 5)), ("refused", "quorum"))
        self.reopen()
        self.assertEqual(clause(put("ann", "ann", 6)), ("refused", "quorum"))

    def test_one_text_holds_laws_rules_and_wants_and_its_laws_judge(self):
        """OVERHAUL §2 (KERNEL-HANDOFF §11): a thing's text holds law, rule and want lines in one grammar, and
        so does its kind's; the laws judge every write (`%`, `request.verb`, the kind's through `under`), the
        rules and wants stand beside them for the host to fire and pose, and a want reading past the thing
        as it stands refuses the text by name."""
        kind = ('law small "two at most": new.count <= 2\n'
                'rule rang "rings at two": new.count >= 2 and old.count <= 1 then delvetalk {request.object} ring\n'
                'want poked "wants a poke": new.count <= 0 asks delvetalk {request.object} poke')
        self.assertEqual(self.create("kind/x", KIND_LAW, self.OWNER, record(law=label(kind)))["status"], "created")
        text = ('law kind: under "kind/x"\n'
                'law odd "an even count is a bump\'s": request.kind == amend or new.count % 2 == 1 or request.verb == "bump"\n'
                'rule echo: request.verb == "poke" then delvetalk me note / text: {request.object} poked to {new.count}\n'
                'want started: new.count <= 0 and not "kind/x" wants poked asks delvetalk {request.object} poke\n' + self.OWNER)
        made = self.create("g", PLAIN, text)
        self.assertEqual(made["status"], "created", made)
        clause = lambda r: (r["status"], r["receipt"]["outcome"].get("clause"))
        self.assertEqual(clause(self.turn("g", "poke", identity="p1")), ("admitted", None))
        self.assertEqual(clause(self.turn("g", "poke", identity="p2")), ("refused", "odd"))
        self.assertEqual(clause(self.turn("g", "bump", record(n=nat(1)), identity="b1")), ("admitted", None))
        self.assertEqual(clause(self.turn("g", "poke", identity="p3")), ("refused", "small"))
        self.reopen()
        self.assertEqual(field(self.state("g"), "count"), nat(2))
        bad = self.create("h", PLAIN, 'want w: old.count <= 0 asks delvetalk {request.object} poke\n' + self.OWNER)
        self.assertEqual(bad["status"], "error", bad)
        self.assertIn("`old.count` in a want", bad["message"])


SEALED = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
law once "written once": new.count <= 1
def initial() -> State:
  {count: 0n}
def write(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case _: told(state.count + 1n)
def told(n: Nat) -> Activity<Nat>:
  match world.offer({to: "", document: Document.text("#1 is written")}):
    case _: n
""")


class RefusedOffers(Reflection):
    """A refused turn offers nothing: its offers were the turn's, and the turn did not happen (the objects lane's
    `sealed/1 write`, refused, still told the resident "#1 is written")."""

    def test_a_refused_turn_carries_no_offer(self):
        self.open_library()
        self.make("sealed", SEALED, record(count=nat(0)))
        first = self.turn("sealed", "write")
        self.assertEqual((first["status"], [o["text"] for o in first.get("offers", [])]), ("admitted", ["#1 is written"]), first)
        again = self.turn("sealed", "write")
        self.assertEqual((again["status"], again["receipt"]["outcome"].get("clause")), ("refused", "once"), again)
        self.assertNotIn("offers", again)
        self.assertNotIn("offers", again["receipt"])
        offered = self.host.send(op="world-offers", principal="ember")["offers"]
        self.assertEqual([o["text"] for o in offered], ["#1 is written"], offered)

if __name__ == "__main__":
    unittest.main()


ADD = {"tag": "variant", "label": "add", "payload": record(delta=nat(1))}
OPENS = "law opens: request.kind == 0 or request.kind == 2"
# Asks the host whether setting `verdict` would admit (`world.judge`), waits for ann's `go`, then notes the answer.
ASKER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  verdict: String
  noted: String
def initial() -> State:
  {verdict: "", noted: ""}
def ask(state: State, context: Abi.Context) -> Activity<String>:
  match world.judge(extend(keep(), {verdict: Plans.Edit::<String, {}>.set({value: "yes"})})):
    case judged(j): later(if j.admitted then "admitted" else j.clause)
    case _: "other"
def later(said: String) -> Activity<String>:
  match world.await({slot: {principal: "ann", intent: "go"}, patience: 50n}):
    case reply(_):
      match world.write(extend(keep(), {noted: Plans.Edit::<String, {}>.set({value: said})})):
        case _: said
    case _: ""
""", "ask")


class Cited(Reflection):
    """A law reading another object reads it as the commit leaves it, and a want resting on another's want
    is judged by both: refuted if one turn's two writes each pass a joint bound against the other's state
    before the turn, or a law reading `"B" wants N` admits while B's want holds through C's."""

    def setUp(self):
        super().setUp()
        self.open_library()

    def open(self, name, principal="ember"):
        return self.turn(name, "open", principal=principal)

    def clause(self, r):
        return r["receipt"]["outcome"].get("clause", r["receipt"]["outcome"]["class"]) if r["status"] == "refused" else r["status"]

    def propose(self, identity, names):
        roots = [{"object": n, "version": self.host.send(op="world-view", principal="ember", object=n)["version"]} for n in names]
        return self.host.send(op="world-propose", principal="ember", identity=identity, roots=roots,
                              writes=[{"object": n, "edits": [record(open=ADD)]} for n in names])

    def test_one_commit_writing_two_objects_is_judged_as_the_world_it_makes(self):
        # codex 2026-10-12 host 11: each count judged against the other's zero, and both admitted.
        self.make("a", GATE, record(open=nat(0)), law='law pair: request.kind == 2 or new.open + "b".open <= 1')
        self.make("b", GATE, record(open=nat(0)), law='law pair: request.kind == 2 or new.open + "a".open <= 1')
        r = self.propose("both", ["a", "b"])
        self.assertEqual((r["status"], self.clause(r)), ("refused", "pair"), r)
        self.assertEqual(self.propose("one", ["a"])["status"], "admitted")
        # A bound the other write meets only once it lands admits the two together.
        self.make("c", GATE, record(open=nat(0)), law='law after: new.open == 0 or "d".open >= 1')
        self.make("d", GATE, record(open=nat(0)))
        self.assertEqual(self.clause(self.propose("alone", ["c"])), "after")
        self.assertEqual(self.propose("together", ["c", "d"])["status"], "admitted")
        self.reopen()
        self.assertEqual([field(self.state(n), "open")["value"] for n in "abcd"], ["1", "0", "1", "1"])

    def test_a_law_reading_a_want_that_rests_on_anothers_want_judges_both(self):
        # codex 2026-10-12 host 10: A's facts held B's want but not C's state and want, so B read unwanted.
        self.make("c", GATE, record(open=nat(0)), law=OPENS + "\nwant blocked: new.open >= 1 asks delvetalk c open")
        self.make("b", GATE, record(open=nat(0)), law=OPENS + '\nwant blocked: "c" wants blocked asks delvetalk b open')
        self.make("a", GATE, record(open=nat(0)), law='law free: request.kind == 2 or not "b" wants blocked')
        self.assertEqual(self.open("a")["status"], "admitted")
        self.assertEqual(self.open("c")["status"], "admitted")
        wants = self.host.send(op="world-wants", principal="ember", object="b")["rows"]
        self.assertEqual([w["name"] for w in wants], ["blocked"], wants)
        r = self.open("a")
        self.assertEqual((r["status"], self.clause(r)), ("refused", "free"), r)
        self.assertIn("c", [x["object"] for x in r["receipt"]["roots"]])

    def test_a_judgment_that_read_another_object_is_stale_when_it_moves(self):
        # codex 2026-10-12 host 12: world.judge read b through a's law but left no root, so the resumed turn noted
        # an approval b had since withdrawn.
        self.make("b", GATE, record(open=nat(0)))
        self.make("a", ASKER, record(), law='law gate: request.kind == 2 or new.verdict == old.verdict or "b".open == 0')
        self.assertEqual(self.turn("a", "ask")["status"], "suspended")
        self.assertEqual(self.open("b")["status"], "admitted")
        self.assertEqual(self.turn("b", "open", principal="ann", identity="go")["status"], "admitted")
        self.assertEqual(field(self.state("a"), "noted")["value"], "gate")
