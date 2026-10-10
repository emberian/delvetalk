"""Program reflection: inspect, check, the sealed standard library, interpret as a suspension,
and the sending object as the delivered turn's caller.

Each case is named by the defect that would make it fail. The library is world/lib (or a copy
of it); packages import it by name and carry none of it.
"""
import os
import re
import shutil
import tempfile
import time
import unittest

from tests.host import HostCase
from tests.test_chain import field, nil, reference
from tests.test_turn_world import ROOT, label, nat, record

LIBRARY = os.path.join(ROOT, "world", "lib")

PACKAGE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case written(_): state.count + 1n
    case _: 0n
"""

BARE = """edition ObjectiveBend 1
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
"""

BROKEN = """edition ObjectiveBend 1
def initial() -> Nat:
  missing
"""

# One object that reflects (inspect, check) and one that interprets and sends.
PROBE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./Form.obend as Form
record Arg:
  n: Nat
record State:
  count: Nat
  seen: String
record Edits:
  count: Plans.Edit<Nat, Nat>
  seen: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Arg>
def initial() -> State:
  {count: 0n, seen: ""}
def keep() -> Edits:
  {count: Plans.Edit::<Nat, Nat>.keep({}), seen: Plans.Edit::<String, {}>.keep({})}
def bump(state: State, context: Abi.Context) -> Activity<Plan, Response, String>:
  note(context, 1n, "bumped")
def bump2(state: State, input: Arg, context: Abi.Context) -> Activity<Plan, Response, String>:
  note(context, input.n, "bumped")
def note(context: Abi.Context, n: Nat, text: String) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: n}), seen: Plans.Edit::<String, {}>.set({value: text})})})):
    case _: text
def inspectIt(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.inspect({object: {world: "", object: input.target}})):
    case inspected(i): note(context, 0n, i.source)
    case denied(_): note(context, 0n, "denied")
    case _: note(context, 0n, "other")
def checkIt(state: State, input: {package: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.check({package: input.package})):
    case checked(c): first(context, c.diagnostics)
    case _: note(context, 0n, "other")
def first(context: Abi.Context, found: Lists.List<String>) -> Activity<Plan, Response, String>:
  match found:
    case nil(_): note(context, 0n, "clean")
    case cons(c): note(context, 0n, c.head)
def ask(state: State, input: {utterance: String, policy: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.interpret({utterance: input.utterance, offers: offered(), policy: {world: "", object: input.policy}, model: ""})):
    case proposal(p): note(context, p.argument.n, p.method)
    case unclear(_): note(context, 0n, "unclear")
    case timedOut(_): note(context, 0n, "timedOut")
    case denied(_): note(context, 0n, "denied")
    case _: note(context, 0n, "other")
def offered() -> Lists.List<Form.Form>:
  Lists.List::<Form.Form>.cons({head: {card: "probe", action: "bump2", fields: Lists.List::<Form.Field>.nil()}, tail: Lists.List::<Form.Form>.nil()})
def fire(state: State, input: {target: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.send({object: {world: "", object: input.target}, method: "bump", argument: Data.of::<Arg>({n: 0n})})):
    case delivery(_): note(context, 0n, "sent")
    case _: note(context, 0n, "other")
"""

POLICY = """edition ObjectiveBend 1
record State:
  model: String
  system: String
  examples: String
def initial() -> State:
  {model: "", system: "", examples: ""}
"""


def source_seed(count=0):
    return record(count=nat(count))


def probe_seed():
    return record(count=nat(0), seen=label(""))


class Reflection(HostCase):
    def open_library(self, library=LIBRARY, who="ember", **extra):
        r = self.host.send(op="world-open", path=self.path, library=library, principal=who, **extra)
        self.assertEqual(r["status"], "opened", r)
        return r

    def make(self, name, source, seed, **extra):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           source=source, entry="initial", seed=seed, **extra)
        self.assertEqual(r["status"], "created", r)
        return r

    def turn(self, obj, method, argument=None, identity=None, principal="ember"):
        self.n = getattr(self, "n", 0) + 1
        return self.host.send(op="world-turn", principal=principal, object=obj, method=method,
                              argument=argument or record(), identity=identity or f"t{self.n}")

    def state(self, name):
        v = self.host.send(op="world-view", principal="ember", object=name)
        self.assertEqual(v["status"], "viewed", v)
        return v["state"]

    def seen(self, name):
        return field(self.state(name), "seen")["value"]

    def lines(self):
        with open(self.path) as handle:
            return handle.read().splitlines()


class Library(Reflection):
    def test_a_package_importing_plans_and_abi_by_name_runs_its_activity(self):
        self.open_library()
        self.make("c", PACKAGE, source_seed())
        r = self.turn("c", "bump")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)

    def test_the_journal_records_the_library_pin_and_the_object_names_it_not_its_bytes(self):
        opened = self.open_library()
        created = self.make("c", PACKAGE, source_seed())
        entries = [__import__("json").loads(line) for line in self.lines()]
        library = [e for e in entries if e["outcome"]["tag"] == "library"][0]
        self.assertEqual(library["outcome"]["pin"], opened["library"])
        self.assertEqual(library["outcome"]["previous"], "")
        compile_inputs = created["receipt"]["outcome"]["compile"]
        self.assertEqual(compile_inputs["library"], opened["library"])
        self.assertEqual([m["name"] for m in compile_inputs["modules"]], ["Main"])

    def test_a_replacement_package_may_add_an_import_the_original_lacked(self):
        self.open_library()
        self.make("c", BARE, source_seed())
        r = self.host.send(op="world-reprogram", principal="ember", identity="rp", object="c", version=0,
                           package=PACKAGE)
        self.assertEqual(r["status"], "admitted", r)
        bump = self.turn("c", "bump")
        self.assertEqual((bump["status"], bump["result"]), ("admitted", nat(1)), bump)

    def test_a_package_may_not_shadow_a_library_module_with_other_bytes(self):
        self.open_library()
        r = self.host.send(op="world-create", principal="ember", identity="x", object="c", entry="initial",
                           seed=source_seed(), modules=[{"name": "Plan", "source": "edition ObjectiveBend 1\n"},
                                                        {"name": "Main", "source": PACKAGE}])
        self.assertEqual(r["status"], "error")
        self.assertIn("shadows the library", r["message"])

    def test_an_import_the_library_lacks_is_refused_with_the_compilers_diagnostic(self):
        self.open_library()
        r = self.host.send(op="world-create", principal="ember", identity="x", object="c", entry="initial",
                           seed=source_seed(), source=PACKAGE.replace("./Abi.obend", "./Nope.obend"))
        self.assertEqual(r["status"], "error")

    def test_a_library_change_is_refused_for_a_stranger_and_admitted_for_the_opener(self):
        with tempfile.TemporaryDirectory() as scratch:
            lib = os.path.join(scratch, "lib")
            shutil.copytree(LIBRARY, lib)
            opened = self.open_library(lib)
            self.make("old", PACKAGE, source_seed())
            with open(os.path.join(lib, "Spell.obend"), "a") as handle:
                handle.write("# a comment that changes the pin\n")
            stranger = self.host.send(op="world-library", principal="mallory", identity="lib-1")
            self.assertEqual(stranger["status"], "refused", stranger)
            self.assertEqual((stranger["receipt"]["outcome"]["class"], stranger["receipt"]["outcome"]["clause"]),
                             ("lawRefused", "opener"))
            opener = self.host.send(op="world-library", principal="ember", identity="lib-2")
            self.assertEqual(opener["status"], "library", opener)
            changed = opener["receipt"]["outcome"]
            self.assertEqual(changed["previous"], opened["library"])
            self.assertNotEqual(changed["pin"], opened["library"])
            # An object made before keeps the library it was compiled under; a new one gets the new pin.
            self.assertEqual(self.turn("old", "bump")["status"], "admitted")
            fresh = self.make("new", PACKAGE, source_seed())
            self.assertEqual(fresh["receipt"]["outcome"]["compile"]["library"], changed["pin"])
            self.assertEqual(self.turn("new", "bump")["status"], "admitted")
            before = {n: self.host.send(op="world-view", principal="ember", object=n) for n in ("old", "new")}
            # Restart: the library is reloaded at the recorded pin.
            self.release()
            self.host = self.spawn()
            again = self.host.send(op="world-open", path=self.path, library=lib)
            self.assertEqual((again["status"], again["library"]), ("opened", changed["pin"]), again)
            for n, view in before.items():
                self.assertEqual(self.host.send(op="world-view", principal="ember", object=n), view)
            self.assertEqual(self.turn("old", "bump")["status"], "admitted")
            # Different bytes at the path are refused by name.
            self.release()
            self.host = self.spawn()
            shutil.copy(os.path.join(LIBRARY, "Spell.obend"), os.path.join(lib, "Spell.obend"))
            differ = self.host.send(op="world-open", path=self.path, library=lib)
            self.assertEqual(differ["status"], "error")
            self.assertIn("the bytes differ", differ["message"])

    def test_a_world_opened_without_a_library_path_replays_from_the_journal(self):
        self.open_library()
        self.make("c", PACKAGE, source_seed())
        self.turn("c", "bump")
        before = self.host.send(op="world-view", principal="ember", object="c")
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="c"), before)
        self.assertEqual(self.turn("c", "bump")["status"], "admitted")

    def test_a_library_that_imports_a_module_it_lacks_or_cycles_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as scratch:
            for name, imports in (("A", "B"), ("B", "A")):
                with open(os.path.join(scratch, name + ".obend"), "w") as handle:
                    handle.write(f"edition ObjectiveBend 1\nimport ./{imports}.obend as X\n")
            r = self.host.send(op="world-open", path=self.path, library=scratch, principal="ember")
            self.assertEqual(r["status"], "error")
            self.assertIn("cycle", r["message"])
            with open(os.path.join(scratch, "B.obend"), "w") as handle:
                handle.write("edition ObjectiveBend 1\nimport ./Missing.obend as X\n")
            r = self.host.send(op="world-open", path=self.path, library=scratch, principal="ember")
            self.assertIn("not in the library", r["message"])

    def test_opening_with_a_library_names_the_opening_principal(self):
        r = self.host.send(op="world-open", path=self.path, library=LIBRARY)
        self.assertEqual(r["status"], "error")
        self.assertIn("opening principal", r["message"])


class Inspect(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("secret", PACKAGE, source_seed(), read={"principals": ["ember"]})
        self.make("probe", PROBE, probe_seed())

    def test_the_creator_inspects_pin_law_and_entry_source_and_a_stranger_is_denied(self):
        mine = self.host.send(op="world-inspect", principal="ember", object="secret")
        self.assertEqual(mine["status"], "inspected", mine)
        self.assertEqual(mine["source"], PACKAGE)
        self.assertRegex(mine["pin"], r"^bafyrei[a-z2-7]{52}$")  # CIDv1, dag-cbor, sha2-256
        self.assertIn("owner", mine["law"])
        stranger = self.host.send(op="world-inspect", principal="kim", object="secret")
        self.assertEqual(stranger["status"], "denied")
        self.assertNotIn("source", stranger)
        self.assertEqual(self.host.send(op="world-inspect", principal="ember", object="ghost")["status"], "unknown")

    def test_the_inspect_plan_answers_under_the_turns_principal(self):
        mine = self.turn("probe", "inspectIt", record(target=label("secret")))
        self.assertEqual((mine["status"], mine["result"]), ("admitted", label(PACKAGE)), mine)
        kim = self.turn("probe", "inspectIt", record(target=label("secret")), principal="kim")
        self.assertEqual((kim["status"], kim["result"]), ("admitted", label("denied")))


class Check(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("probe", PROBE, probe_seed())

    def test_a_broken_package_gets_a_located_diagnostic_and_a_clean_one_none(self):
        broken = self.turn("probe", "checkIt", record(package=label(BROKEN)))
        self.assertEqual(broken["status"], "admitted", broken)
        self.assertRegex(broken["result"]["value"], r"^Checked:\d+: [a-z-]+: .+")
        self.assertNotRegex(broken["result"]["value"], r"^Checked:0:")
        clean = self.turn("probe", "checkIt", record(package=label(PACKAGE)))
        self.assertEqual(clean["result"], label("clean"))

    def test_a_check_installs_nothing_and_the_journal_keeps_only_the_count(self):
        height = self.host.send(op="world-status")["height"]
        objects = self.host.send(op="world-status")["objects"]
        r = self.turn("probe", "checkIt", record(package=label(BROKEN)))
        self.assertEqual(r["receipt"]["checks"], 1)
        self.assertEqual(self.host.send(op="world-status")["height"], height + 1)
        self.assertEqual(self.host.send(op="world-status")["objects"], objects)
        self.assertNotIn("def initial", self.lines()[-1])

    def test_a_module_without_initial_is_checked_whole_not_refused_for_its_entry(self):
        plain = "edition ObjectiveBend 1\ndef bump(count: Nat) -> Nat:\n  count + 1n\n"
        self.assertEqual(self.turn("probe", "checkIt", record(package=label(plain)))["result"], label("clean"))
        types = "edition ObjectiveBend 1\nrecord Pair:\n  left: Nat\n  right: Nat\n"
        self.assertEqual(self.turn("probe", "checkIt", record(package=label(types)))["result"], label("clean"))
        # A broken definition after the first is still found: the entry does not limit the check.
        later = plain + "def later() -> Nat:\n  missing\n"
        self.assertRegex(self.turn("probe", "checkIt", record(package=label(later)))["result"]["value"],
                         r"^Checked:\d+: .*missing")

    def test_a_package_that_declares_a_law_checks_clean(self):
        law = PACKAGE.replace("def initial", "law ceiling: new.count <= 5\ndef initial")
        self.assertEqual(self.turn("probe", "checkIt", record(package=label(law)))["result"], label("clean"))


def interpreter_world(test):
    test.open_library()
    test.make("policy", POLICY, record(model=label("claude-test"), system=label("Be literal."),
                                       examples=label("one example")))
    test.make("probe", PROBE, probe_seed())


LAWFUL = PACKAGE + "law small: new.count <= 5\n"


class LibraryCheck(Reflection):
    """world-check and `library: <pin>` compile against the world's sealed library without the caller
    sending it; refuted if a check journals, if the library is read from the request, or if a
    stateless process cannot resolve the pin."""

    def test_world_check_compiles_over_the_sealed_library_and_journals_nothing(self):
        opened = self.open_library()
        before = self.host.send(op="world-status")["height"]
        r = self.host.send(op="world-check", principal="", modules=[{"name": "Tally", "source": PACKAGE}], entry="bump")
        self.assertEqual((r["status"], r["library"]), ("checked", opened["library"]), r)
        self.assertIn("Plan", [m["name"] for m in r["artifact"]["modules"]])
        self.assertEqual(self.host.send(op="world-status")["height"], before)

    def test_world_check_names_the_module_and_line_of_a_refusal(self):
        self.open_library()
        r = self.host.send(op="world-check", principal="glm", source=BROKEN, entry="initial")
        self.assertEqual(r["status"], "refused", r)
        self.assertEqual((r["diagnostic"]["module"], r["diagnostic"]["span"]["line"]), ("Package", 3), r)
        self.assertIn("missing", r["diagnostic"]["message"])

    def test_world_check_accepts_a_package_with_laws_as_world_create_does(self):
        self.open_library()
        r = self.host.send(op="world-check", principal="glm", source=LAWFUL, entry="initial")
        self.assertEqual(r["status"], "checked", r)

    def test_stateless_check_and_compile_resolve_the_pin_from_the_open_world(self):
        opened = self.open_library()
        pin = opened["library"]
        checked = self.host.send(op="check-package", library=pin, modules=[{"name": "Tally", "source": PACKAGE}], entry="bump")
        self.assertEqual(checked["status"], "checked", checked)
        compiled = self.host.send(op="compile", library=pin, source=PACKAGE, entry="bump")
        self.assertEqual(compiled["status"], "compiled", compiled)
        unknown = self.host.send(op="compile", library="bafy-not-a-pin", source=PACKAGE, entry="bump")
        self.assertEqual(unknown["status"], "error", unknown)
        self.assertIn("unknown library pin", unknown["message"])

    def test_a_stateless_process_seals_the_library_once_and_names_it_by_pin(self):
        opened = self.open_library()
        repl = self.spawn()
        loaded = repl.send(op="library-load", path=LIBRARY)
        self.assertEqual((loaded["status"], loaded["pin"]), ("library", opened["library"]), loaded)
        r = repl.send(op="check-package", library=loaded["pin"], source=PACKAGE, entry="bump")
        self.assertEqual(r["status"], "checked", r)
        lawful = repl.send(op="check-package", library=loaded["pin"], source=LAWFUL, entry="initial")
        self.assertEqual(lawful["status"], "refused", lawful)


class Interpret(Reflection):
    def setUp(self):
        super().setUp()
        interpreter_world(self)

    def ask(self, policy="policy", identity=None, principal="ember"):
        return self.turn("probe", "ask", record(utterance=label("ring it three times"), policy=label(policy)),
                         identity=identity, principal=principal)

    def pending(self):
        r = self.host.send(op="world-interpretations")
        self.assertEqual(r["status"], "interpretations", r)
        return r["pending"]

    def settle(self, item, reply):
        return self.host.send(op="world-interpretation", id=item["id"], reply=reply)

    def replied(self, method="bump2", **argument):
        return {"status": "replied", "json": {"method": method, "argument": argument}, "model": "m"}

    def test_interpret_suspends_and_lists_the_request_with_the_policys_system_prompt(self):
        r = self.ask()
        self.assertEqual(r["status"], "suspended", r)
        [item] = self.pending()
        self.assertEqual(set(item), {"id", "object", "policy", "utterance", "offers"})
        self.assertEqual(item["object"], "probe")
        self.assertEqual(item["utterance"], "ring it three times")
        self.assertEqual(item["policy"], {"model": "claude-test", "system": "Be literal.", "examples": "one example"})
        self.assertEqual(item["offers"], [{"card": "probe", "action": "bump2", "fields": []}])
        self.assertEqual(self.seen("probe"), "")

    def test_a_reply_that_fits_resumes_proposal_and_the_turn_commits(self):
        self.ask()
        [item] = self.pending()
        settled = self.settle(item, self.replied(n=3))
        self.assertEqual(settled["status"], "interpreted", settled)
        self.assertEqual(settled["receipt"]["outcome"]["verdict"]["tag"], "proposal")
        [resumed] = settled["resumed"]
        self.assertEqual(resumed["status"], "admitted", resumed)
        self.assertEqual((self.seen("probe"), field(self.state("probe"), "count")), ("bump2", nat(3)))
        self.assertEqual(self.pending(), [])

    def test_a_reply_that_does_not_fit_resumes_unclear(self):
        for index, reply in enumerate((
                self.replied(n="three"),                    # the argument is not the method's input type
                self.replied(method="ghost", n=1),          # not a method of the object
                self.replied(method="ask", n=1),            # a method, but not an offered action
                {"status": "replied", "json": ["nonsense"]},
                {"status": "replied", "json": {"argument": {"n": 1}}})):
            self.ask(identity=f"ask-{index}")
            [item] = self.pending()
            settled = self.settle(item, reply)
            self.assertEqual(settled["receipt"]["outcome"]["verdict"]["tag"], "unclear", (reply, settled))
            self.assertEqual(self.seen("probe"), "unclear", reply)
            self.assertEqual(self.pending(), [])
        self.assertEqual(field(self.state("probe"), "count"), nat(0))

    def test_a_failed_reply_resumes_unclear_naming_the_reason(self):
        self.ask()
        [item] = self.pending()
        settled = self.settle(item, {"status": "failed", "reason": "rate", "detail": "429"})
        self.assertIn("rate", settled["receipt"]["outcome"]["verdict"]["needs"][0])
        self.assertEqual(self.seen("probe"), "unclear")

    def test_a_reply_nobody_is_waiting_for_is_refused_and_a_retry_returns_the_same_receipt(self):
        self.assertEqual(self.host.send(op="world-interpretation", id="nope", reply=self.replied(n=1))["status"], "error")
        self.ask()
        [item] = self.pending()
        first = self.settle(item, self.replied(n=2))
        again = self.settle(item, self.replied(n=2))
        self.assertEqual(again["receipt"], first["receipt"])
        other = self.settle(item, self.replied(n=9))
        self.assertEqual(other["class"], "duplicateIdentity")
        self.assertEqual(field(self.state("probe"), "count"), nat(2))

    def test_the_deadline_comes_from_the_clock_and_resumes_timedOut(self):
        self.ask()
        self.assertEqual(len(self.pending()), 1)
        self.host.send(op="world-advance", height=10)
        self.assertEqual(self.seen("probe"), "")
        r = self.host.send(op="world-advance", height=100)
        self.assertEqual(r["status"], "advanced", r)
        self.assertEqual(self.seen("probe"), "timedOut")
        self.assertEqual(self.pending(), [])

    def test_a_policy_the_principal_cannot_read_is_answered_denied(self):
        self.make("hidden", POLICY, record(model=label("m"), system=label("s"), examples=label("")),
                  read={"principals": ["kim"]})
        r = self.ask(policy="hidden")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.seen("probe"), "denied")
        self.assertEqual(self.pending(), [])

    def test_a_pending_interpretation_and_its_settlement_survive_restart(self):
        self.ask()
        self.reopen()
        [item] = self.pending()
        self.assertEqual(item["policy"]["system"], "Be literal.")
        self.settle(item, self.replied(n=4))
        self.assertEqual(field(self.state("probe"), "count"), nat(4))
        before = self.host.send(op="world-view", principal="ember", object="probe")
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="probe"), before)
        self.assertEqual(self.pending(), [])


class CallerAcrossSend(Reflection):
    def test_a_delivered_turn_sees_the_sending_object_as_its_caller(self):
        law = 'law only: request.kind == 0 implies request.caller == "garden"\n'
        self.open_library()
        self.make("garden", PROBE, probe_seed())
        self.make("bell", PROBE.replace("def initial", law + "def initial", 1), probe_seed())
        direct = self.turn("bell", "bump")
        self.assertEqual((direct["status"], direct["receipt"]["outcome"]["clause"]), ("refused", "only"))
        sent = self.turn("garden", "fire", record(target=label("bell")))
        self.assertEqual(sent["status"], "admitted", sent)
        self.assertEqual(self.host.send(op="world-pending")["count"], 0)
        [receipt] = sent["delivered"]
        self.assertEqual(receipt["status"], "admitted", receipt)
        self.assertEqual(receipt["receipt"]["outcome"]["writes"][0]["callers"], ["garden"])
        self.assertEqual(field(self.state("bell"), "count"), nat(1))
        before = self.host.send(op="world-view", principal="ember", object="bell")
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="bell"), before)


FORGE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, Nat>
def initial() -> State:
  {note: ""}
def said(context: Abi.Context, text: String) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: text})}})):
    case _: text
def rework(state: State, input: {target: String, package: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.reprogram({object: {world: "", object: input.target}, package: input.package, migration: ""})):
    case reprogrammed(r): said(context, r.pin)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def relaw(state: State, input: {target: String, law: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.amend({object: {world: "", object: input.target}, law: input.law})):
    case amended(_): said(context, "amended")
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
"""

REWORKED = PACKAGE.replace("case _: 0n", "case _: 7n")


class ReprogramAnother(Reflection):
    """A reprogram or amend of another object is a change the target's own law judges, with
    request.caller = the proposing object and kind 1 or 2 (a write stays self-only)."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("forge", FORGE, record(note=label("")))

    def rework(self, target, principal="ember", obj="forge"):
        return self.turn(obj, "rework", record(target=label(target), package=label(REWORKED)), principal=principal)

    def test_the_creator_reprograms_a_target_through_a_forge_and_the_journal_names_the_forge(self):
        before = self.make("c", PACKAGE, source_seed())["receipt"]["outcome"]["pin"]
        r = self.rework("c")
        self.assertEqual(r["status"], "admitted", r)
        writes = {w["object"]: w for w in r["receipt"]["outcome"]["writes"]}
        self.assertEqual((writes["c"]["callers"], writes["c"]["kinds"]), (["forge"], [1]))
        after = self.host.send(op="world-view", principal="ember", object="c")["pin"]
        self.assertNotEqual(after, before)
        self.assertEqual(after, r["result"]["value"])
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="c")["pin"], after)

    def test_the_default_law_refuses_a_stranger_reprogramming_through_a_forge(self):
        before = self.make("c", PACKAGE, source_seed())["receipt"]["outcome"]["pin"]
        r = self.rework("c", principal="kim")
        # The target's law is asked in the turn: the forge hears `refused {owner}`, never `reprogrammed`,
        # and its own turn commits what it says about that.
        self.assertEqual((r["status"], r["result"]), ("admitted", label("owner")), r)
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="c")["pin"], before)
        self.assertNotIn("c", [w["object"] for w in r["receipt"]["outcome"]["writes"]])

    def test_a_law_naming_the_forge_admits_anyone_through_it_and_no_other_object(self):
        law = 'law forge: request.kind == 0 or request.caller == "forge" or request.subject == "ember"\n'
        self.make("c", PACKAGE.replace("def initial", law + "def initial", 1), source_seed())
        self.make("other", FORGE, record(note=label("")))
        self.assertEqual(self.rework("c", principal="kim")["status"], "admitted")
        refused = self.rework("c", principal="kim", obj="other")
        self.assertEqual((refused["status"], refused["result"]), ("admitted", label("forge")), refused)

    def test_an_amend_of_another_object_is_judged_by_its_law(self):
        self.make("c", PACKAGE, source_seed())
        text = 'law owner: request.kind == 0 or request.subject == "ember"\nlaw small: new.count <= 3'
        r = self.turn("forge", "relaw", record(target=label("c"), law=label(text)))
        self.assertEqual((r["status"], r["result"]), ("admitted", label("amended")), r)
        self.assertIn("small", self.host.send(op="world-inspect", principal="ember", object="c")["law"])
        kim = self.turn("forge", "relaw", record(target=label("c"), law=label(text)), principal="kim")
        self.assertEqual((kim["status"], kim["result"]), ("admitted", label("owner")), kim)

    def test_an_amendment_that_would_seal_out_its_proposer_is_answered_in_the_turn(self):
        self.make("c", PACKAGE, source_seed())
        sealed = 'law owner: request.kind == 0 or request.subject == "nobody"'
        r = self.turn("forge", "relaw", record(target=label("c"), law=label(sealed)))
        self.assertEqual(r["status"], "admitted", r)
        self.assertIn("law does not admit an amendment by its proposer ember", r["result"]["value"])
        self.assertNotIn("nobody", self.host.send(op="world-inspect", principal="ember", object="c")["law"])


class Maximum(Reflection):
    def test_a_128_module_library_seals_under_two_seconds_and_its_modules_import(self):
        with tempfile.TemporaryDirectory() as scratch:
            for i in range(128):
                with open(os.path.join(scratch, f"M{i:03}.obend"), "w") as handle:
                    imports = f"import ./M{i - 1:03}.obend as P\n" if i else ""
                    handle.write(f"edition ObjectiveBend 1\n{imports}def one{i}() -> Nat:\n  1n\n")
            started = time.time()
            r = self.host.send(op="world-open", path=self.path, library=scratch, principal="ember")
            elapsed = time.time() - started
            self.assertEqual(r["status"], "opened", r)
            self.assertLess(elapsed, 2.0)
            print(f"\n  128-module library sealed and journaled in {elapsed:.2f}s")
            reopened = time.time()
            self.reopen()
            self.assertLess(time.time() - reopened, 2.0)

    def test_a_library_of_too_many_modules_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as scratch:
            for i in range(257):
                with open(os.path.join(scratch, f"M{i:03}.obend"), "w") as handle:
                    handle.write("edition ObjectiveBend 1\n")
            r = self.host.send(op="world-open", path=self.path, library=scratch, principal="ember")
            self.assertEqual(r["status"], "error")
            self.assertIn("more than 256", r["message"])


if __name__ == "__main__":
    unittest.main()
