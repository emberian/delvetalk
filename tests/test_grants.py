"""A grant lets one grantee run one method of one object as its grantor, until a clock height, for a
number of uses, until revoked; a law naming the grantor admits it.

Evidence for FOUNDATION §4 Capabilities (layer: host).

Delegation as an object: a grant lets a named grantee run one method of one object as the
principal of the direct turn that made it, until a clock height, until revoked.

Each case is named by the defect that would make it fail. The scheduler is the wake pattern:
a registrar authorizes it once; later a turn of someone else (the wake principal) sends the
ring on the registrar's behalf, and the bell's law names only the registrar.
"""
import json
import unittest

from transport.journal import entries as journal_entries
from tests.host import whole

from tests.test_reflection import Reflection
from tests.wire import field, label, nat, record
from tests.bend import declared

SCHEDULER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record Arg:
  n: Nat
record State:
  note: String
def initial() -> State:
  {note: ""}
def said(context: Abi.Context, text: String) -> Activity<String>:
  match world.write({note: Plans.Edit::<String, {}>.set({value: text})}):
    case _: text
def authorize(state: State, input: {target: String, method: String, until: Nat}, context: Abi.Context) -> Activity<String>:
  match world.grant({to: context.object, object: {world: "", object: input.target}, method: input.method, until: input.until}):
    case granted(g): said(context, g.id)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def authorizeBell(state: State, context: Abi.Context) -> Activity<String>:
  match world.grant({to: context.object, object: {world: "", object: "bell"}, method: "ring", until: 100n}):
    case granted(g): said(context, g.id)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def fire(state: State, input: {target: String, via: String}, context: Abi.Context) -> Activity<String>:
  match world.sendVia({object: {world: "", object: input.target}, method: "ring", argument: Data.of::<Arg>({n: 1n}), via: input.via}):
    case delivery(_): said(context, "sent")
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def fireThenWait(state: State, input: {target: String, via: String}, context: Abi.Context) -> Activity<String>:
  match world.sendVia({object: {world: "", object: input.target}, method: "ring", argument: Data.of::<Arg>({n: 1n}), via: input.via}):
    case delivery(_): waited(context)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def waited(context: Abi.Context) -> Activity<String>:
  match world.await({slot: {principal: "nobody", intent: "never"}, patience: 10n}):
    case timedOut(_): said(context, "waited")
    case _: said(context, "other")
def poke(state: State, input: {target: String, via: String}, context: Abi.Context) -> Activity<String>:
  match world.callVia::<String>({object: {world: "", object: input.target}, method: "ring", argument: Data.of::<Arg>({n: 1n}), via: input.via}):
    case returned(r): said(context, r.result)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def cancel(state: State, input: {id: String}, context: Abi.Context) -> Activity<String>:
  match world.revoke({id: input.id}):
    case revoked(_): said(context, "revoked")
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def relay(state: State, input: {other: String, target: String}, context: Abi.Context) -> Activity<String>:
  match world.call::<String>({object: {world: "", object: input.other}, method: "authorizeBell", argument: {}}):
    case returned(r): said(context, r.result)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
""")

BELL = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record Arg:
  n: Nat
record State:
  count: Nat
  by: String
  from: String
law registrar: request.kind == 0 implies request.subject == "registrar"
def initial() -> State:
  {count: 0n, by: "", from: ""}
def ring(state: State, input: Arg, context: Abi.Context) -> Activity<String>:
  match world.write({count: Plans.Edit::<Nat, Nat>.add({delta: input.n}), by: Plans.Edit::<String, {}>.set({value: context.principal}), from: Plans.Edit::<String, {}>.set({value: context.caller})}):
    case _: "rung"
""")


ROSTER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
  members: Lists.List<String>
law members: request.kind == 0 implies (request.subject in new.members or request.subject == "ember")
law rings: request.kind == 0 implies (request.method == "ring" or request.method == "admit")
def initial() -> State:
  {count: 0n, members: Lists.List::<String>.nil({})}
def ring(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write({count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), members: Plans.Entries::<String, String>.keep({})}):
    case _: 1n
def toll(state: State, context: Abi.Context) -> Activity<Nat>:
  match world.write({count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), members: Plans.Entries::<String, String>.keep({})}):
    case _: 1n
def admit(state: State, input: {who: String}, context: Abi.Context) -> Activity<Nat>:
  match world.write({count: Plans.Edit::<Nat, Nat>.keep({}), members: Plans.Entries::<String, String>.append({item: input.who})}):
    case _: 0n
""")


class LawFacts(Reflection):
    """`request.subject in new.F` reads membership from state; `request.method` names the method."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("roster", ROSTER, record(count=nat(0), members={"tag": "list", "items": []}))

    def clause(self, r):
        return r["receipt"]["outcome"].get("clause") if r["status"] == "refused" else r["status"]

    def test_membership_comes_from_state_and_the_law_reads_the_method_that_made_the_change(self):
        self.assertEqual(self.clause(self.turn("roster", "ring", principal="kim")), "members")
        self.assertEqual(self.clause(self.turn("roster", "admit", record(who=label("kim")))), "admitted")
        self.assertEqual(self.clause(self.turn("roster", "ring", principal="kim")), "admitted")
        self.assertEqual(self.clause(self.turn("roster", "ring", principal="bob")), "members")
        self.assertEqual(self.clause(self.turn("roster", "toll")), "rings")

    def test_a_list_membership_of_a_number_fact_is_refused_at_compile(self):
        bad = ROSTER.replace("request.subject in new.members", "request.height in new.members")
        r = self.host.send(op="world-create", principal="ember", identity="bad", object="bad", source=bad,
                           entry="initial", seed=record(count=nat(0), members={"tag": "list", "items": []}))
        self.assertEqual(r["status"], "error", r)


class GrantFixture(Reflection):
    opener = None

    def setUp(self):
        super().setUp()
        self.open_library(**({"opener": self.opener} if self.opener else {}))
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



class Grants(GrantFixture):
    def test_a_scheduler_sending_via_the_registrars_grant_is_admitted_by_a_law_naming_the_registrar(self):
        grant = self.authorize()
        held = self.lines()[-1]
        self.assertEqual(json.loads(held)["outcome"]["grants"][0]["grantor"], "registrar")
        self.assertEqual(self.fire(grant), "sent")
        delivered = self.deliver()
        self.assertEqual(delivered["status"], "admitted", delivered)
        entry = whole(self.host, delivered)
        self.assertEqual(entry["identity"]["principal"], "registrar")
        self.assertEqual(entry["delivery"]["via"], grant)
        self.assertEqual(entry["outcome"]["writes"][0]["vias"], [grant])
        self.assertEqual(self.bell(), ("1", "registrar", "scheduler"))

    def test_without_the_grant_for_this_method_and_object_the_send_is_the_wakers_or_noGrant(self):
        self.make("other", SCHEDULER, record(note=label("")))
        grant = self.authorize()
        self.assertEqual(self.fire(""), "sent")
        delivered = self.deliver()
        self.assertEqual((delivered["status"], delivered["receipt"]["outcome"]["clause"]), ("refused", "registrar"))
        self.assertEqual(self.fire(grant, obj="other"), "noGrant")       # granted to the scheduler, not to other
        self.assertEqual(self.fire(self.authorize(method="toll")), "noGrant")   # a grant names one method
        self.assertEqual(self.bell(), ("0", "", ""))

    def test_a_stranger_cannot_revoke_and_after_the_grantors_revoke_the_send_is_noGrant(self):
        self.make("other", SCHEDULER, record(note=label("")))
        grant = self.authorize()
        self.assertEqual(self.turn("other", "cancel", record(id=label(grant)), principal="mallory")["result"], label("notGrantor"))
        self.assertEqual(self.fire(grant), "sent")
        self.assertEqual(self.turn("scheduler", "cancel", record(id=label(grant)), principal="registrar")["result"], label("revoked"))
        self.assertEqual(self.fire(grant), "noGrant")
        self.reopen()
        self.assertEqual(self.fire(grant), "noGrant")

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
        advanced = self.host.send(op="world-advance", principal="wake", height=20)
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

    def test_only_a_direct_turn_may_grant_not_a_callee(self):
        self.make("other", SCHEDULER, record(note=label("")))
        r = self.turn("other", "relay", record(other=label("scheduler"), target=label("bell")), principal="registrar")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["result"], label("notDirect"), r)
        direct = self.turn("scheduler", "authorizeBell", principal="registrar")
        self.assertEqual(len(direct["result"]["value"]), 59, direct)


class GrantLifecycle(GrantFixture):
    opener = "ember"

    def lower_bound(self, n=1):
        r = self.host.send(op="world-open", path=self.path, maxGrants=n)
        self.assertEqual(r["status"], "opened", r)

    def listed(self, gid):
        rows = self.host.send(op="world-grants", principal="registrar", grant=gid)["grants"]
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["id"], gid)
        return rows[0]

    def test_revocation_releases_capacity_and_the_cited_id_keeps_its_ending(self):
        self.lower_bound()
        gid = self.authorize()
        self.fire(gid)
        receipt = whole(self.host, self.deliver())
        self.assertEqual(receipt["outcome"]["writes"][0]["vias"], [gid])
        refused = self.turn("scheduler", "authorizeBell", principal="registrar")
        self.assertEqual((refused["status"], refused["receipt"]["outcome"]["class"]), ("refused", "capacity"), refused)
        self.assertIn("maxGrants", refused["receipt"]["outcome"]["reason"])
        revoked = self.host.send(op="world-revoke", principal="registrar", identity="end", grant=gid)
        self.assertEqual(revoked["status"], "admitted", revoked)
        ended = self.listed(gid)
        self.assertEqual((ended["ended"], ended["endedAt"]), ("revoked", revoked["receipt"]["height"]))
        self.assertNotIn("reading", ended)
        self.assertNotIn("fixed", ended)
        self.assertNotEqual(self.authorize(), gid)
        for snapshot in (False, True):
            if snapshot:
                self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
            self.reopen()
            self.assertEqual(self.listed(gid), ended)
            self.assertEqual(self.fire(gid), "noGrant")
            inspected = self.host.send(op="world-inspect", principal="registrar", grant=gid)
            self.assertEqual(inspected["grant"], ended)

    def test_expiry_is_inclusive_and_compacts_at_the_clock_entry_not_the_read(self):
        self.lower_bound()
        gid = self.authorize(until=5)
        self.host.send(op="world-advance", height=5)
        r = self.turn("scheduler", "authorizeBell", principal="registrar")
        self.assertEqual(r["status"], "refused", r)
        expired = self.host.send(op="world-advance", height=6)
        ended = self.listed(gid)
        self.assertEqual((ended["ended"], ended["endedAt"]), ("expired", expired["receipt"]["height"]))
        self.authorize()
        self.reopen()
        self.assertEqual(self.listed(gid), ended)

    def test_a_residents_65th_live_grant_is_refused_but_other_residents_and_opener_have_room(self):
        for _ in range(64):
            self.authorize()
        r = self.turn("scheduler", "authorizeBell", principal="registrar")
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"]), ("refused", "capacity"), r)
        self.assertIn("grantsPerPrincipal", r["receipt"]["outcome"]["reason"])
        self.authorize(principal="kim")
        for _ in range(65):
            self.authorize(principal="ember")
        gid = self.host.send(op="world-grants", principal="registrar")["grants"][0]["id"]
        ended = self.host.send(op="world-revoke", principal="ember", identity="release-share", grant=gid)
        self.assertEqual(ended["status"], "admitted", ended)
        self.authorize()

    def test_the_257th_tombstone_evicts_only_the_live_index_copy_and_journal_resolves_the_oldest(self):
        self.lower_bound()
        first = None
        for i in range(257):
            gid = self.authorize()
            r = self.host.send(op="world-revoke", principal="registrar", identity=f"end-{i}", grant=gid)
            self.assertEqual(r["status"], "admitted", r)
            if first is None:
                first = gid
                height = r["receipt"]["height"]
        self.assertEqual(self.host.send(op="world-snapshot")["status"], "snapshot")
        from tests.test_snapshot import read_snapshot
        body = read_snapshot(self.path + ".snapshot." + str(self.host.send(op="world-status")["height"]) + ".cbor")
        self.assertEqual(body["grants"], [])
        self.assertEqual(len(body["grantTombstones"]), 256)
        self.assertNotIn(first, [g["id"] for g in body["grantTombstones"]])
        self.reopen()
        oldest = self.listed(first)
        self.assertEqual((oldest["ended"], oldest["endedAt"]), ("revoked", height))

    def test_a_lent_reading_is_only_in_the_creation_receipt_after_compaction(self):
        from tests.test_extend import CARD
        self.make("card", CARD, record(count=nat(0)))
        lent = self.turn("card", "receive", record(text=label("delvetalk card lend / to: kim / method: bump / until: +5"), post=label("")))
        self.assertEqual(lent["status"], "admitted", lent)
        [terms] = lent["receipt"]["outcome"]["grants"]
        self.assertIn("lent by ember", terms["reading"])
        self.host.send(op="world-advance", height=6)
        row = self.listed(terms["id"])
        self.assertEqual(row["ended"], "expired")
        self.assertNotIn("reading", row)
        self.assertNotIn("until", row)

    def test_expired_on_creation_is_immediately_a_tombstone_and_does_not_fill_the_cap(self):
        self.lower_bound()
        self.host.send(op="world-advance", height=6)
        gid = self.authorize(until=5)
        row = self.listed(gid)
        self.assertEqual((row["ended"], row["endedAt"]), ("expired", row["height"]))
        self.authorize()

    def test_grant_reads_bound_unknown_ids_and_do_not_reveal_a_private_targets_tombstone(self):
        gid = self.authorize()
        self.host.send(op="world-revoke", principal="registrar", identity="ended-private", grant=gid)
        hidden = self.host.send(op="world-root", principal="ember", reason="private target",
                                act={"kind": "set", "object": "bell", "field": "read", "value": {"principals": ["registrar", "ember"]}})
        self.assertEqual(hidden["status"], "root", hidden)
        self.assertEqual(self.host.send(op="world-inspect", principal="mallory", grant=gid)["status"], "denied")
        self.assertEqual(self.host.send(op="world-grants", principal="mallory", grant=gid)["grants"], [])
        for op in ("world-inspect", "world-grants"):
            r = self.host.send(op=op, principal="registrar", grant="g" * 256)
            self.assertEqual(r["status"], "unknown" if op == "world-inspect" else "grants", r)
            too_long = self.host.send(op=op, principal="registrar", grant="g" * 257)
            self.assertEqual(too_long["status"], "error", too_long)
            self.assertIn("1..256", too_long["message"])

    def test_a_grant_bound_can_only_be_lowered(self):
        r = self.host.send(op="world-open", path=self.path, maxGrants=4097)
        self.assertEqual(r["status"], "error", r)
        self.assertIn("never raise", r["message"])


LAMP = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  colour: String
  level: Nat
  by: String
law owner: request.kind == 0 implies request.subject == "owner"
def initial() -> State:
  {colour: "", level: 0n, by: ""}
def light(state: State, input: {colour: String, level: Nat}, context: Abi.Context) -> Activity<String>:
  match world.write({colour: Plans.Edit::<String, {}>.set({value: input.colour}), level: Plans.Edit::<Nat, Nat>.set({value: input.level}), by: Plans.Edit::<String, {}>.set({value: context.principal})}):
    case _: input.colour
""")

HOLDER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  note: String
record Fix:
  colour: String
record Level:
  level: Nat
record Full:
  colour: String
  level: Nat
def initial() -> State:
  {note: ""}
def said(context: Abi.Context, text: String) -> Activity<String>:
  match world.write({note: Plans.Edit::<String, {}>.set({value: text})}):
    case _: text
def authorize(state: State, input: {colour: String, uses: Nat}, context: Abi.Context) -> Activity<String>:
  match world.grantWith({to: context.object, object: {world: "", object: "lamp"}, method: "light", until: 100n, fixed: Data.of::<Fix>({colour: input.colour}), uses: input.uses}):
    case granted(g): said(context, g.id)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def dim(state: State, input: {via: String, level: Nat}, context: Abi.Context) -> Activity<String>:
  match world.callVia::<String>({object: {world: "", object: "lamp"}, method: "light", argument: Data.of::<Level>({level: input.level}), via: input.via}):
    case returned(r): said(context, r.result)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def paint(state: State, input: {via: String, colour: String}, context: Abi.Context) -> Activity<String>:
  match world.callVia::<String>({object: {world: "", object: "lamp"}, method: "light", argument: Data.of::<Full>({colour: input.colour, level: 1n}), via: input.via}):
    case returned(r): said(context, r.result)
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
def post(state: State, input: {via: String, level: Nat}, context: Abi.Context) -> Activity<String>:
  match world.sendVia({object: {world: "", object: "lamp"}, method: "light", argument: Data.of::<Level>({level: input.level}), via: input.via}):
    case delivery(_): said(context, "sent")
    case refused(r): said(context, r.clause)
    case _: said(context, "other")
""")


class Attenuation(Reflection):
    """A grant may fix part of the callee's argument, serve a number of uses, and be revoked by
    its grantor as a write of its own (`world-revoke`)."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("lamp", LAMP, record(colour=label(""), level=nat(0), by=label("")))
        self.make("holder", HOLDER, record(note=label("")))

    def grant(self, colour="red", uses=2):
        r = self.turn("holder", "authorize", record(colour=label(colour), uses=nat(uses)), principal="owner")
        self.assertEqual(r["status"], "admitted", r)
        return r["result"]["value"]

    def lamp(self):
        s = self.state("lamp")
        return field(s, "colour")["value"], field(s, "level")["value"], field(s, "by")["value"]

    def use(self, method, via, principal="kim", **arg):
        r = self.turn("holder", method, record(via=label(via), **arg), principal=principal)
        self.assertIn(r["status"], ("admitted", "refused"), r)
        return r

    def test_world_grants_lists_each_grant_as_it_stands_with_its_entry(self):
        g = self.grant()
        self.use("dim", g, level=nat(3))
        [listed] = self.host.send(op="world-grants", principal="anonymous")["grants"]
        self.assertEqual((listed["id"], listed["object"], listed["uses"], listed["revoked"]), (g, "lamp", 1, False), listed)
        made = [e for e in journal_entries(self.path) if g in json.dumps(e) and '"grants"' in json.dumps(e)][0]
        self.assertEqual((listed["height"], listed["hash"]), (made["height"], made["hash"]))
        self.host.send(op="world-revoke", principal="owner", identity="rv", grant=g)
        [after] = self.host.send(op="world-grants", principal="", reverse=True)["grants"]
        self.assertTrue(after["revoked"], after)

    def test_revocation_drops_fixed_arguments_and_uses_from_the_compact_record(self):
        gid = self.grant()
        terms = next(g for e in journal_entries(self.path) for g in e.get("outcome", {}).get("grants", []) if g["id"] == gid)
        self.assertIn("fixed", terms)
        self.assertEqual(terms["uses"], 2)
        revoked = self.host.send(op="world-revoke", principal="owner", identity="compact-fixed", grant=gid)
        self.assertEqual(revoked["status"], "admitted", revoked)
        [row] = self.host.send(op="world-grants", principal="owner", grant=gid)["grants"]
        self.assertEqual((row["id"], row["ended"], row["endedAt"]), (gid, "revoked", revoked["receipt"]["height"]))
        self.assertNotIn("fixed", row)
        self.assertNotIn("uses", row)
        self.reopen()
        [after] = self.host.send(op="world-grants", principal="owner", grant=gid)["grants"]
        self.assertEqual(after, row)

    def test_the_fixed_part_is_merged_into_the_callers_argument_and_a_grant_needs_a_use(self):
        self.assertEqual(self.grant(uses=0), "uses")
        g = self.grant()
        r = self.use("dim", g, level=nat(3))
        self.assertEqual((r["status"], r["result"]), ("admitted", label("red")), r)
        self.assertEqual(self.lamp(), ("red", "3", "owner"))
        self.assertEqual(r["receipt"]["outcome"]["spent"], [{"id": g, "uses": 1}])

    def test_a_conflicting_field_is_refused_and_spends_nothing_and_the_same_bytes_pass(self):
        g = self.grant(uses=1)
        self.assertEqual(self.use("paint", g, colour=label("blue"))["result"], label("grantConflict"))
        self.assertEqual(self.lamp(), ("", "0", ""))
        same = self.use("paint", g, colour=label("red"))
        self.assertEqual(same["result"], label("red"), same)
        self.assertEqual(self.lamp(), ("red", "1", "owner"))

    def test_uses_run_out_and_stay_spent_across_a_restart(self):
        g = self.grant(uses=2)
        self.assertEqual(self.use("dim", g, level=nat(1))["result"], label("red"))
        self.assertEqual(self.use("dim", g, level=nat(2))["result"], label("red"))
        self.assertEqual(self.use("dim", g, level=nat(3))["result"], label("grantSpent"))
        self.assertEqual(self.lamp(), ("red", "2", "owner"))
        # Once by replay, once from a snapshot that holds the grant's uses left.
        self.reopen()
        self.assertEqual(self.use("dim", g, level=nat(4))["result"], label("grantSpent"))
        self.assertIn("height", self.host.send(op="world-snapshot"))
        self.reopen()
        self.assertGreater(self.host.send(op="world-open", path=self.path)["snapshot"]["resumed"], 0)
        self.assertEqual(self.use("dim", g, level=nat(4), principal="ann")["result"], label("grantSpent"))

    def test_a_send_under_an_attenuated_grant_delivers_the_merged_argument(self):
        g = self.grant(uses=1)
        r = self.use("post", g, level=nat(7))
        self.assertEqual(r["result"], label("sent"), r)
        [send] = r["receipt"]["sends"]
        self.assertEqual(sorted(f["name"] for f in send["argument"]["fields"]), ["colour", "level"])
        [delivered] = r["delivered"]
        self.assertEqual(delivered["status"], "admitted", delivered)
        self.assertEqual(self.lamp(), ("red", "7", "owner"))
        self.assertEqual(self.use("post", g, level=nat(8))["result"], label("grantSpent"))

    def test_the_grantor_revokes_as_a_write_of_its_own_and_a_stranger_cannot(self):
        g = self.grant(uses=5)
        stranger = self.host.send(op="world-revoke", principal="mallory", identity="r1", grant=g)
        self.assertEqual((stranger["status"], stranger["receipt"]["outcome"]["clause"]), ("refused", "notGrantor"), stranger)
        self.assertEqual(self.use("dim", g, level=nat(1))["result"], label("red"))
        mine = self.host.send(op="world-revoke", principal="owner", identity="r2", grant=g)
        self.assertEqual(mine["status"], "admitted", mine)
        self.assertEqual(mine["receipt"]["outcome"]["revokes"], [g])
        self.assertEqual(self.use("dim", g, level=nat(2))["result"], label("noGrant"))
        self.reopen()
        self.assertEqual(self.use("dim", g, level=nat(2))["result"], label("noGrant"))
        self.assertEqual(self.host.send(op="world-revoke", principal="owner", identity="r3", grant="nope")["status"], "error")

LENDER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  colour: String
  level: Nat
  note: String
record Fix:
  colour: String
law owner: request.kind == 2 or request.subject == "owner"
def initial() -> State:
  {colour: "", level: 0n, note: ""}
def light(state: State, input: {colour: String, level: Nat}, context: Abi.Context) -> Activity<String>:
  match world.write({colour: Plans.Edit::<String, {}>.set({value: input.colour}), level: Plans.Edit::<Nat, Nat>.set({value: input.level}), note: Plans.Edit::<String, {}>.keep({})}):
    case _: input.colour
def lend(state: State, input: {to: String}, context: Abi.Context) -> Activity<String>:
  match world.grantWith({to: input.to, object: {world: "", object: context.object}, method: "light", until: 100n, fixed: Data.of::<Fix>({colour: "red"}), uses: 1n}):
    case granted(g): g.id
    case refused(r): r.clause
    case _: "other"
""", "light", "lend")


class LentDirect(Reflection):
    """A thing lending its own method to a principal (`lentVia`): the borrower's own turn runs it as a call under
    the grant does, its fixed part merged and a use spent (codex 2026-10-12 host 3); refuted if the borrower
    names another colour, or lights it twice on one use."""

    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("lamp", LENDER, record(colour=label(""), level=nat(0), note=label("")))

    def light(self, **arg):
        return self.turn("lamp", "light", record(**arg), principal="kim")

    def test_a_direct_turn_under_a_lent_grant_keeps_its_fixed_part_and_spends_its_use(self):
        self.assertEqual(self.light(colour=label("red"), level=nat(1))["status"], "refused")
        lent = self.turn("lamp", "lend", record(to=label("kim")), principal="owner")
        self.assertEqual(lent["status"], "admitted", lent)
        blue = self.light(colour=label("blue"), level=nat(2))
        self.assertEqual((blue["status"], blue["receipt"]["outcome"].get("clause")), ("refused", "grantConflict"), blue)
        red = self.light(colour=label("red"), level=nat(3))
        self.assertEqual(red["status"], "admitted", red)
        self.assertEqual(len(red["receipt"]["outcome"]["spent"]), 1, red)
        again = self.light(colour=label("red"), level=nat(4))
        self.assertEqual(again["status"], "refused", again)
        s = self.state("lamp")
        self.assertEqual((field(s, "colour")["value"], field(s, "level")["value"]), ("red", "3"))


if __name__ == "__main__":
    unittest.main()
