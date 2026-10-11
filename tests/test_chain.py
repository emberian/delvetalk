"""Sends ring a bell that opens a door that lights a lantern, delivered in the settling pass.

Evidence for FOUNDATION §3 Delivery (layer: host).

The message chain: bell rings, door opens, lantern lights.

This drives the host's `send` machinery: `world-turn` answers a send with a
delivery id, and the settling pass after every durable op runs pending deliveries
(up to 64 per op; the reply carries them as `delivered`). `world-deliver {limit}`
runs any that remain; `world-pending` lists them. The chain is wired with
subscriptions.
"""
import unittest

from tests.test_turn_world import TurnWorld
from tests.wire import boolean, empty, field, label, nat, nil, record, reference, relation
from tests.bend import closure


def town_kinds(send, owner="ember", names=("bell", "cistern")):
    """The named kinds as genesis makes them (deploy/genesis.py KINDS; bell and cistern unless told): a Kind created
    under its law, then shaped, so a garden plants and digs through them and a room carves rooms. `send(**request)` is the host's."""
    from deploy import genesis
    for name, of, form, head, law, body in genesis.KINDS:
        if name not in names or send(op="world-view", principal=owner, object="kind/" + name).get("status") == "viewed":
            continue
        made = send(op="world-create", principal=owner, identity="mk-kind-" + name, object="kind/" + name, modules=closure("Kind"),
                    entry="initial", seed=record(owner=label(owner), name=label(name), of=label(of), form=label(form), head=label(head),
                                                 law=label(law), body=label(genesis.body_of(body))), law=genesis.KIND_LAW)
        assert made["status"] == "created", made
        shaped = send(op="world-turn", principal=owner, object="kind/" + name, method="shape", argument=record(object=label("kind/" + name)),
                      identity="shape-kind-" + name)
        assert shaped["status"] == "admitted", shaped


def town_garden(send, owner="ember", id="garden", name="THE NIGHT GARDEN"):
    """The garden as genesis makes it (deploy/genesis.py HANDS): kind/bell, kind/cistern and kind/garden as genesis
    makes them, then the owner's `kind/garden make` at an exact id; the body (world/bodies/garden.obend) is laid in the
    settling of that turn. Returns the make's reply."""
    town_kinds(send, owner, names=("bell", "cistern", "garden"))
    made = send(op="world-turn", principal=owner, object="kind/garden", method="make", identity="mk-" + id,
                argument=record(id=label(id), name=label(name)))
    assert made["status"] == "admitted" and made["result"]["label"] == "made", made
    return made


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
        # The chain is wired by subscriptions: the door watches the bell's `rung`, the lantern
        # the door's `open`; each write is delivered to the watcher's `changed`.
        for watcher, obj in (("lantern", "door"), ("door", "bell")):
            w = self.turn(watcher, "watch", record(object=label(obj)))
            self.assertEqual((w["status"], w["result"]), ("admitted", label("watching")), w)
        self.assertEqual(self.turn("door", "watch", record(object=label("bell")))["result"], label("watching"))  # a repeat is idempotent
        ring = self.turn("bell", "ring", principal="gemini")
        self.assertEqual(ring["status"], "admitted", ring)
        self.assertEqual(ring["result"], boolean(True))  # rung; the host tells the subscribers
        self.assertEqual(field(self.state("bell"), "rung"), boolean(True))
        # Deliveries run in the settling pass of the same durable op: the ring's reply carries them.
        self.assertEqual([d["status"] for d in ring["delivered"]], ["admitted", "admitted"], ring)
        self.assertEqual(self.host.send(op="world-pending")["count"], 0)
        self.assertEqual(field(self.state("door"), "open"), boolean(True))
        self.assertEqual(field(self.state("door"), "openedBy"), label("bell"))  # opened by the change, not a turn
        self.assertEqual(field(self.state("lantern"), "lit"), boolean(True))
        self.assertEqual(field(self.state("lantern"), "litBy"), label("door"))
        # The receiver is a helper: no turn may name it, so a forged `changed` opens nothing.
        self.make("door2", closure("Door"), record())
        self.turn("door2", "watch", record(object=label("bell")))
        forged = record(object=reference("bell"), field=label("rung"), version=nat(9), inserted={"tag": "list", "items": [boolean(True)]},
                        retracted={"tag": "list", "items": []})
        refused = self.turn("door2", "changed", forged, principal="gemini")
        self.assertEqual((refused["status"], refused["receipt"]["outcome"]["class"]), ("refused", "noMethod"), refused)
        self.assertEqual(field(self.state("door2"), "open"), boolean(False))

if __name__ == "__main__":
    unittest.main()
