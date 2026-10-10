"""A supervisor named at creation is told when a supervised activity breaks, runs out of budget or
times out, and of nothing else.

Evidence for FOUNDATION §8 supervisors (layer: host).

Supervisors: an object names a supervisor at creation, and an
activity of it that ends `broken`, out of `budget`, or after its await `timedOut` is delivered to
the supervisor as `ended {receipt, how}` under the causal ledger.

    python3 -W error -m unittest tests.test_supervisors -v
"""
import json
import unittest

from tests.test_chain import field
from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record, declared

SUPERVISOR = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
  how: String
  class: String
  who: String
def initial() -> State:
  {count: 0n, how: "", class: "", who: ""}
def classOf(outcome: Plans.Outcome) -> String:
  match outcome:
    case admitted(_): "admitted"
    case refused(r): r.class
def ended(state: State, input: {receipt: Plans.Receipt, how: String}, context: Abi.Context) -> Activity<Nat>:
  match world.write({count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), how: Plans.Edit::<String, {}>.set({value: input.how}), class: Plans.Edit::<String, {}>.set({value: classOf(input.receipt.outcome)}), who: Plans.Edit::<String, {}>.set({value: context.caller})}):
    case _: 0n
""")

WORKER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def bump(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write({count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}):
    case _: 1n
def deep(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Nat>({object: Plans.self(context), method: "deep", argument: Plans.nothing()}):
    case _: 0n
def count(n: Nat) -> Nat:
  count(n + 1n)
def spin(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write({count: Plans.Edit::<Nat, Nat>.add({delta: count(0n)})}):
    case _: 0n
def wait(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.await({slot: {principal: "nobody", intent: "never"}, patience: 2n}):
    case timedOut(_): 7n
    case _: 0n
def spawn(state: State, input: {id: String, supervisor: String}, context: Abi.Context) -> Activity<Nat>:
  match world.createUnder({package: "Main", seed: Data.of::<{count: Nat}>({count: 5n}), law: "", requireAbsent: {world: "", object: input.id}, supervisor: {world: "", object: input.supervisor}}):
    case created(_): 1n
    case refused(_): 0n
    case _: 2n
""")


class Supervisors(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("boss", SUPERVISOR, record(count=nat(0), how=label(""), **{"class": label("")}, who=label("")))
        self.make("w", WORKER, record(count=nat(0)), supervisor="boss")
        self.make("free", WORKER, record(count=nat(0)))

    def boss(self):
        s = self.state("boss")
        return tuple(field(s, k)["value"] for k in ("count", "how", "class", "who"))

    def test_a_broken_activity_is_told_to_the_supervisor_under_the_ledger(self):
        r = self.turn("w", "deep")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "evaluation"), r)
        ended = r["receipt"]["ended"]
        self.assertEqual((ended["to"], ended["sender"], ended["method"]), ("boss", "w", "ended"))
        self.assertEqual(int(ended["ledger"]["depth"]), int(r["receipt"]["ledger"]["depth"]) - 1)
        [told] = r["delivered"]
        self.assertEqual(told["status"], "admitted", told)
        self.assertEqual(self.boss(), ("1", "broken", "evaluation", "w"))
        self.reopen()
        self.assertEqual(self.boss(), ("1", "broken", "evaluation", "w"))
        self.assertEqual(self.host.send(op="world-pending")["count"], 0)

    def test_an_activity_out_of_budget_is_told(self):
        r = self.host.send(op="world-turn", principal="ember", object="w", method="spin", argument=record(),
                           identity="s1", limits={"ticks": "2000"})
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "budget"), r)
        self.assertEqual(self.boss(), ("1", "budget", "budget", "w"))

    def test_an_activity_whose_await_timed_out_is_told_when_it_ends(self):
        r = self.turn("w", "wait")
        self.assertEqual(r["status"], "suspended", r)
        self.assertEqual(self.boss()[0], "0")
        advanced = self.host.send(op="world-advance", height=5)
        [resumed] = advanced["resumed"]
        self.assertEqual((resumed["status"], resumed["receipt"]["result"]), ("admitted", nat(7)), resumed)
        self.assertEqual(self.boss(), ("1", "timedOut", "admitted", "w"))

    def test_an_admitted_turn_and_an_unsupervised_object_tell_nobody(self):
        self.assertEqual(self.turn("w", "bump")["status"], "admitted")
        r = self.turn("free", "deep")
        self.assertEqual(r["status"], "refused")
        self.assertNotIn("ended", r["receipt"])
        self.assertEqual(self.boss()[0], "0")

    def test_a_child_created_under_a_supervisor_reports_to_it(self):
        r = self.turn("free", "spawn", record(id=label("kid"), supervisor=label("boss")))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(r["receipt"]["outcome"]["creates"][0]["supervisor"], "boss")
        self.assertEqual(self.host.send(op="world-inspect", principal="ember", object="kid")["supervisor"], "boss")
        self.turn("kid", "deep")
        self.assertEqual(self.boss(), ("1", "broken", "evaluation", "kid"))
        none = self.turn("free", "spawn", record(id=label("kid2"), supervisor=label("ghost")))
        self.assertEqual(none["result"], nat(0), none)
        self.assertIn("height", self.host.send(op="world-snapshot"))
        self.reopen()
        self.turn("kid", "deep")
        self.assertEqual(self.boss(), ("2", "broken", "evaluation", "kid"))

    def test_a_supervisor_that_is_not_an_object_is_a_request_error(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-x", object="x", source=WORKER,
                           entry="initial", seed=record(count=nat(0)), supervisor="ghost")
        self.assertEqual(r["status"], "error", r)


if __name__ == "__main__":
    unittest.main()
