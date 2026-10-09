"""Delegation as an object: a grant lets a named grantee run one method of one object as the
principal of the direct turn that made it, until a clock height, until revoked.

Each case is named by the defect that would make it fail. The scheduler is the wake pattern:
a registrar authorizes it once; later a turn of someone else (the wake principal) sends the
ring on the registrar's behalf, and the bell's law names only the registrar.
"""
import json
import unittest

from tests.test_chain import field
from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record

SCHEDULER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record Arg:
  n: Nat
record State:
  note: String
record Edits:
  note: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits, Arg>
type Response = Plans.Response<State, String>
def initial() -> State:
  {note: ""}
def said(context: Abi.Context, text: String) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {note: Plans.Edit::<String, {}>.set({value: text})}})):
    case _: text
def authorize(state: State, input: {target: String, method: String, until: Nat}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.grant({to: context.object, object: {world: "", object: input.target}, method: input.method, until: input.until})):
    case granted(g): said(context, g.id)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def authorizeBell(state: State, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.grant({to: context.object, object: {world: "", object: "bell"}, method: "ring", until: 100n})):
    case granted(g): said(context, g.id)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def fire(state: State, input: {target: String, via: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.sendVia({object: {world: "", object: input.target}, method: "ring", argument: {n: 1n}, via: input.via})):
    case delivery(_): said(context, "sent")
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def fireThenWait(state: State, input: {target: String, via: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.sendVia({object: {world: "", object: input.target}, method: "ring", argument: {n: 1n}, via: input.via})):
    case delivery(_): waited(context)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def waited(context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.await({slot: {principal: "nobody", intent: "never"}, patience: 10n})):
    case timedOut(_): said(context, "waited")
    case _: said(context, "other")
def poke(state: State, input: {target: String, via: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.callVia({object: {world: "", object: input.target}, method: "ring", argument: {n: 1n}, via: input.via})):
    case returned(r): said(context, r.result)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def cancel(state: State, input: {id: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.revoke({id: input.id})):
    case revoked(_): said(context, "revoked")
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def relay(state: State, input: {other: String, target: String}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.call({object: {world: "", object: input.other}, method: "authorizeBell", argument: {n: 0n}})):
    case returned(r): said(context, r.result)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
"""

BELL = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record Arg:
  n: Nat
record State:
  count: Nat
  by: String
  from: String
record Edits:
  count: Plans.Edit<Nat, Nat>
  by: Plans.Edit<String, {}>
  from: Plans.Edit<String, {}>
type Plan = Plans.Plan<Edits, Arg>
type Response = Plans.Response<State, String>
law registrar: request.kind == 0 implies request.subject == "registrar"
def initial() -> State:
  {count: 0n, by: "", from: ""}
def ring(state: State, input: Arg, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: input.n}), by: Plans.Edit::<String, {}>.set({value: context.principal}), from: Plans.Edit::<String, {}>.set({value: context.caller})}})):
    case _: "rung"
"""


ROSTER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
record State:
  count: Nat
  members: Lists.List<String>
record Edits:
  count: Plans.Edit<Nat, Nat>
  members: Plans.Entries<String, String>
type Plan = Plans.Plan<Edits, {}>
type Response = Plans.Response<State, Nat>
law members: request.kind == 0 implies (request.subject in new.members or request.subject == "ember")
law rings: request.kind == 0 implies (request.method == "ring" or request.method == "admit")
def initial() -> State:
  {count: 0n, members: Lists.List::<String>.nil({})}
def ring(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), members: Plans.Entries::<String, String>.keep({})}})):
    case _: 1n
def toll(state: State, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), members: Plans.Entries::<String, String>.keep({})}})):
    case _: 1n
def admit(state: State, input: {who: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.keep({}), members: Plans.Entries::<String, String>.append({item: input.who})}})):
    case _: 0n
"""


class LawFacts(Reflection):
    """`request.subject in new.F` reads membership from state; `request.method` names the method."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("roster", ROSTER, record(count=nat(0), members={"tag": "variant", "label": "nil", "payload": record()}))

    def clause(self, r):
        return r["receipt"]["outcome"].get("clause") if r["status"] == "refused" else r["status"]

    def test_membership_comes_from_state_not_a_hard_coded_principal(self):
        self.assertEqual(self.clause(self.turn("roster", "ring", principal="kim")), "members")
        self.assertEqual(self.clause(self.turn("roster", "admit", record(who=label("kim")))), "admitted")
        self.assertEqual(self.clause(self.turn("roster", "ring", principal="kim")), "admitted")
        self.assertEqual(self.clause(self.turn("roster", "ring", principal="bob")), "members")

    def test_the_law_reads_the_method_that_made_the_change(self):
        self.assertEqual(self.clause(self.turn("roster", "ring")), "admitted")
        self.assertEqual(self.clause(self.turn("roster", "toll")), "rings")

    def test_a_list_membership_of_a_number_fact_is_refused_at_compile(self):
        bad = ROSTER.replace("request.subject in new.members", "request.height in new.members")
        r = self.host.send(op="world-create", principal="ember", identity="bad", object="bad", source=bad,
                           entry="initial", seed=record(count=nat(0), members={"tag": "variant", "label": "nil", "payload": record()}))
        self.assertEqual(r["status"], "error", r)


class Grants(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("scheduler", SCHEDULER, record(note=label("")))
        self.make("bell", BELL, record(count=nat(0), by=label(""), **{"from": label("")}))

    def authorize(self, until=100, method="ring", principal="registrar"):
        r = self.turn("scheduler", "authorize", record(target=label("bell"), method=label(method), until=nat(until)),
                      principal=principal)
        self.assertEqual(r["status"], "admitted", r)
        return r["result"]["value"]

    def fire(self, via, obj="scheduler", principal="wake"):
        r = self.turn(obj, "fire", record(target=label("bell"), via=label(via)), principal=principal)
        self.assertEqual(r["status"], "admitted", r)
        self.fired = r.get("delivered", [])
        return r["result"]["value"]

    def deliver(self):
        """The delivery the last fire's settling pass ran."""
        [receipt] = self.fired
        return receipt

    def bell(self):
        state = self.state("bell")
        return field(state, "count")["value"], field(state, "by")["value"], field(state, "from")["value"]

    def test_a_scheduler_sending_via_the_registrars_grant_is_admitted_by_a_law_naming_the_registrar(self):
        grant = self.authorize()
        held = self.lines()[-1]
        self.assertEqual(json.loads(held)["outcome"]["grants"][0]["grantor"], "registrar")
        self.assertEqual(self.fire(grant), "sent")
        delivered = self.deliver()
        self.assertEqual(delivered["status"], "admitted", delivered)
        entry = delivered["receipt"]
        self.assertEqual(entry["identity"]["principal"], "registrar")
        self.assertEqual(entry["delivery"]["via"], grant)
        self.assertEqual(entry["outcome"]["writes"][0]["vias"], [grant])
        self.assertEqual(self.bell(), ("1", "registrar", "scheduler"))

    def test_the_same_send_without_a_grant_runs_as_the_waker_and_the_law_refuses_it(self):
        self.authorize()
        self.assertEqual(self.fire(""), "sent")
        delivered = self.deliver()
        self.assertEqual((delivered["status"], delivered["receipt"]["outcome"]["clause"]), ("refused", "registrar"))
        self.assertEqual(self.bell(), ("0", "", ""))

    def test_after_revoke_the_send_is_refused_noGrant_in_the_turn(self):
        grant = self.authorize()
        r = self.turn("scheduler", "cancel", record(id=label(grant)), principal="registrar")
        self.assertEqual(r["result"], label("revoked"), r)
        self.assertEqual(self.fire(grant), "noGrant")
        self.assertEqual(self.host.send(op="world-pending")["count"], 0)

    def test_after_the_clock_passes_until_the_send_is_refused_noGrant(self):
        grant = self.authorize(until=5)
        self.host.send(op="world-advance", height=5)
        self.assertEqual(self.fire(grant), "sent")
        self.assertEqual(self.deliver()["status"], "admitted")
        self.host.send(op="world-advance", height=6)
        self.assertEqual(self.fire(grant), "noGrant")

    def test_a_suspended_turn_whose_grant_was_revoked_is_refused_at_its_commit(self):
        grant = self.authorize()
        r = self.turn("scheduler", "fireThenWait", record(target=label("bell"), via=label(grant)), principal="wake")
        self.assertEqual(r["status"], "suspended", r)
        # The grantor revokes from another object, so the scheduler's root stays current.
        self.make("other", SCHEDULER, record(note=label("")))
        revoked = self.turn("other", "cancel", record(id=label(grant)), principal="registrar")
        self.assertEqual(revoked["result"], label("revoked"), revoked)
        advanced = self.host.send(op="world-advance", height=20)
        [resumed] = advanced["resumed"]
        self.assertEqual(resumed["status"], "refused", resumed)
        self.assertEqual(resumed["receipt"]["outcome"].get("clause"), "noGrant", resumed)
        self.assertEqual(self.host.send(op="world-pending")["count"], 0)
        self.assertEqual(self.bell(), ("0", "", ""))

    def test_a_call_via_the_grant_runs_the_callee_as_the_grantor_with_the_caller_as_caller(self):
        grant = self.authorize()
        r = self.turn("scheduler", "poke", record(target=label("bell"), via=label(grant)), principal="wake")
        self.assertEqual((r["status"], r["result"]), ("admitted", label("rung")), r)
        self.assertEqual(self.bell(), ("1", "registrar", "scheduler"))
        plain = self.turn("scheduler", "poke", record(target=label("bell"), via=label("")), principal="wake")
        self.assertEqual(plain["receipt"]["outcome"]["clause"], "registrar")

    def test_a_grant_names_one_method_and_one_object(self):
        grant = self.authorize(method="toll")
        self.assertEqual(self.fire(grant), "noGrant")

    def test_another_object_cannot_use_a_grant_made_to_the_scheduler(self):
        self.make("other", SCHEDULER, record(note=label("")))
        grant = self.authorize()
        self.assertEqual(self.fire(grant, obj="other"), "noGrant")

    def test_a_stranger_cannot_revoke_and_the_grant_still_stands(self):
        self.make("other", SCHEDULER, record(note=label("")))
        grant = self.authorize()
        r = self.turn("other", "cancel", record(id=label(grant)), principal="mallory")
        self.assertEqual(r["result"], label("notGrantor"), r)
        self.assertEqual(self.fire(grant), "sent")

    def test_only_a_direct_turn_may_grant_not_a_callee(self):
        self.make("other", SCHEDULER, record(note=label("")))
        r = self.turn("other", "relay", record(other=label("scheduler"), target=label("bell")), principal="registrar")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["result"], label("notDirect"), r)
        direct = self.turn("scheduler", "authorizeBell", principal="registrar")
        self.assertEqual(len(direct["result"]["value"]), 59, direct)

    def test_grants_and_revocations_replay(self):
        grant = self.authorize()
        kept = self.authorize()
        self.turn("scheduler", "cancel", record(id=label(grant)), principal="registrar")
        self.assertEqual(self.fire(kept), "sent")
        before = self.host.send(op="world-view", principal="ember", object="bell")
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="ember", object="bell"), before)
        self.assertEqual(self.fire(grant), "noGrant")
        self.assertEqual(self.fire(kept), "sent")


if __name__ == "__main__":
    unittest.main()
