"""Programmable from within: reprogram and amend, judged by the object's own law."""
import unittest

from tests.test_turn_world import ON_DISK, TurnWorld, closure, label, nat, record, fixture

with open(ON_DISK["Counter"]) as handle:
    COUNTER = handle.read()

assert "delta: 1n" in COUNTER and "state.count + 1n" in COUNTER
ADDS_TWO = COUNTER.replace("delta: 1n", "delta: 2n").replace("state.count + 1n", "state.count + 2n")
EMBER_ONLY = 'law counter: request.subject == "ember"'
BOTH = 'law counter: request.subject == "ember" or request.subject == "kimik3"'

TOTALS = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
  total: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
  total: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits, {}>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {count: 0n, total: 0n}
def migrate(old: {count: Nat}) -> State:
  {count: old.count, total: old.count}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), total: Plans.Edit::<Nat, Nat>.keep({})}})):
    case written(_): state.total
    case _: 0n
"""


def with_law(source, law):
    return source.replace("def initial", law + "\ndef initial", 1)


def pad(source, size):
    """The source, padded with comment lines to just under `size` bytes."""
    lines = []
    total = len(source.encode())
    line = "# " + "x" * 96 + "\n"
    while total + len(line) < size:
        lines.append(line)
        total += len(line)
    return source + "".join(lines)


class Reprogram(TurnWorld):
    def make(self, obj="c1", source=COUNTER, principal="ember", count=0):
        r = self.host.send(op="world-create", principal=principal, identity="mk-" + obj, object=obj,
                           modules=closure("Counter", override={"Counter": source}), entry="initial",
                           seed=record(count=nat(count)))
        return r

    def reprogram(self, source, who="ember", obj="c1", migration="", ident=None):
        version = self.host.send(op="world-view", principal="e", object=obj)["version"]
        self.m = getattr(self, "m", 0) + 1
        return self.host.send(op="world-reprogram", principal=who, identity=ident or f"rp{self.m}",
                              object=obj, version=version, package=source, migration=migration)

    def amend(self, law, who="ember", obj="c1"):
        version = self.host.send(op="world-view", principal="e", object=obj)["version"]
        self.m = getattr(self, "m", 0) + 1
        return self.host.send(op="world-amend", principal=who, identity=f"am{self.m}",
                              object=obj, version=version, law=law)

    def pin(self, obj="c1"):
        return self.host.send(op="world-view", principal="e", object=obj)["pin"]


class Code(Reprogram):
    def test_bumps_to_three_then_five_across_the_pin_change_and_the_receipt_names_both_pins(self):
        self.assertEqual(self.make()["status"], "created")
        before = self.pin()
        for _ in range(3):
            self.assertEqual(self.turn("c1", "bump")["status"], "admitted")
        self.assertEqual(self.count("c1"), (3, "3"))
        r = self.reprogram(ADDS_TWO)
        self.assertEqual(r["status"], "admitted", r)
        rec = r["receipt"]["outcome"]["reprograms"][0]
        after = self.pin()
        self.assertNotEqual(before, after)
        self.assertEqual((rec["oldPin"], rec["newPin"]), (before, after))
        self.assertEqual(self.count("c1"), (4, "3"))       # the reprogram is a write: one version
        self.assertEqual(self.turn("c1", "bump")["result"], nat(5))
        self.assertEqual(self.count("c1"), (5, "5"))

    def test_a_different_state_type_without_a_migration_is_refused_by_name_and_changes_nothing(self):
        self.make()
        pin = self.pin()
        r = self.reprogram(TOTALS)
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["clause"]), ("refused", "programRefused", "stateType"))
        self.assertEqual((self.pin(), self.count("c1")), (pin, (0, "0")))

    def test_a_migration_converts_the_state_once_and_the_new_method_sees_the_total(self):
        self.make()
        for _ in range(3):
            self.turn("c1", "bump")
        r = self.reprogram(TOTALS, migration="migrate")
        self.assertEqual(r["status"], "admitted", r)
        state = self.host.send(op="world-view", principal="e", object="c1")["state"]
        self.assertEqual({f["name"]: f["value"]["value"] for f in state["fields"]}, {"count": "3", "total": "3"})
        self.assertEqual(r["receipt"]["outcome"]["reprograms"][0]["result"], state)
        self.assertEqual(self.turn("c1", "bump")["result"], nat(3))   # state.total, from the migration
        self.assertEqual(self.turn("c1", "bump")["result"], nat(3))   # and it was not run again

    def test_a_migration_with_the_wrong_type_is_refused_by_name(self):
        self.make()
        bad = TOTALS.replace("def migrate(old: {count: Nat}) -> State:", "def migrate(old: {count: Bool}) -> State:").replace(
            "{count: old.count, total: old.count}", "{count: 0n, total: 0n}")
        r = self.reprogram(bad, migration="migrate")
        self.assertEqual(r["receipt"]["outcome"]["clause"], "migration")

    def test_a_package_that_does_not_compile_is_refused_by_name(self):
        self.make()
        r = self.reprogram("edition ObjectiveBend 1\nthis is not a package\n")
        self.assertEqual(r["receipt"]["outcome"]["clause"], "compile")

    def test_a_retried_reprogram_returns_the_same_receipt_and_does_not_apply_twice(self):
        self.make()
        first = self.reprogram(ADDS_TWO, ident="once")
        h = self.height()
        again = self.host.send(op="world-reprogram", principal="ember", identity="once", object="c1",
                               version=0, package=ADDS_TWO)
        self.assertEqual(again, first)
        self.assertEqual(self.height(), h)


class Law(Reprogram):
    def test_a_law_on_the_subject_refuses_a_strangers_reprogram_naming_the_clause(self):
        self.make(source=with_law(COUNTER, EMBER_ONLY))
        r = self.reprogram(ADDS_TWO, who="mallory")
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"], out["clause"]), ("refused", "lawRefused", "counter"))
        self.assertEqual(self.reprogram(ADDS_TWO, who="ember")["status"], "admitted")

    def test_ember_widens_the_subject_to_two_principals_and_the_second_can_then_reprogram(self):
        self.make(source=with_law(COUNTER, EMBER_ONLY))
        self.assertEqual(self.reprogram(ADDS_TWO, who="kimik3")["status"], "refused")
        a = self.amend(BOTH)
        self.assertEqual(a["status"], "admitted", a)
        note = a["receipt"]["outcome"]["amendments"][0]
        self.assertEqual((note["old"], note["new"]), (EMBER_ONLY, BOTH))
        self.assertEqual(self.reprogram(ADDS_TWO, who="kimik3")["status"], "admitted")
        self.assertEqual(self.amend(EMBER_ONLY, who="mallory")["receipt"]["outcome"]["clause"], "counter")

    def test_an_amendment_by_a_stranger_is_refused_and_the_law_is_unchanged(self):
        self.make(source=with_law(COUNTER, EMBER_ONLY))
        r = self.amend(BOTH, who="mallory")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["clause"]), ("refused", "counter"))
        self.assertEqual(self.reprogram(ADDS_TWO, who="kimik3")["status"], "refused")

    def test_an_amendment_that_would_lock_out_its_author_is_refused_as_having_no_amendment_clause(self):
        self.make(source=with_law(COUNTER, EMBER_ONLY))
        r = self.amend('law counter: request.subject == "nobody"')
        out = r["receipt"]["outcome"]
        self.assertEqual((out["class"], out["clause"]), ("lawRefused", "law has no amendment clause"))
        self.assertEqual(self.amend(BOTH)["status"], "admitted")

    def test_an_amendment_that_does_not_parse_is_refused_by_name(self):
        self.make(source=with_law(COUNTER, EMBER_ONLY))
        r = self.amend("law counter: new.count >= 1")
        self.assertEqual(r["receipt"]["outcome"]["clause"], "law syntax")

    def test_a_law_with_no_amendment_clause_is_refused_at_creation(self):
        r = self.make(source=with_law(COUNTER, 'law sealed: request.subject == "nobody"'))
        self.assertEqual(r["status"], "error")
        self.assertIn("law has no amendment clause", r["message"])

    def test_the_law_can_be_read_on_the_pin_of_the_new_package(self):
        self.make(source=with_law(COUNTER, EMBER_ONLY))
        new_pin = self.reprogram(ADDS_TWO, who="ember")["receipt"]["outcome"]["reprograms"][0]["newPin"]
        locked = BOTH.replace("or request.subject == \"kimik3\"", 'and request.pin == "%s"' % new_pin)
        self.assertEqual(self.amend(locked)["status"], "admitted")
        self.assertEqual(self.turn("c1", "bump")["status"], "admitted")   # runs under the pin the law names


class Restart(Reprogram):
    def test_restart_replays_code_state_and_law(self):
        self.make(source=with_law(COUNTER, EMBER_ONLY))
        self.turn("c1", "bump")
        self.amend(BOTH)
        rp = self.reprogram(ADDS_TWO, who="kimik3")
        self.assertEqual(rp["status"], "admitted")
        before = (self.pin(), self.count("c1"), self.host.send(op="world-status")["head"])
        self.reopen()
        self.assertEqual((self.pin(), self.count("c1"), self.host.send(op="world-status")["head"]), before)
        self.assertEqual(self.turn("c1", "bump", principal="kimik3")["result"], nat(3))   # adds 2 after the pin change
        self.assertEqual(self.reprogram(ADDS_TWO, who="mallory")["receipt"]["outcome"]["clause"], "counter")

    def test_a_tampered_new_source_in_the_journal_breaks_open_at_its_height(self):
        self.make()
        self.reprogram(ADDS_TWO)
        self.host.close()
        self.hosts.remove(self.host)
        with open(self.path) as f:
            text = f.read()
        with open(self.path, "w") as f:
            f.write(text.replace("delta: 2n", "delta: 9n", 1))
        h = self.spawn()
        r = h.send(op="world-open", path=self.path)
        self.assertEqual(r["status"], "error")
        self.assertIn("height 2", r["message"])


PLAN_FIXTURE = fixture("""def evolve(state: State, input: {package: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.reprogram({object: Plans.self(context), package: input.package, migration: ""})):
    case reprogrammed(_): 1n
    case refused(r): 0n
    case _: 2n
def widen(state: State, input: {law: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.amend({object: Plans.self(context), law: input.law})):
    case amended(_): 1n
    case _: 0n
""")


class PlansInTurn(Reprogram):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk", object="p",
                           modules=PLAN_FIXTURE, entry="initial", seed=record(count=nat(5)))
        self.assertEqual(r["status"], "created", r)

    def test_an_object_reprograms_itself_with_a_plan_and_runs_the_new_code_next_turn(self):
        fixture_source = PLAN_FIXTURE[-1]["source"]
        newer = fixture_source + "def extra(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:\n  addSelf(context, 40n)\n"
        r = self.turn("p", "evolve", record(package=label(newer)))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(len(r["receipt"]["outcome"]["reprograms"]), 1)
        self.assertEqual(self.turn("p", "extra")["status"], "admitted")
        self.assertEqual(self.count("p"), (2, "45"))

    def test_a_refused_plan_reprogram_is_answered_in_turn_and_the_turn_still_commits(self):
        r = self.turn("p", "evolve", record(package=label("edition ObjectiveBend 1\nnonsense\n")))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(0)))
        self.assertNotIn("reprograms", r["receipt"]["outcome"])

    def test_an_object_amends_its_own_law_with_a_plan(self):
        r = self.turn("p", "widen", record(law=label('law own: request.subject == "ember"')))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.turn("p", "widen", record(law=label("law x: new.count <= 100")), principal="mallory")["receipt"]["outcome"]["clause"], "own")


class Maximum(Reprogram):
    def test_a_sixty_four_kib_package_is_refused_by_name_and_a_thirty_one_kib_one_is_admitted(self):
        self.make()
        big = self.reprogram(pad(ADDS_TWO, 64 * 1024))
        self.assertEqual(big["receipt"]["outcome"]["clause"], "packageBytes")
        self.assertEqual(self.count("c1"), (0, "0"))
        source = pad(ADDS_TWO, 31 * 1024)
        self.assertGreater(len(source.encode()), 30 * 1024)
        ok = self.reprogram(source)
        self.assertEqual(ok["status"], "admitted", ok)
        self.reopen()
        self.assertEqual(self.turn("c1", "bump")["result"], nat(2))


if __name__ == "__main__":
    unittest.main()
