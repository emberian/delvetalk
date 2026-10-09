"""The message chains: bell rings, door opens, lantern lights; and a cycle.

Both tests drive the host's `send` machinery: `world-turn` answers a send with a
delivery id, and the settling pass after every durable op runs pending deliveries
(up to 64 per op; the reply carries them as `delivered`). `world-deliver {limit}`
runs any that remain; `world-pending` lists them. The chain is wired with
Card's observers.
"""
import json
import unittest

from tests.test_turn_world import TurnWorld, closure, label, nat, record


def boolean(value):
    return {"tag": "boolean", "value": value}


def empty():
    return {"tag": "record", "fields": []}


def nil():
    return {"tag": "list", "items": []}


def reference(name):
    return record(world=label(""), object=label(name))


def garden_seed(policy="", pending=(), confirm=True, owner="ember"):
    """A Garden Seed: its owner, its policy object, whether prose waits for "yes", and the proposals already waiting."""
    wire = {"tag": "list", "items": [record(principal=label(principal), spell=label(spell))
                                     for principal, spell in pending]}
    return record(owner=label(owner), policy=reference(policy), confirm=boolean(confirm), pending=wire)


def garden_state(planted=0, owner="ember"):
    """A whole Garden State, for world-create (which takes a whole state, not a Seed)."""
    return record(owner=label(owner), planted={"tag": "natural", "value": str(planted)}, policy=reference(""), confirm=boolean(True),
                  pending=nil(), children=nil(), pageCheckpoint=label(""))


# A package that declares a law cannot be imported by a creator ("a law belongs to the
# package's entry module"), so make() creates it with world-create: the whole State is
# these defaults with the Seed's fields laid over them (as the host's create does), made
# by the seed's owner (a law must admit an amendment by its installer).
def lawful_defaults():
    return {
        "Garden": [("owner", label("ember")), ("planted", {"tag": "natural", "value": "0"}), ("policy", reference("")),
                   ("confirm", boolean(True)), ("pending", nil()), ("children", nil()), ("pageCheckpoint", label(""))],
        "Thing": [("owner", label("ember")), ("name", label("")), ("description", label("")), ("holder", reference("")),
                  ("location", reference("")), ("offer", {"tag": "variant", "label": "none", "payload": record()})],
    }


def field(state, name):
    return [f["value"] for f in state["fields"] if f["name"] == name][0]


# Objects are born the way the world makes them: a creator performs `create` with a
# Seed and the host lays it over the child's initial(). The host's own world-create
# still takes a whole state, so a test that wants a Seed borrows a one-method creator.
MAKER = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./PACKAGE.obend as Child
record State:
  made: Nat
record Edits:
  made: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
def initial() -> State:
  {made: 0n}
def make(state: State, input: {id: String, seed: Child.Seed}, context: Abi.Context) -> Activity<Plan, Response, String>:
  match perform(Plan.create({package: "PACKAGE", seed: Data.of::<Child.Seed>(input.seed), law: "", requireAbsent: {world: "", object: input.id}})):
    case created(_): "created"
    case refused(r): r.clause
    case _: "no answer"
"""


class Chain(TurnWorld):
    def make(self, name, modules, seed):
        """Create object `name` from the last module of `modules` with a Seed, through a creator
        (or, for a package that declares a law, with world-create by the seed's owner)."""
        package = modules[-1]["name"]
        if any(line.startswith("law ") for line in modules[-1]["source"].splitlines()):
            given = {f["name"]: f["value"] for f in seed["fields"]}
            whole = [(k, given.get(k, v)) for k, v in lawful_defaults()[package]]
            owner = given.get("owner", label("ember"))["value"]
            r = self.host.send(op="world-create", principal=owner, identity="mk-" + name, object=name,
                               modules=modules, entry="initial", seed={"tag": "record", "fields": [{"name": k, "value": v} for k, v in whole]})
            self.assertEqual(r["status"], "created", r)
            return
        maker = "maker-" + name
        creator = modules + [{"name": "Maker", "source": MAKER.replace("PACKAGE", package)}]
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + maker, object=maker,
                           modules=creator, entry="initial", seed=record(made=nat(0)))
        self.assertEqual(r["status"], "created", r)
        made = self.host.send(op="world-turn", principal="ember", object=maker, method="make",
                              argument=record(id=label(name), seed=seed), identity="make-" + name)
        self.assertEqual((made["status"], made.get("result")), ("admitted", label("created")), made)

    def state(self, name):
        view = self.host.send(op="world-view", principal="ember", object=name)
        self.assertEqual(view["status"], "viewed", view)
        return view["state"]

    def deliver_all(self, rounds=8):
        replies = []
        for _ in range(rounds):
            replies.append(self.host.send(op="world-deliver", limit=16))
            if not self.host.send(op="world-pending").get("count"):
                break
        return replies

    def test_ring_then_open_then_light(self):
        self.make("lantern", closure("Lantern"), record())
        self.make("door", closure("Door"), record())
        silver = {"tag": "variant", "label": "silver", "payload": empty()}
        self.make("bell", closure("Bell"), record(
            colour=silver, seed=label("s"), planting=record(principal=label("glm"), intent=label("p"))))
        # The chain is wired by observers: the door observes the bell, the lantern the door.
        for obj, watcher, method in (("door", "lantern", "light"), ("bell", "door", "open")):
            w = self.turn(obj, "observe", record(object=reference(watcher), method=label(method)))
            self.assertEqual((w["status"], w["result"]["label"]), ("admitted", "edit"), w)
        again = self.turn("bell", "observe", record(object=reference("door"), method=label("open")))
        self.assertEqual(again["result"]["label"], "unchanged")
        ring = self.turn("bell", "ring", principal="gemini")
        self.assertEqual(ring["status"], "admitted", ring)
        self.assertEqual(ring["result"], nat(1))  # one observer, one send
        self.assertEqual(field(self.state("bell"), "rung"), boolean(True))
        # Deliveries run in the settling pass of the same durable op: the ring's reply carries them.
        self.assertEqual([d["status"] for d in ring["delivered"]], ["admitted", "admitted"], ring)
        self.assertEqual(self.host.send(op="world-pending")["count"], 0)
        self.assertEqual(field(self.state("door"), "open"), boolean(True))
        self.assertEqual(field(self.state("door"), "openedBy"), label("gemini"))
        self.assertEqual(field(self.state("lantern"), "lit"), boolean(True))
        self.assertEqual(field(self.state("lantern"), "litBy"), label("gemini"))

    def test_a_tick_cycle_ends_in_a_budget_exhausted_refusal(self):
        self.make("loop", closure("Loop"), record())
        first = self.turn("loop", "tick")
        self.assertEqual(first["status"], "admitted", first)
        replies = self.deliver_all(rounds=200)
        self.assertIn("budgetExhausted", json.dumps(replies))
        self.assertFalse(self.host.send(op="world-pending").get("count"))
        count = int(field(self.state("loop"), "count")["value"])
        self.assertGreater(count, 1)
        # The refusal is the last word: delivering again changes nothing.
        before = self.state("loop")
        self.host.send(op="world-deliver", limit=16)
        self.assertEqual(self.state("loop"), before)


if __name__ == "__main__":
    unittest.main()
