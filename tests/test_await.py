"""Objects are born in turns by create, and a turn suspended on another turn's receipt (`await` on its slot)
resumes when it lands, times out by the clock, and survives restart.

Evidence for FOUNDATION §3 (layer: host).

create and await: objects born in turns, turns suspended on other turns' receipts.

The clock is `world-advance`; the host never reads wall time.
"""
import json
import unittest

from transport.journal import entries as journal_entries
from tests.wire import write_journal

from tests.test_chain import Chain, silver, town_garden
from tests.wire import boolean, field, label, nat, record, rows
from tests.bend import closure, declared


def uri(post):
    return post if post.startswith("at://") else "at://did:plc:glm/town.delve.feed.post/" + post


def bell_seed(post="post-1"):
    return record(colour=silver(), seed=label("a bell for lost moths"), planting=label(uri(post)), planter=label("glm"), planterHandle=label(""))


# The object the awaited turns run on: its receive refuses, by its law, when the text says "no".
HUB = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
law cap: new.count <= 0
def initial() -> State:
  {count: 0n}
def receive(state: State, input: {text: String, post: String}, context: Abi.Context) -> Activity<Nat>:
  if input.text == "no" then refusing(context) else 0n
def refusing(context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case _: 1n
""")

# The strike awaits the receipt of one turn (its slot: principal and intent) and rings if that turn was
# admitted; a rain counts, touching nothing the strike writes. Its card takes the host's spells.
STRIKER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
import ./Document.obend as Document
import ./Form.obend as Form
import ./Card.obend as Card
record State:
  principal: String
  intent: String
  rung: Bool
  rains: Nat
def initial() -> State:
  {principal: "", intent: "", rung: false, rains: 0n}
def strike(state: State, context: Abi.Context) -> Activity<Bool>:
  match world.await({slot: {principal: state.principal, intent: state.intent}, patience: 8n}):
    case reply(r): ringOn(r.receipt.outcome, state.rung, context)
    case _: state.rung
def ringOn(outcome: Plans.Outcome, rung: Bool, context: Abi.Context) -> Activity<Bool>:
  match outcome:
    case admitted(_): rang(context)
    case _: rung
def rang(context: Abi.Context) -> Activity<Bool>:
  match world.write(extend(keep(), {rung: Plans.Edit::<Bool, {}>.set({value: true})})):
    case _: true
def rain(state: State, input: {text: String}, context: Abi.Context) -> Activity<Nat>:
  match world.write(extend(keep(), {rains: Plans.Edit::<Nat, Nat>.add({delta: 1n})})):
    case _: state.rains + 1n
form rain:
  text: text 1..120
def receive(state: State, input: Card.Reply, context: Abi.Context) -> Activity<Card.Replied>:
  Card.answer(input, context, forms(), Document.text("A striker."))
""", "strike", "rain")


class Await(Chain):
    """A striker's strike awaits one turn's receipt on the hub, named by its slot (glm's intent)."""

    def setUp(self):
        super().setUp()
        self.assertEqual(self.host.send(op="world-open", path=self.path, clock="transport")["status"], "opened")
        r = self.host.send(op="world-create", principal="ember", identity="mk-hub", object="hub",
                           modules=closure("World") + [{"name": "Hub", "source": HUB}], entry="initial", seed=record(count=nat(0)))
        self.assertEqual(r["status"], "created", r)

    def bell(self, name="bell", intent="answer-1"):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=closure("Lantern")[:-1] + [{"name": "Striker", "source": STRIKER}], entry="initial",
                           seed=record(principal=label("glm"), intent=label(intent)))
        self.assertEqual(r["status"], "created", r)

    def strike(self, name="bell", ident=None, who="gemini"):
        return self.turn(name, "strike", principal=who, identity=ident or f"strike-{name}")

    def settle(self, intent="answer-1", who="glm", text="yes"):
        """The awaited turn: glm's turn on the hub under the slot's intent."""
        return self.host.send(op="world-turn", principal=who, object="hub", method="receive",
                              argument=record(text=label(text), post=label("")), identity=intent)

    def rung(self, name="bell"):
        return self.state_field(name, "rung")

    def state_field(self, obj, name):
        return field(self.state(obj), name)


class Create(Await):
    GARDEN = "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver"

    def plant(self, who="glm", post="at://glm.delve.town/app.bsky.feed.post/3m-plant"):
        return self.turn("garden", "receive", record(text=label(self.GARDEN), post=label(post)),
                         principal=who, identity=post)

    def test_a_partial_seed_overlays_initial_and_a_field_the_state_lacks_is_refused_as_type_mismatch(self):
        child = "edition ObjectiveBend 1\nrecord State:\n  n: Nat\n  m: Nat\ndef initial() -> State:\n  {n: 0n, m: 9n}\n"
        maker = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  made: Nat
def initial() -> State:
  {made: 0n}
def make(state: State, input: {kid: String, bad: Bool}, context: Abi.Context) -> Activity<String>:
  match world.create({package: "Child", seed: if input.bad then Data.of::<{ghost: Nat}>({ghost: 1n}) else Data.of::<{n: Nat}>({n: 5n}), law: "", requireAbsent: {world: "", object: input.kid}}):
    case created(_): "created"
    case refused(r): r.clause
    case _: "other"
""")
        modules = closure("World") + [{"name": "Child", "source": child}, {"name": "Maker", "source": maker}]
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

    def test_bells_are_minted_past_an_id_already_held_and_the_garden_holds_the_minted_one(self):
        """kind/bell asks the host for the first free garden/bell/<n> (HOST-HANDOFF 5.127), so an id someone else
        already holds refuses nothing."""
        town_garden(self.host.send)
        self.make("garden/bell/1", closure("Bell"), bell_seed())
        r = self.plant()
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(r["receipt"]["outcome"]["creates"][0]["object"], "garden/bell/2")
        things = [field(c, "object")["value"] for c in rows(field(self.state("garden"), "things"))]
        self.assertEqual(things, ["garden/bell/2"])
        self.assertEqual(self.plant(post="at://glm.delve.town/app.bsky.feed.post/3m-plant2")["receipt"]["outcome"]["creates"][0]["object"], "garden/bell/3")

class Suspend(Await):
    def test_a_strike_before_the_awaited_turn_suspends_then_resumes_with_its_receipt_and_rings(self):
        self.bell()
        s = self.strike()
        self.assertEqual(s["status"], "suspended", s)
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

    def test_an_await_on_a_committed_turn_answers_at_once_and_on_a_refused_one_resumes_silent(self):
        self.bell()
        self.settle()
        self.assertEqual(self.strike()["status"], "admitted")
        self.assertEqual(self.rung(), boolean(True))
        self.bell("other", intent="answer-2")
        self.strike("other")
        refused = self.settle(intent="answer-2", text="no")
        self.assertEqual(refused["status"], "refused", refused)
        # The strike heard the refusal: its own turn is admitted and the bell stays silent.
        self.assertEqual(refused["resumed"][0]["status"], "admitted")
        self.assertEqual(self.rung("other"), boolean(False))

    def test_the_clock_moves_only_forward_by_world_advance_and_times_out_a_waiting_strike(self):
        self.bell()
        self.strike()
        h = self.height()
        a = self.host.send(op="world-advance", principal="transport", height=8)             # at the deadline: not past it
        self.assertEqual((a["status"], a["clock"], a.get("resumed")), ("advanced", 8, None))
        r = self.host.send(op="world-advance", principal="transport", height=3)              # backwards: a no-op, unjournaled
        self.assertEqual((r["status"], r["clock"], self.height()), ("advanced", 8, h + 1))
        b = self.host.send(op="world-advance", principal="transport", height=9)
        self.assertEqual([x["status"] for x in b["resumed"]], ["admitted"])
        self.assertEqual(self.rung(), boolean(False))                # timedOut -> unchanged
        self.assertEqual(self.host.send(op="world-view", principal="e", object="bell")["version"], 0)
        # The awaited turn arriving later changes nothing: the strike is over.
        self.assertNotIn("resumed", self.settle())
        self.assertEqual(self.rung(), boolean(False))

    def test_a_suspended_turn_whose_bell_was_rained_on_meanwhile_is_rebased_on_resume(self):
        # The rain added to `rains`; the strike sets only `rung`, which nothing else changed, so
        # the resumed strike commits on the bell as it is now (a resumed turn's own object re-bases).
        self.bell()
        self.strike(who="glm")  # glm's own resumption: glm's reply carries its result
        rain = self.turn("bell", "rain", record(text=label("drip")), principal="kimik3")
        self.assertEqual(rain["status"], "admitted")
        settled = self.settle()
        [resumed] = settled["resumed"]
        self.assertEqual((resumed["status"], resumed["result"]), ("admitted", boolean(True)), resumed)
        self.assertNotIn("rerunOf", resumed)
        self.assertEqual(self.rung(), boolean(True))

    def test_a_rule_placed_on_a_waiting_turns_object_moves_no_version_and_the_turn_resumes(self):
        # A placing is not a state move: the strike rooted on the bell at its version resumes after a rule is
        # placed on the bell, and the rule is read back.
        self.bell()
        self.strike(who="glm")
        version = self.host.send(op="world-view", principal="glm", object="bell")["version"]
        spell = "delvetalk bell rule\nname: told\nwhen: request.method == \"rain\"\nthen: delvetalk bell rain / text: again"
        placed = self.turn("bell", "receive", record(text=label(spell), post=label("")), principal="kimik3", identity="place-told")
        self.assertEqual(placed["status"], "admitted", placed)
        self.assertEqual(self.host.send(op="world-view", principal="glm", object="bell")["version"], version)
        self.assertEqual([(r["name"], r["from"]) for r in self.host.send(op="world-rules", principal="glm", object="bell")["rows"]],
                         [("told", "bell")])
        [resumed] = self.settle()["resumed"]
        self.assertEqual((resumed["status"], resumed["result"]), ("admitted", boolean(True)), resumed)
        self.assertEqual(self.host.send(op="world-view", principal="glm", object="bell")["version"], version + 1)

    def test_a_settling_turn_sees_another_principals_resumption_only_as_its_projection(self):
        # codex host 1: glm's turn releases gemini's strike; glm's reply carries gemini's receipt as
        # glm may read it, never its result or the journaled resumption.
        self.bell()
        self.strike()
        [resumed] = self.settle()["resumed"]
        self.assertEqual((resumed["status"], resumed["receipt"]["identity"]["principal"]), ("admitted", "gemini"), resumed)
        self.assertNotIn("result", resumed)
        self.assertNotIn("result", resumed["receipt"])
        self.assertNotIn("resumes", resumed["receipt"])
        self.assertNotIn("ticksUsed", resumed)

    def test_restart_between_suspend_and_resume_rebuilds_the_activity_and_its_deadline(self):
        self.bell()
        self.bell("late", intent="answer-2")
        self.strike()
        self.strike("late")
        self.host.send(op="world-advance", principal="transport", height=4)
        self.reopen()
        self.assertEqual([r["status"] for r in self.settle()["resumed"]], ["admitted"])
        self.assertEqual(self.rung(), boolean(True))
        self.assertEqual(self.host.send(op="world-receipt", principal="gemini", identity="strike-bell")
                         ["receipt"]["outcome"]["tag"], "admitted")
        self.reopen()
        self.assertEqual(self.host.send(op="world-advance", principal="transport", height=9)["resumed"][0]["status"], "admitted")
        self.assertEqual(self.rung("late"), boolean(False))

    def test_a_ninth_pending_activity_on_one_object_is_refused_by_name(self):
        self.bell()
        for i in range(8):
            self.assertEqual(self.strike(ident=f"s{i}")["status"], "suspended")
        ninth = self.strike(ident="s8")
        out = ninth["receipt"]["outcome"]
        self.assertEqual((ninth["status"], out["class"], out["reason"]), ("refused", "capacity", "the host's pendingActivitiesPerObject is full; it drains as readings and waits settle: try later."))

    def test_a_tampered_checkpoint_digest_in_the_journal_breaks_open(self):
        self.bell()
        self.strike()
        self.release()
        entries = journal_entries(self.path)
        text = json.dumps(entries[-1], separators=(",", ":"))
        i = text.index('"items"')  # the strike's checkpoint tokens, journaled as blocks
        # A v2 checkpoint's tokens are bare: change the first number in the blocks. The entry keeps its old hash.
        j = next(k for k in range(i, len(text)) if text[k].isdigit() and text[k - 1] in "[,")
        entries[-1] = json.loads(text[:j] + "9" + text[j:])
        write_journal(self.path, entries)
        h = self.spawn()
        r = h.send(op="world-open", path=self.path)
        self.assertEqual(r["status"], "error")
        self.assertIn("height 4", r["message"])  # the strike's entry: after the clock setting, the hub and the striker


# Waits on glm's turn, then sends the bell a rain under the waiting turn's principal.
RELAY = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def wait(state: State, input: {intent: String, text: String}, context: Abi.Context) -> Activity<Nat>:
  match world.await({slot: {principal: "glm", intent: input.intent}, patience: 8n}):
    case reply(_): sent(input.text, context)
    case _: 0n
def sent(text: String, context: Abi.Context) -> Activity<Nat>:
  match world.send({object: {world: context.world, object: "bell"}, method: "rain", argument: {text: text}}):
    case delivery(_): 1n
    case _: 0n
""")


class Rains(Await):
    def test_two_agents_raining_in_one_settle_pass_are_both_admitted(self):
        """Two agents' turns wait on one turn; its receipt resumes both in one settling pass and
        their two rains reach the bell as two deliveries of that pass: two inserts of
        different keys, both admitted, both kept in key order."""
        self.make("bell", closure("Bell"), bell_seed())
        r = self.host.send(op="world-create", principal="ember", identity="mk-relay", object="relay",
                           modules=closure("World") + [{"name": "Relay", "source": RELAY}], entry="initial", seed=record(count=nat(0)))
        self.assertEqual(r["status"], "created", r)
        for who, text in (("kimik3", "a drizzle"), ("gemini", "a squall")):
            w = self.turn("relay", "wait", record(intent=label("answer-1"), text=label(text)), principal=who, identity="wait-" + who)
            self.assertEqual(w["status"], "suspended", w)
        settled = self.settle()
        self.assertEqual([x["status"] for x in settled["resumed"]], ["admitted", "admitted"], settled)
        rains = [x for x in settled.get("delivered", []) if x.get("receipt", {}).get("identity", {}).get("principal") in ("kimik3", "gemini")]
        self.assertEqual([x["status"] for x in rains], ["admitted", "admitted"], rains)
        authors = sorted(field(r, "author")["value"] for r in rows(self.state_field("bell", "rains")))
        self.assertEqual(authors, ["gemini", "kimik3"])


if __name__ == "__main__":
    unittest.main()
