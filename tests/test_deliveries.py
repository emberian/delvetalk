"""send and the causal ledger: deliveries run as later turns, budgets only shrink.

Deliveries run in the settling pass after every durable op (at most 64 per op), so a
sending turn's reply carries them as `delivered`; `world-deliver` runs what is left.

The Bell/Door/Lantern shapes are one fixture package instantiated three times;
Loop is the same package sending to itself.
"""
import unittest

from tests.test_turn_world import TurnWorld, closure, label, nat, record

MAX_DEPTH = 100          # Limits.maxDepth
SENDS_PER_TURN = 32      # Limits.sendsPerTurn

SOURCE = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
  lit: Bool
record Arg:
  target: String
  left: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
  lit: Plans.Edit<Bool, {}>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
%(law)sdef initial() -> State:
  {count: 0n, lit: false}
def keep() -> Edits:
  {count: Plans.Edit::<Nat, Nat>.keep({}), lit: Plans.Edit::<Bool, {}>.keep({})}
def sendTo(target: String, method: String, argument: Arg) -> Activity<Plan, Response, Nat>:
  match perform(Plan.send({object: {world: "", object: target}, method: method, argument: Data.of::<Arg>(argument)})):
    case delivery(_): 1n
    case _: 0n
def tally(context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})})):
    case written(_): 1n
    case _: 0n
def ring(state: State, input: Arg, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})})):
    case written(_): sendTo(input.target, "open", {target: "lantern", left: 0n})
    case _: 0n
def open(state: State, input: Arg, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})})):
    case written(_): sendTo(input.target, "light", {target: "", left: 0n})
    case _: 0n
def light(state: State, input: Arg, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: extend(keep(), {lit: Plans.Edit::<Bool, {}>.set({value: true})})})):
    case written(_): 1n
    case _: 0n
def spin(state: State, input: Arg, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})})):
    case written(_): sendTo(input.target, "spin", {target: context.object, left: 0n})
    case _: 0n
def hop(state: State, input: Arg, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match perform(Plan.write({object: Plans.self(context), edits: extend(keep(), {count: Plans.Edit::<Nat, Nat>.add({delta: 1n})})})):
    case written(_): hopOn(input.left, context)
    case _: 0n
def hopOn(left: Nat, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  match left:
    case 0: 1n
    case 1+previous: sendTo(context.object, "hop", {target: "", left: previous})
def fan(state: State, input: Arg, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  fanOut(input.target, input.left)
def fanOut(target: String, left: Nat) -> Activity<Plan, Response, Nat>:
  match left:
    case 0: 1n
    case 1+previous:
      match perform(Plan.send({object: {world: "", object: target}, method: "light", argument: Data.of::<Arg>({target: "", left: 0n})})):
        case delivery(_): fanOut(target, previous)
        case _: 0n
"""


def package(law=""):
    return closure("Plan") + [{"name": "Relay", "source": SOURCE % {"law": law}}]


def arg(target="", left=0):
    return record(target=label(target), left=nat(left))


class Deliveries(TurnWorld):
    def make(self, obj, law="", chain=None, principal="ember"):
        request = dict(op="world-create", principal=principal, identity="mk-" + obj, object=obj,
                       modules=package(law), entry="initial",
                       seed=record(count=nat(0), lit={"tag": "boolean", "value": False}))
        if chain:
            request["chain"] = chain
        r = self.host.send(**request)
        self.assertEqual(r["status"], "created", r)

    def fields(self, obj):
        v = self.host.send(op="world-view", principal="e", object=obj)["state"]["fields"]
        return {f["name"]: f["value"]["value"] for f in v}

    def turn(self, *args, **kwargs):
        r = super().turn(*args, **kwargs)
        self.settled = getattr(self, "settled", []) + r.get("delivered", [])
        return r

    def deliver_all(self, limit=16, rounds=64):
        """Every delivery since the last call: those the settling passes ran, then the rest."""
        receipts, self.settled = getattr(self, "settled", []), []
        if not self.pending()["count"]:
            return receipts
        for _ in range(rounds):
            r = self.host.send(op="world-deliver", limit=limit)
            self.assertEqual(r["status"], "delivered", r)
            receipts += r["receipts"] + r.get("delivered", [])
            if r["pending"] == 0 and not self.pending()["count"]:
                break
        return receipts

    def pending(self):
        return self.host.send(op="world-pending")

    def entries(self):
        import json
        with open(self.path) as f:
            return [json.loads(line) for line in f]


class Chain(Deliveries):
    def test_ring_opens_the_door_which_lights_the_lantern_across_three_objects(self):
        for name in ("bell", "door", "lantern"):
            self.make(name)
        r = self.turn("bell", "ring", arg("door"), principal="glm", identity="ring-1")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.pending()["count"], 0)
        receipts = self.deliver_all()
        self.assertEqual([x["status"] for x in receipts], ["admitted", "admitted"])
        self.assertEqual(self.fields("lantern")["lit"], True)
        self.assertEqual((self.fields("bell")["count"], self.fields("door")["count"]), ("1", "1"))
        self.assertEqual(self.pending()["count"], 0)

    def test_a_delivery_runs_as_its_senders_principal_and_its_receipt_names_the_sender(self):
        for name in ("bell", "door", "lantern"):
            self.make(name)
        sent = self.turn("bell", "ring", arg("door"), principal="glm", identity="ring-1")
        first = self.deliver_all()[0]["receipt"]
        self.assertEqual(first["identity"]["principal"], "glm")
        self.assertEqual(first["identity"]["intent"], first["delivery"]["id"])
        self.assertEqual(first["delivery"]["from"], {"principal": "glm", "intent": "ring-1"})
        self.assertEqual(first["delivery"]["id"], sent["receipt"]["sends"][0]["id"])

    def test_a_delivery_inherits_the_ledger_decremented(self):
        for name in ("bell", "door", "lantern"):
            self.make(name)
        sent = self.turn("bell", "ring", arg("door"), identity="ring-1")
        top = sent["receipt"]["ledger"]
        self.assertEqual(top["depth"], MAX_DEPTH)
        child = sent["receipt"]["sends"][0]["ledger"]
        self.assertEqual(child["depth"], MAX_DEPTH - 1)
        self.assertEqual(child["work"], top["work"] - sent["ticksUsed"])
        self.assertLessEqual(child["storage"], top["storage"])

    def test_a_refused_sending_turn_delivers_nothing(self):
        self.make("bell", law="law none: new.count <= 0\n")
        self.make("door")
        r = self.turn("bell", "ring", arg("door"))
        self.assertEqual(r["receipt"]["outcome"]["class"], "lawRefused")
        self.assertNotIn("sends", r["receipt"])
        self.assertEqual(self.pending()["count"], 0)
        self.assertEqual(self.deliver_all(), [])

    def test_a_send_to_an_unknown_object_is_consumed_as_a_refused_delivery(self):
        self.make("bell")
        self.turn("bell", "ring", arg("ghost"))
        r = self.deliver_all()
        self.assertEqual(r[0]["receipt"]["outcome"]["class"], "unknownObject")
        self.assertEqual(self.pending()["count"], 0)


class Exhaustion(Deliveries):
    def test_a_loop_sending_to_itself_stops_at_exactly_max_depth_with_a_journaled_refusal(self):
        self.make("loop")
        self.turn("loop", "spin", arg("loop"))
        receipts = self.deliver_all()
        self.assertEqual(self.fields("loop")["count"], str(MAX_DEPTH))
        self.assertEqual(self.pending()["count"], 0)
        last = receipts[-1]["receipt"]["outcome"]
        self.assertEqual((last["class"], last["reason"]), ("budgetExhausted", "depth"))
        self.assertEqual(len(receipts), MAX_DEPTH)          # 99 runs and the refusal
        self.assertEqual(receipts[-1]["receipt"]["ledger"]["depth"], 0)
        self.assertEqual(sum(1 for r in receipts if r["status"] == "admitted"), MAX_DEPTH - 1)

    def measure_spin(self):
        """Ticks of one spin turn, measured in a scratch world so no queue is left here."""
        import os
        scratch = self.spawn()
        scratch.send(op="world-open", path=os.path.join(self.dir.name, "scratch.journal"))
        scratch.send(op="world-create", principal="ember", identity="mk", object="m", modules=package(),
                     entry="initial", seed=record(count=nat(0), lit={"tag": "boolean", "value": False}))
        return scratch.send(op="world-turn", principal="ember", object="m", method="spin",
                            argument=arg("m"), identity="t")["ticksUsed"]

    def test_a_two_object_cycle_exhausts_work_before_depth(self):
        ticks = self.measure_spin()
        work = int(ticks * 2.5)
        self.make("ping", chain={"depth": MAX_DEPTH, "work": work, "storage": 1048576})
        self.make("pong")
        self.turn("ping", "spin", arg("pong"))
        receipts = self.deliver_all()
        last = receipts[-1]["receipt"]
        self.assertEqual((last["outcome"]["class"], last["outcome"]["reason"]), ("budgetExhausted", "work"))
        self.assertGreater(last["ledger"]["depth"], 0)
        self.assertEqual(int(self.fields("ping")["count"]) + int(self.fields("pong")["count"]), 3)

    def test_a_chain_ledger_can_be_lowered_at_creation_never_raised(self):
        r = self.host.send(op="world-create", principal="ember", identity="x", object="x",
                           modules=package(), entry="initial",
                           seed=record(count=nat(0), lit={"tag": "boolean", "value": False}),
                           chain={"depth": MAX_DEPTH + 1, "work": 1, "storage": 1})
        self.assertEqual(r["status"], "error")

    def test_the_ledger_is_not_a_field_of_a_turn_request(self):
        self.make("loop")
        r = self.host.send(op="world-turn", principal="ember", object="loop", method="spin",
                           argument=arg("loop"), identity="t", ledger={"depth": 10 ** 9, "work": 10 ** 9, "storage": 10 ** 9})
        self.assertEqual(r["receipt"]["ledger"]["depth"], MAX_DEPTH)


class Restart(Deliveries):
    def test_restart_with_deliveries_left_over_resumes_the_queue_and_delivers_each_id_once(self):
        self.make("loop")
        first = self.turn("loop", "spin", arg("loop"), principal="glm")
        self.assertEqual(len(first["delivered"]), 64)    # the settling pass's share
        before = self.pending()
        self.assertEqual(before["count"], 1)
        self.reopen()                                    # as after a crash with the queue non-empty
        self.assertEqual(self.pending(), before)
        self.settled = []
        rest = self.deliver_all()
        self.assertEqual(len(rest), MAX_DEPTH - 64)
        self.assertEqual(self.deliver_all(), [])         # a retry delivers nothing twice
        self.reopen()
        self.assertEqual(self.pending()["count"], 0)
        ids = [e["delivery"]["id"] for e in self.entries() if "delivery" in e]
        self.assertEqual(len(ids), MAX_DEPTH)
        self.assertEqual(len(set(ids)), MAX_DEPTH)
        self.assertEqual(self.fields("loop")["count"], str(MAX_DEPTH))

    def test_the_ledger_is_in_the_journal_so_restart_cannot_mint_capacity(self):
        self.make("loop")
        self.turn("loop", "spin", arg("loop"))
        self.reopen()
        self.settled = []
        receipts = self.deliver_all()
        self.assertEqual(int(self.fields("loop")["count"]), MAX_DEPTH)
        self.assertEqual(receipts[-1]["receipt"]["outcome"]["reason"], "depth")

    def test_a_tampered_ledger_in_a_sending_entry_breaks_the_chain(self):
        self.make("loop")
        self.turn("loop", "spin", arg("loop"))
        self.release()
        with open(self.path) as f:
            lines = f.read().splitlines()
        lines[1] = lines[1].replace('"depth":99', '"depth":999')     # the sending entry, height 2
        with open(self.path, "w") as f:
            f.write("\n".join(lines) + "\n")
        h = self.spawn()
        r = h.send(op="world-open", path=self.path)
        self.assertEqual(r["status"], "error")
        self.assertIn("height 2", r["message"])


class Maximum(Deliveries):
    def test_a_chain_of_sixty_four_deliveries_completes(self):
        self.make("loop")
        self.turn("loop", "hop", arg("", 64))
        receipts = self.deliver_all()
        self.assertEqual(len(receipts), 64)
        self.assertTrue(all(r["status"] == "admitted" for r in receipts))
        self.assertEqual(self.fields("loop")["count"], "65")
        self.assertEqual(self.pending()["count"], 0)

    def test_two_hundred_fan_out_sends_are_refused_by_the_per_turn_limit_and_nothing_is_delivered(self):
        self.make("fanner")
        self.make("lantern")
        r = self.turn("fanner", "fan", arg("lantern", 200))
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"]), ("refused", "evaluation"))
        self.assertIn("send capacity", out["reason"])
        self.assertEqual(self.pending()["count"], 0)
        self.assertEqual(self.deliver_all(), [])
        self.assertEqual(self.fields("lantern")["lit"], False)

    def test_exactly_the_limit_of_sends_is_delivered(self):
        self.make("fanner")
        self.make("lantern")
        r = self.turn("fanner", "fan", arg("lantern", SENDS_PER_TURN))
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(len(r["receipt"]["sends"]), SENDS_PER_TURN)
        self.assertEqual(len({s["id"] for s in r["receipt"]["sends"]}), SENDS_PER_TURN)
        self.assertEqual(len(self.deliver_all()), SENDS_PER_TURN)
        self.assertEqual(self.fields("lantern")["lit"], True)


if __name__ == "__main__":
    unittest.main()
