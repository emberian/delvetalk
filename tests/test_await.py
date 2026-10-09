"""create and await: objects born in turns, turns suspended on other turns' receipts.

The clock is `world-advance`; the host never reads wall time.
"""
import time
import unittest

from tests.test_chain import Chain, boolean, nil, reference
from tests.test_objects import closure
from tests.test_replay import get, silver
from tests.test_turn_world import TurnWorld, label, nat, record


def planting(post):
    return record(principal=label("glm"), intent=label(post))


def bell_seed(post="post-1"):
    return record(planter=label("glm"), colour=silver(), seed=label("a bell for lost moths"), rains=nil(),
                  rung=boolean(False), door=reference(""), lastDelivery=label(""), planting=planting(post))


class Await(Chain):
    def bell(self, name="bell", post="post-1"):
        self.make(name, closure("Bell"), bell_seed(post))

    def strike(self, name="bell", ident=None, who="gemini"):
        return self.turn(name, "strike", principal=who, identity=ident or f"strike-{name}")

    def settle(self, post="post-1", who="glm"):
        """Any journaled entry under the slot's identity settles it."""
        return self.host.send(op="world-propose", principal=who, identity=post, roots=[], writes=[])

    def rung(self, name="bell"):
        return self.state_field(name, "rung")

    def state_field(self, obj, name):
        return get(self.state(obj), name)


class Create(Await):
    GARDEN = "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver"

    def plant(self, who="glm", post="at://glm.delve.town/app.bsky.feed.post/3m-plant"):
        return self.turn("garden", "receive", record(text=label(self.GARDEN), who=label(who), post=label(post)),
                         principal=who, identity=post)

    def test_a_planted_bell_appears_with_its_planter_and_only_the_overlaid_fields(self):
        self.make("garden", closure("Garden"), record(planted=nat(0)))
        self.assertEqual(self.plant()["status"], "admitted")
        bell = self.state("garden/bell/1")
        self.assertEqual(get(bell, "planter"), label("glm"))
        self.assertEqual(get(bell, "rung"), boolean(False))                 # default from initial()
        v = self.host.send(op="world-view", principal="e", object="garden/bell/1")
        self.assertEqual((v["status"], v["version"]), ("viewed", 0))
        self.assertEqual(self.state("garden")["fields"][0]["value"], nat(1))

    def test_the_creation_is_journaled_in_the_admitted_entry_and_replays(self):
        self.make("garden", closure("Garden"), record(planted=nat(0)))
        r = self.plant()
        self.assertEqual(r["receipt"]["outcome"]["creates"][0]["object"], "garden/bell/1")
        before = self.state("garden/bell/1")
        self.reopen()
        self.assertEqual(self.state("garden/bell/1"), before)
        # The creator is the owner of what it made (the default law names the planter's turn).
        again = self.host.send(op="world-turn", principal="glm", object="garden/bell/1", method="rain",
                               argument=record(author=label("kimik3"), text=label("rain")), identity="r1")
        self.assertEqual(again["status"], "admitted", again)

    def test_a_second_create_of_one_id_is_refused_naming_the_root_and_creates_nothing(self):
        self.make("garden", closure("Garden"), record(planted=nat(0)))
        first = self.turn("garden", "cistern", record(), principal="kimik3")
        self.assertEqual((first["status"], first["result"]["label"]), ("admitted", "made"))
        second = self.turn("garden", "cistern", record(), principal="glm")
        out = second["receipt"]["outcome"]
        self.assertEqual((second["status"], out["class"], out["object"]), ("refused", "requiredAbsence", "garden/cistern/1"))
        self.assertEqual(second["receipt"]["absent"], ["garden/cistern/1"])
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
sum Seed:
  good: {n: Nat}
  bad: {ghost: Nat}
type Plan = Plans.Plan<Edits, Seed>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {made: 0n}
def make(state: State, input: {kid: String, bad: Bool}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.create({package: "Child", seed: if input.bad then Seed.bad({ghost: 1n}) else Seed.good({n: 5n}), law: "", requireAbsent: {world: "", object: input.kid}})):
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

    def test_an_existing_object_makes_the_create_fail_even_if_made_by_world_create(self):
        self.make("garden", closure("Garden"), record(planted=nat(0)))
        self.make("garden/cistern/1", closure("Cistern"), record(entries=nil()))
        r = self.turn("garden", "cistern", record(), principal="glm")
        self.assertEqual(r["receipt"]["outcome"]["class"], "requiredAbsence")


class Suspend(Await):
    def test_a_strike_before_the_planting_suspends_then_resumes_with_the_receipt_and_rings(self):
        self.bell()
        s = self.strike()
        self.assertEqual(s["status"], "suspended", s)
        self.assertEqual(s["slot"], {"principal": "glm", "intent": "post-1"})
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
        refused = self.host.send(op="world-propose", principal="glm", identity="post-1",
                                 roots=[{"object": "bell", "version": 99}], writes=[])
        self.assertEqual(refused["status"], "refused")
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
        a = self.host.send(op="world-advance", height=8)             # at the deadline: not past it
        self.assertEqual((a["status"], a["clock"], a.get("resumed")), ("advanced", 8, None))
        b = self.host.send(op="world-advance", height=9)
        self.assertEqual(len(b["resumed"]), 1)
        self.assertEqual(b["resumed"][0]["status"], "admitted")
        self.assertEqual(self.rung(), boolean(False))                # timedOut -> unchanged
        self.assertEqual(self.host.send(op="world-view", principal="e", object="bell")["version"], 0)
        # The slot arriving later changes nothing: the strike is over.
        self.assertNotIn("resumed", self.settle())
        self.assertEqual(self.rung(), boolean(False))

    def test_advancing_to_or_before_now_is_a_no_op_and_not_journaled(self):
        h = self.height()
        self.host.send(op="world-advance", height=5)
        self.assertEqual(self.height(), h + 1)
        r = self.host.send(op="world-advance", height=3)
        self.assertEqual((r["status"], r["clock"]), ("advanced", 5))
        self.assertEqual(self.height(), h + 1)

    def test_a_suspended_turn_whose_bell_was_written_meanwhile_is_refused_stale_on_resume(self):
        self.bell()
        self.strike()
        rain = self.turn("bell", "rain", record(author=label("kimik3"), text=label("drip")), principal="kimik3")
        self.assertEqual(rain["status"], "admitted")
        settled = self.settle()
        out = settled["resumed"][0]["receipt"]["outcome"]
        self.assertEqual((settled["resumed"][0]["status"], out["class"], out["object"]), ("refused", "staleRoot", "bell"))
        self.assertEqual(self.rung(), boolean(False))

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
        self.host.send(op="world-advance", height=4)
        self.reopen()
        self.assertEqual(self.host.send(op="world-advance", height=9)["resumed"][0]["status"], "admitted")

    def test_a_ninth_pending_activity_on_one_object_is_refused_by_name(self):
        self.bell()
        for i in range(8):
            self.assertEqual(self.strike(ident=f"s{i}")["status"], "suspended")
        ninth = self.strike(ident="s8")
        out = ninth["receipt"]["outcome"]
        self.assertEqual((ninth["status"], out["class"]), ("refused", "evaluation"))
        self.assertIn("pendingActivitiesPerObject", out["reason"])

    def test_a_tampered_checkpoint_digest_in_the_journal_breaks_open(self):
        self.bell()
        self.strike()
        self.release()
        with open(self.path) as f:
            text = f.read()
        i = text.index('"tokens"')
        with open(self.path, "w") as f:
            f.write(text[:i] + text[i:].replace('"n":"', '"n":"9', 1))
        h = self.spawn()
        r = h.send(op="world-open", path=self.path)
        self.assertEqual(r["status"], "error")
        self.assertIn("height 2", r["message"])


class Seeds(TurnWorld):
    def test_a_thousand_element_seed_is_created_viewed_and_replayed(self):
        from tests.test_turn_world import NAMES_SOURCE, names_modules
        seed = {"tag": "variant", "label": "nil", "payload": record()}
        for i in range(1000):
            seed = {"tag": "variant", "label": "cons", "payload": record(head=label("x"), tail=seed)}
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
