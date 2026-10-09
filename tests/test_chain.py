"""The message chains: bell rings, door opens, lantern lights; and a cycle.

Both tests drive the host's `send` machinery (`world-turn` answers a send with a
delivery id; `world-deliver {limit}` runs the queued deliveries; `world-pending`
lists them). The host lane has not landed it, so both are expected failures.
Against the foundation binary today the first turn that sends is refused:

    receipt outcome {'class': 'evaluation', 'reason': 'plan not supported: send'}

When the host merges, the unexpected success flips these to ordinary passes.
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


def field(state, name):
    return [f["value"] for f in state["fields"] if f["name"] == name][0]


class Chain(TurnWorld):
    def make(self, name, modules, seed):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
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

    def test_ring_then_open_then_light(self):
        self.make("lantern", closure("Lantern"), record(lit=boolean(False), litBy=label("")))
        self.make("door", closure("Door"), record(
            open=boolean(False), openedBy=label(""), knocks=nil(),
            lantern=reference("none"), lastDelivery=label("")))
        silver = {"tag": "variant", "label": "silver", "payload": empty()}
        self.make("bell", closure("Bell"), record(
            planter=label("glm"), colour=silver, seed=label("s"), rains=nil(), rung=boolean(False),
            door=reference("none"), lastDelivery=label(""),
            planting=record(principal=label(""), intent=label(""))))
        # The placeholders are overwritten through the objects' own configure methods.
        for obj, argument in (("door", record(lantern=reference("lantern"))), ("bell", record(door=reference("door")))):
            self.assertEqual(self.turn(obj, "configure", argument)["status"], "admitted")
        ring = self.turn("bell", "ring", record(who=label("gemini")))
        self.assertEqual(ring["status"], "admitted", ring)
        self.assertEqual(field(self.state("bell"), "rung"), boolean(True))
        self.assertNotEqual(field(self.state("bell"), "lastDelivery"), label(""))
        self.assertEqual(field(self.state("lantern"), "lit"), boolean(False))
        self.deliver_all()
        self.assertEqual(field(self.state("door"), "open"), boolean(True))
        self.assertEqual(field(self.state("door"), "openedBy"), label("gemini"))
        self.assertEqual(field(self.state("lantern"), "lit"), boolean(True))
        self.assertEqual(field(self.state("lantern"), "litBy"), label("gemini"))

    def test_a_tick_cycle_ends_in_a_budget_exhausted_refusal(self):
        self.make("loop", closure("Loop"), record(count=nat(0)))
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
