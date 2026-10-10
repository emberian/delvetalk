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


def asking(confirm):
    """A garden's confirmFor: plant when an understood planting waits for "yes"."""
    return {"tag": "list", "items": [label("plant")] if confirm else []}


def garden_seed(policy="", pending=(), confirm=True, owner="ember"):
    """A Garden Seed: its owner, its policy object, whether prose waits for "yes" (plant in
    its confirmFor), and the proposals already waiting."""
    wire = {"tag": "list", "items": [record(principal=label(principal), spell=label(spell), needs=nil())
                                     for principal, spell in pending]}
    return record(owner=label(owner), policy=reference(policy), confirmFor=asking(confirm), pending=wire)


def garden_state(planted=0, owner="ember"):
    """A whole Garden State, for world-create (which takes a whole state, not a Seed)."""
    return record(owner=label(owner), planted={"tag": "natural", "value": str(planted)}, policy=reference(""), confirmFor=asking(True),
                  pending=nil(), children=nil(), pageCheckpoint=label(""), observers=nil())


def field(state, name):
    return [f["value"] for f in state["fields"] if f["name"] == name][0]


class Chain(TurnWorld):
    def make(self, name, modules, seed):
        """Create object `name` from the last module of `modules` with a Seed, which world-create
        lays over the package's initial() as a creator's `create` does; the seed's owner, if it
        names one, creates it (a law must admit an amendment by its installer)."""
        owner = {f["name"]: f["value"] for f in seed["fields"]}.get("owner", label("ember"))["value"]
        r = self.host.send(op="world-create", principal=owner, identity="mk-" + name, object=name,
                           modules=modules, entry="initial", seed=seed)
        self.assertEqual(r["status"], "created", r)

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



class Chains(Chain):
    def test_ring_then_open_then_light(self):
        self.make("lantern", closure("Lantern"), record())
        self.make("door", closure("Door"), record())
        silver = {"tag": "variant", "label": "silver", "payload": empty()}
        self.make("bell", closure("Bell"), record(
            colour=silver, seed=label("s"), planting=label("p"), planter=label("glm"), planterHandle=label("")))
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
