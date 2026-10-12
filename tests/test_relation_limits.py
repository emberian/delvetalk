"""An object whose relations are full, every row at its widest, keeps each cell under
`Bounds.maxCellBytes` (its scalar part and every row, KERNEL-HANDOFF §15 step 4) and still takes a
write.

Evidence for FOUNDATION's scale rule (layer: objects). Refuted by a full object's scalar part past
262,144 canonical bytes, or a write to it refused `capacity`.
"""
import unittest

from deploy import genesis
from tests.test_chain import Chain, town_kinds
from tests.wire import label, nat, record, reference, relation
from tests.bend import MODULES, closure

MAX = 262144
DID = "did:plc:" + "x" * 24


def did(n):
    return "did:plc:%024d" % n


def limit(module, field):
    """The limit a module's relations() declares for `field`."""
    with open(MODULES[module]) as f:
        source = f.read()
    at = source.index('{field: "%s"' % field)
    tail = source[at:]
    return int(tail[tail.index("limit: ") + 7:].split("n", 1)[0])


class FullRelations(Chain):
    def full(self, name, module, seed, by="ember", law=None):
        r = self.host.send(op="world-create", principal=by, identity="mk-" + name, object=name, modules=closure(module), entry="initial", seed=seed, **({"law": law} if law else {}))
        self.assertEqual(r["status"], "created", r)
        size = self.host.send(op="world-inspect", principal=by, object=name, source=False)["scalarBytes"]
        self.assertLess(size, MAX, name)
        return size

    def say(self, obj, text, who, ident):
        r = self.turn(obj, "receive", record(text=label(text), post=label("at://x/" + ident)), principal=who, identity=ident)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_a_bell_full_of_the_longest_rains_takes_another(self):
        n = limit("Bell", "rains")
        rains = [record(author=label(DID), handle=label("h" * 30), verb=label(""), text=label("r" * 120), at=nat(100000), n=nat(i)) for i in range(n)]
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.full("bell", "Bell", record(colour=silver, seed=label("s" * 80), planting=label("at://x/p"), planter=label(DID), planterHandle=label("h" * 30), rains=relation(*rains)))
        self.say("bell", "delvetalk bell rain / text: " + "r" * 120, did(7), "rain")
        refused = self.turn("bell", "receive", record(text=label("delvetalk bell rain / text: " + "r" * 121), post=label("at://x/long")), principal=did(7), identity="long")
        self.assertEqual(refused["receipt"]["outcome"]["class"], "badSpell", refused)

    def test_a_garden_full_of_things_plants_another(self):
        n = limit("Record", "things")
        things = [record(world=label(""), object=label("garden/bell/%d" % (10000 + i))) for i in range(n)]
        self.full("garden", "Record", record(owner=label("ember"), things=relation(*things)), law=genesis.RECORD_LAW)
        body = self.host.send(op="world-reprogram", principal="ember", identity="body-garden", object="garden", version=0,
                              package=genesis.body_of("garden"), mode="extend")
        self.assertEqual(body["status"], "admitted", body)
        town_kinds(self.host.send, names=("bell", "cistern"))
        self.say("garden", "delvetalk garden plant / seed: %s / colour: amber" % ("s" * 80), did(7), "plant")

    def test_a_workshop_full_of_the_largest_held_proposals_is_under_the_bound(self):
        n = limit("Workshop", "held")
        held = [record(n=nat(i + 1), target=label("t" * 128), package=label("p" * 16384), migration=label("m" * 1400), proposer=label(DID), proposerHandle=label("h" * 30), name=label("n" * 32), intent=label("i" * 64)) for i in range(n)]
        self.full("workshop", "Workshop", record(title=label("Workshop"), held=relation(*held), next=nat(n + 1)))

    def test_an_avatar_full_of_the_longest_notes_takes_another(self):
        n = limit("Avatar", "inbox")
        rows = [record(**{"from": label(DID), "handle": label("h" * 30), "text": label("e" * 280), "at": nat(100000), "n": nat(i),
                          "uri": label("at://%s/town.delve.feed.post/%013d" % (DID, i))}) for i in range(n)]
        self.full(DID, "Avatar", record(handle=label("h" * 30), inbox=relation(*rows)), by=DID)
        r = self.say(DID, "x" * 3000, did(7), "mention")
        self.assertEqual(r.get("offers", []), [], r)
        view = self.host.send(op="world-view", principal=DID, object=DID)["state"]
        kept = [f["value"] for f in view["fields"] if f["name"] == "inbox"][0]["payload"]["fields"][0]["value"]["items"][-1]
        self.assertEqual([len(f["value"]["value"]) for f in kept["fields"] if f["name"] == "text"], [280])


if __name__ == "__main__":
    unittest.main()
