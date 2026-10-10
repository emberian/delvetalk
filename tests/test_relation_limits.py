"""Every relation's declared limit times its widest row fits in 256 KiB (HOST-HANDOFF 108): an object
whose relation is full, every row at its widest, is under `maxStateBytes` and still takes a write.

Evidence for FOUNDATION's scale rule (layer: objects). Refuted by a full relation past 262,144
canonical bytes, or a write to it refused `capacity`.
"""
import os
import unittest

from tests.test_chain import Chain, reference
from tests.test_objects import closure
from tests.test_turn_world import label, nat, record, relation

MAX = 262144
DID = "did:plc:" + "x" * 24


def did(n):
    return "did:plc:%024d" % n


def lst(*items):
    return {"tag": "list", "items": list(items)}


def limit(module, field):
    """The limit a module's relations() declares for `field`."""
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "world", "objects", module + ".obend")) as f:
        source = f.read()
    at = source.index('{field: "%s"' % field)
    tail = source[at:]
    return int(tail[tail.index("limit: ") + 7:].split("n", 1)[0])


class FullRelations(Chain):
    def full(self, name, module, seed, by="ember"):
        r = self.host.send(op="world-create", principal=by, identity="mk-" + name, object=name, modules=closure(module), entry="initial", seed=seed)
        self.assertEqual(r["status"], "created", r)
        size = self.host.send(op="world-inspect", principal=by, object=name, source=False)["stateBytes"]
        print("\n  %s full: %d bytes" % (name, size))
        self.assertLess(size, MAX, name)
        return size

    def say(self, obj, text, who, ident):
        r = self.turn(obj, "receive", record(text=label(text), post=label("at://x/" + ident)), principal=who, identity=ident)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_a_bell_full_of_the_longest_rains_takes_another(self):
        n = limit("Bell", "rains")
        rains = [record(author=label(DID), handle=label("h" * 30), text=label("r" * 120), at=nat(100000), n=nat(i)) for i in range(n)]
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        self.full("bell", "Bell", record(colour=silver, seed=label("s" * 80), planting=label("at://x/p"), planter=label(DID), planterHandle=label("h" * 30), rains=relation(*rains)))
        self.say("bell", "delvetalk bell rain / text: " + "r" * 120, did(7), "rain")
        refused = self.turn("bell", "receive", record(text=label("delvetalk bell rain / text: " + "r" * 121), post=label("at://x/long")), principal=did(7), identity="long")
        self.assertEqual(refused["receipt"]["outcome"]["class"], "badSpell", refused)

    def test_a_garden_full_of_children_plants_another(self):
        n = limit("Garden", "children")
        silver = {"tag": "variant", "label": "silver", "payload": record()}
        children = [record(world=label(""), object=label("garden/bell/%d" % (10000 + i)), colour=silver) for i in range(n)]
        self.full("garden", "Garden", record(owner=label("ember"), policy=reference(""), children=relation(*children), planted=nat(n)))
        self.say("garden", "delvetalk garden plant / seed: %s / colour: amber" % ("s" * 80), did(7), "plant")

    def test_a_directory_full_of_greetings_greets_another(self):
        n = limit("Directory", "greeted")
        greeted = [record(principal=label(did(i))) for i in range(n)]
        self.full("directory", "Directory", record(owner=label("ember"), greeted=relation(*greeted)))
        self.assertEqual(self.say("directory", "hello", did(n + 1), "hello")["result"]["label"], "menu")

    def test_a_workshop_full_of_the_largest_held_proposals_is_under_the_bound(self):
        n = limit("Workshop", "held")
        held = [record(n=nat(i + 1), target=label("t" * 128), package=label("p" * 16384), migration=label("m" * 1400), proposer=label(DID), proposerHandle=label("h" * 30)) for i in range(n)]
        self.full("workshop", "Workshop", record(title=label("Workshop"), held=relation(*held), next=nat(n + 1)))

    def test_an_env_full_of_the_longest_events_takes_another(self):
        n = limit("Env", "buffer")
        rows = [record(kind=label("mention"), actor=label(DID), handle=label("h" * 30), uri=label("at://%s/town.delve.feed.post/%013d" % (DID, i)),
                       cid=label("b" * 59), text=label("e" * 280), replyTo=label("at://%s/town.delve.feed.post/%013d" % (DID, i)), at=nat(100000), n=nat(i)) for i in range(n)]
        owner = DID
        self.full("env/" + owner, "Env", record(owner=label(owner), handle=label("h"), buffer=relation(*rows)), by=owner)
        r = self.say("env/" + owner, "x" * 3000, did(7), "mention")
        self.assertEqual(r["result"]["label"], "done", r)
        view = self.host.send(op="world-view", principal=owner, object="env/" + owner)["state"]
        kept = [f["value"] for f in view["fields"] if f["name"] == "buffer"][0]["payload"]["fields"][0]["value"]["items"][-1]
        self.assertEqual([len(f["value"]["value"]) for f in kept["fields"] if f["name"] == "text"], [280])


if __name__ == "__main__":
    unittest.main()
