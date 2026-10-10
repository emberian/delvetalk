"""create and await: objects born in turns, turns suspended on other turns' receipts.

The clock is `world-advance`; the host never reads wall time.
"""
import time
import unittest

from tests.host import awaiting_relations
from tests.test_chain import Chain, boolean, garden_seed, nil, reference
from tests.test_objects import closure
from tests.test_replay import get, rows, silver
from tests.test_turn_world import TurnWorld, label, nat, record


def uri(post):
    return post if post.startswith("at://") else "at://did:plc:glm/town.delve.feed.post/" + post


def bell_seed(post="post-1"):
    return record(colour=silver(), seed=label("a bell for lost moths"), planting=label(uri(post)), planter=label("glm"), planterHandle=label(""))


# The object the planting posts are recorded for: a reply to one runs here (its receive
# refuses, by its law, when the reply says "no"), and that turn answers the post.
HUB = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
law cap: new.count <= 0
def initial() -> State:
  {count: 0n}
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  if input.text == "no" then refusing(context) else 0n
def refusing(context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})}})):
    case _: 1n
"""


class Await(Chain):
    """A bell's strike awaits the planting post's answer (awaitPost): the first turn on the
    post's recorded object whose replyTo names it. The posts are recorded for a hub."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.host.send(op="world-open", path=self.path, clock="transport")["status"], "opened")
        r = self.host.send(op="world-create", principal="ember", identity="mk-hub", object="hub",
                           modules=closure("Plan") + [{"name": "Hub", "source": HUB}], entry="initial", seed=record(count=nat(0)))
        self.assertEqual(r["status"], "created", r)
        self.recorded = set()

    def bell(self, name="bell", post="post-1"):
        self.make(name, closure("Bell"), bell_seed(post))

    def strike(self, name="bell", ident=None, who="gemini"):
        return self.turn(name, "strike", principal=who, identity=ident or f"strike-{name}")

    def settle(self, post="post-1", who="glm", text="yes"):
        """The reply that answers the post: a turn on the hub with replyTo = post."""
        post = uri(post)
        if post not in self.recorded:
            r = self.host.send(op="world-posted", principal="transport", uri=post, cid="c", object="hub")
            self.assertEqual(r["status"], "posted", r)
            self.recorded.add(post)
        return self.host.send(op="world-turn", principal=who, object="hub", method="receive",
                              argument=record(text=label(text), post=label(post + "/reply")), identity=post + "/reply", replyTo=post)

    def rung(self, name="bell"):
        return self.state_field(name, "rung")

    def state_field(self, obj, name):
        return get(self.state(obj), name)


class Create(Await):
    GARDEN = "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver"

    def plant(self, who="glm", post="at://glm.delve.town/app.bsky.feed.post/3m-plant"):
        return self.turn("garden", "receive", record(text=label(self.GARDEN), post=label(post), slot=label("")),
                         principal=who, identity=post)

    @awaiting_relations
    def test_a_planted_bell_appears_with_its_planter_and_only_the_overlaid_fields(self):
        self.make("garden", closure("Garden"), garden_seed())
        self.assertEqual(self.plant()["status"], "admitted")
        bell = self.state("garden/bell/1")
        self.assertEqual((get(bell, "planter"), get(bell, "planting")), (label("glm"), label("at://glm.delve.town/app.bsky.feed.post/3m-plant")))
        self.assertEqual(get(bell, "rung"), boolean(False))                 # default from initial()
        v = self.host.send(op="world-view", principal="e", object="garden/bell/1")
        self.assertEqual((v["status"], v["version"]), ("viewed", 0))
        self.assertEqual([f["value"] for f in self.state("garden")["fields"] if f["name"] == "planted"][0], nat(1))

    @awaiting_relations
    def test_the_creation_is_journaled_in_the_admitted_entry_and_replays(self):
        self.make("garden", closure("Garden"), garden_seed())
        r = self.plant()
        self.assertEqual(r["receipt"]["outcome"]["creates"][0]["object"], "garden/bell/1")
        before = self.state("garden/bell/1")
        self.reopen()
        self.assertEqual(self.state("garden/bell/1"), before)
        # The creator is the owner of what it made (the default law names the planter's turn).
        again = self.host.send(op="world-turn", principal="glm", object="garden/bell/1", method="rain",
                               argument=record(text=label("rain")), identity="r1")
        self.assertEqual(again["status"], "admitted", again)

    def test_a_second_create_of_one_id_is_refused_naming_the_root_and_creates_nothing(self):
        self.make("garden", closure("Garden"), garden_seed())
        first = self.turn("garden", "cistern", record(), principal="kimik3")
        self.assertEqual((first["status"], first["result"]["label"]), ("admitted", "made"))
        second = self.turn("garden", "cistern", record(), principal="glm")
        out = second["receipt"]["outcome"]
        self.assertEqual((second["status"], out["class"], out["object"]), ("refused", "requiredAbsence", "garden/cistern"))
        self.assertEqual(second["receipt"]["absent"], ["garden/cistern"])
        self.assertNotIn("creates", out)

    def test_a_partial_seed_overlays_initial_and_a_field_the_state_lacks_is_refused_as_type_mismatch(self):
        child = "edition ObjectiveBend 1\nrecord State:\n  n: Nat\n  m: Nat\ndef initial() -> State:\n  {n: 0n, m: 9n}\n"
        maker = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  made: Nat
record Edits:
  made: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {made: 0n}
def make(state: State, input: {kid: String, bad: Bool}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.create({package: "Child", seed: if input.bad then Data.of::<{ghost: Nat}>({ghost: 1n}) else Data.of::<{n: Nat}>({n: 5n}), law: "", requireAbsent: {world: "", object: input.kid}})):
    case created(_): "created"
    case refused(r): r.clause
    case _: "other"
"""
        modules = closure("Plan") + [{"name": "Child", "source": child}, {"name": "Maker", "source": maker}]
        r = self.host.send(op="world-create", principal="ember", identity="mk", object="maker",
                           modules=modules, entry="initial", seed=record(made=nat(0)))
        self.assertEqual(r["status"], "created", r)
        no = lambda kid, bad: self.turn("maker", "make", record(kid=label(kid), bad={"tag": "boolean", "value": bad}))
        bad = no("k0", True)
        self.assertEqual((bad["status"], bad["result"]), ("admitted", label("typeMismatch")))
        self.assertEqual(self.host.send(op="world-view", principal="e", object="k0")["status"], "unknown")
        good = no("k1", False)
        self.assertEqual(good["result"], label("created"))
        kid = {f["name"]: f["value"] for f in self.state("k1")["fields"]}
        self.assertEqual((kid["n"], kid["m"]), (nat(5), nat(9)))        # n overlaid, m from initial()
        self.reopen()
        again = {f["name"]: f["value"] for f in self.state("k1")["fields"]}
        self.assertEqual(again, kid)

    @awaiting_relations
    def test_bells_are_minted_past_an_id_already_held_and_the_garden_records_the_minted_one(self):
        self.make("garden", closure("Garden"), garden_seed())
        self.make("garden/bell/1", closure("Bell"), bell_seed())
        r = self.plant()
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "planted"), r)
        self.assertEqual(r["receipt"]["outcome"]["creates"][0]["object"], "garden/bell/2")
        children = [get(c, "object")["value"] for c in get(self.state("garden"), "children")["items"]]
        self.assertEqual(children, ["garden/bell/2"])
        self.assertEqual(self.plant(post="at://glm.delve.town/app.bsky.feed.post/3m-plant2")["receipt"]["outcome"]["creates"][0]["object"], "garden/bell/3")

    def test_an_existing_object_makes_the_create_fail_even_if_made_by_world_create(self):
        self.make("garden", closure("Garden"), garden_seed())
        self.make("garden/cistern", closure("Cistern"), record())
        r = self.turn("garden", "cistern", record(), principal="glm")
        self.assertEqual(r["receipt"]["outcome"]["class"], "requiredAbsence")


class Suspend(Await):
    def test_a_strike_before_the_planting_suspends_then_resumes_with_the_receipt_and_rings(self):
        self.bell()
        s = self.strike()
        self.assertEqual(s["status"], "suspended", s)
        self.assertEqual(s["receipt"]["outcome"]["post"], uri("post-1"))
        self.assertEqual(s["deadline"], 8)                       # clock 0 + patience 8
        self.assertEqual(self.rung(), boolean(False))
        settled = self.settle()
        self.assertEqual(settled["status"], "admitted")
        resumed = settled["resumed"]
        self.assertEqual([r["status"] for r in resumed], ["admitted"])
        self.assertEqual(self.rung(), boolean(True))
        final = self.host.send(op="world-receipt", principal="gemini", identity="strike-bell")
        self.assertEqual(final["receipt"]["outcome"]["tag"], "admitted")
        self.assertEqual(final["receipt"]["identity"], {"principal": "gemini", "intent": "strike-bell"})
        self.assertIn("resumes", final["receipt"])

    def test_an_await_on_an_identity_that_already_committed_answers_at_once(self):
        self.bell()
        self.settle()
        r = self.strike()
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.rung(), boolean(True))

    def test_a_refused_planting_resumes_the_strike_with_the_refusal_and_the_bell_stays_silent(self):
        self.bell()
        self.strike()
        refused = self.settle(text="no")
        self.assertEqual(refused["status"], "refused", refused)
        # The strike heard the refusal: its own turn is admitted and the bell stays silent.
        self.assertEqual(refused["resumed"][0]["status"], "admitted")
        self.assertEqual(self.rung(), boolean(False))

    def test_a_retry_of_the_suspended_turn_returns_the_suspension_not_a_second_one(self):
        self.bell()
        first = self.strike()
        h = self.height()
        again = self.strike()
        self.assertEqual(again, first)
        self.assertEqual(self.height(), h)

    def test_the_clock_moves_only_by_world_advance_and_times_out_a_waiting_strike(self):
        self.bell()
        s = self.strike()
        a = self.host.send(op="world-advance", principal="transport", height=8)             # at the deadline: not past it
        self.assertEqual((a["status"], a["clock"], a.get("resumed")), ("advanced", 8, None))
        b = self.host.send(op="world-advance", principal="transport", height=9)
        self.assertEqual(len(b["resumed"]), 1)
        self.assertEqual(b["resumed"][0]["status"], "admitted")
        self.assertEqual(self.rung(), boolean(False))                # timedOut -> unchanged
        self.assertEqual(self.host.send(op="world-view", principal="e", object="bell")["version"], 0)
        # The slot arriving later changes nothing: the strike is over.
        self.assertNotIn("resumed", self.settle())
        self.assertEqual(self.rung(), boolean(False))

    def test_advancing_to_or_before_now_is_a_no_op_and_not_journaled(self):
        h = self.height()
        self.host.send(op="world-advance", principal="transport", height=5)
        self.assertEqual(self.height(), h + 1)
        r = self.host.send(op="world-advance", principal="transport", height=3)
        self.assertEqual((r["status"], r["clock"]), ("advanced", 5))
        self.assertEqual(self.height(), h + 1)

    @awaiting_relations
    def test_a_suspended_turn_whose_bell_was_rained_on_meanwhile_is_rebased_on_resume(self):
        # The rain appended to `rains`; the strike sets only `rung`, which nothing else changed, so
        # the resumed strike commits on the bell as it is now (a resumed turn's own object re-bases).
        self.bell()
        self.strike()
        rain = self.turn("bell", "rain", record(text=label("drip")), principal="kimik3")
        self.assertEqual(rain["status"], "admitted")
        settled = self.settle()
        [resumed] = settled["resumed"]
        self.assertEqual((resumed["status"], resumed["result"]), ("admitted", boolean(True)), resumed)
        self.assertNotIn("rerunOf", resumed)
        self.assertEqual(self.rung(), boolean(True))

    def test_restart_between_suspend_and_resume_rebuilds_the_activity_from_the_journal(self):
        self.bell()
        self.strike()
        self.reopen()
        settled = self.settle()
        self.assertEqual([r["status"] for r in settled["resumed"]], ["admitted"])
        self.assertEqual(self.rung(), boolean(True))
        self.reopen()
        self.assertEqual(self.rung(), boolean(True))
        self.assertEqual(self.host.send(op="world-receipt", principal="gemini", identity="strike-bell")
                         ["receipt"]["outcome"]["tag"], "admitted")

    def test_the_deadline_survives_a_restart(self):
        self.bell()
        self.strike()
        self.host.send(op="world-advance", principal="transport", height=4)
        self.reopen()
        self.assertEqual(self.host.send(op="world-advance", principal="transport", height=9)["resumed"][0]["status"], "admitted")

    def test_a_ninth_pending_activity_on_one_object_is_refused_by_name(self):
        self.bell()
        for i in range(8):
            self.assertEqual(self.strike(ident=f"s{i}")["status"], "suspended")
        ninth = self.strike(ident="s8")
        out = ninth["receipt"]["outcome"]
        self.assertEqual((ninth["status"], out["class"], out["reason"]), ("refused", "capacity", "pendingActivitiesPerObject"))

    def test_a_tampered_checkpoint_digest_in_the_journal_breaks_open(self):
        self.bell()
        self.strike()
        self.release()
        with open(self.path) as f:
            text = f.read()
        i = text.index('"items"')  # the checkpoint's tokens are journaled as blocks
        with open(self.path, "w") as f:
            # A v2 checkpoint's tokens are bare: change the first number in the blocks.
            j = next(k for k in range(i, len(text)) if text[k].isdigit() and text[k - 1] in "[,")
            f.write(text[:j] + "9" + text[j:])
        h = self.spawn()
        r = h.send(op="world-open", path=self.path)
        self.assertEqual(r["status"], "error")
        self.assertIn("height 5", r["message"])  # the clock setting, the hub and the Maker creator's two entries come first


# Waits on a post, then sends the bell a rain under the waiting turn's principal.
RELAY = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {count: 0n}
def wait(state: State, input: {post: String, text: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.awaitPost({post: input.post, patience: 8n})):
    case reply(_): sent(input.text, context)
    case _: 0n
def sent(text: String, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.send({object: {world: context.world, object: "bell"}, method: "rain", argument: {text: text}})):
    case delivery(_): 1n
    case _: 0n
"""


class Rains(Await):
    @awaiting_relations
    def test_two_agents_raining_in_one_settle_pass_are_both_admitted(self):
        """Two agents' turns wait on one post; the reply resumes both in one settling pass and
        their two rains reach the bell as two deliveries of that pass: two inserts of
        different keys, both admitted, both kept in key order."""
        self.bell()
        r = self.host.send(op="world-create", principal="ember", identity="mk-relay", object="relay",
                           modules=closure("Plan") + [{"name": "Relay", "source": RELAY}], entry="initial", seed=record(count=nat(0)))
        self.assertEqual(r["status"], "created", r)
        for who, text in (("kimik3", "a drizzle"), ("gemini", "a squall")):
            w = self.turn("relay", "wait", record(post=label(uri("post-1")), text=label(text)), principal=who, identity="wait-" + who)
            self.assertEqual(w["status"], "suspended", w)
        settled = self.settle()
        self.assertEqual([x["status"] for x in settled["resumed"]], ["admitted", "admitted"], settled)
        rains = [x for x in settled.get("delivered", []) if x.get("receipt", {}).get("identity", {}).get("principal") in ("kimik3", "gemini")]
        self.assertEqual([x["status"] for x in rains], ["admitted", "admitted"], rains)
        authors = sorted(get(r, "author")["value"] for r in rows(self.state_field("bell", "rains")))
        self.assertEqual(authors, ["gemini", "kimik3"])


class Seeds(TurnWorld):
    def test_a_thousand_element_seed_is_created_viewed_and_replayed(self):
        from tests.test_turn_world import NAMES_SOURCE, names_modules
        seed = {"tag": "list", "items": [label("x") for _ in range(1000)]}
        r = self.host.send(op="world-create", principal="ember", identity="mk", object="n",
                           modules=names_modules(), entry="initial", seed=record(names=seed))
        self.assertEqual(r["status"], "created", r)
        v = self.host.send(op="world-view", principal="e", object="n")
        self.assertEqual(v["state"]["fields"][0]["value"], seed)
        self.reopen()
        self.assertEqual(self.host.send(op="world-view", principal="e", object="n")["state"], v["state"])
        grown = self.turn("n", "add", record(text=label("last")))
        self.assertEqual(grown["status"], "admitted", grown)


class Maximum(Await):
    def test_a_hundred_suspended_activities_over_twenty_objects_resume_one_slot_each_in_time(self):
        for i in range(20):
            self.bell(f"b{i}", post=f"p{i}-0")
        for i in range(20):
            self.bell(f"c{i}", post=f"p{i}-1")
        # 100 suspensions: five slots per object pair; each object holds at most eight.
        slots = []
        for i in range(20):
            for k in range(5):
                bell = f"b{i}" if k < 3 else f"c{i}"
                self.assertEqual(self.strike(bell, ident=f"s-{i}-{k}")["status"], "suspended")
                slots.append((bell, f"s-{i}-{k}"))
        self.assertEqual(sum(1 for _ in slots), 100)
        t0 = time.time()
        resumed = 0
        for i in range(20):
            for post in (f"p{i}-0", f"p{i}-1"):
                r = self.settle(post)
                resumed += len(r.get("resumed", []))
        took = time.time() - t0
        print(f"\n  100 resumptions {took:.2f}s")
        self.assertEqual(resumed, 100)
        self.assertLess(took, 10.0)


if __name__ == "__main__":
    unittest.main()
