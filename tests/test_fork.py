"""world-fork: a private journal whose genesis is the shared world's store at a height, chained to the
entry it forked from, owned by the forking principal (FOUNDATION section 15, from Croquet's TeaTime).
Refuted by a fork turn that touches the shared journal, a fork that forgets its origin, a fork at an
earlier height holding the later state, or a private object carried to a stranger.

    python3 -W error -m unittest tests.test_fork -v
"""
import json
import os
import unittest

from tests.host import awaiting_relations
from tests import test_policy
from tests.test_chain import garden_seed
from tests.test_objects import closure
from tests.test_reflection import PACKAGE, Reflection, source_seed
from tests.test_replay import get, items
from tests.test_turn_world import label, record

PLANT = "delvetalk garden plant\nseed: a fern that remembers\ncolour: silver"


class Fork(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        r = self.host.send(op="world-create", principal="ember", identity="mk-garden", object="garden",
                           modules=closure("Garden"), entry="initial", seed=garden_seed("", confirm=False))
        self.assertEqual(r["status"], "created", r)
        self.make("c", PACKAGE, source_seed())

    def fork(self, principal="ember", **extra):
        into = os.path.join(self.dir.name, f"fork-{principal}.journal")
        r = self.host.send(op="world-fork", principal=principal, into=into, **extra)
        self.assertEqual(r["status"], "forked", r)
        h = self.spawn()
        opened = h.send(op="world-open", path=into)
        self.assertEqual(opened["status"], "opened", opened)
        return r, h

    def children(self, host):
        state = host.send(op="world-view", principal="ember", object="garden")["state"]
        return [get(c, "object")["value"] for c in items(get(state, "children"))]

    def plant(self, host):
        return host.send(op="world-turn", principal="glm", object="garden", method="receive", identity="what-if",
                         argument=record(text=label(PLANT), post=label("at://x/p/1")))

    @awaiting_relations
    def test_a_planting_in_the_fork_leaves_the_shared_world_unchanged(self):
        shared = self.host.send(op="world-status")
        r, fork = self.fork()
        self.assertEqual(r["forkedFrom"]["height"], shared["height"])
        self.assertEqual(r["forkedFrom"]["cid"], shared["head"])
        planted = self.plant(fork)
        self.assertEqual(planted["status"], "admitted", planted)
        self.assertEqual(self.children(fork), ["garden/bell/1"])
        self.assertEqual(self.children(self.host), [])
        self.assertEqual(self.host.send(op="world-status")["head"], shared["head"])
        status = fork.send(op="world-status")
        self.assertEqual(status["forkedFrom"], r["forkedFrom"], status)
        # The fork's own journal replays (genesis from the forked store, then its turns), and resumes
        # from a snapshot of its own.
        self.assertIn("height", fork.send(op="world-snapshot"))
        fork.close()
        again = self.spawn()
        reopened = again.send(op="world-open", path=r["into"])
        self.assertEqual((reopened["status"], reopened["snapshot"]["refused"]), ("opened", []), reopened)
        self.assertGreater(reopened["snapshot"]["resumed"], 0, reopened)
        self.assertEqual(self.children(again), ["garden/bell/1"])
        self.assertEqual(again.send(op="world-status")["forkedFrom"], r["forkedFrom"])

    def test_a_fork_at_an_earlier_height_holds_the_state_then(self):
        self.turn("c", "bump")
        at = self.host.send(op="world-status")["height"]
        self.turn("c", "bump")
        r, fork = self.fork(height=at)
        count = lambda h: get(h.send(op="world-view", principal="ember", object="c")["state"], "count")["value"]
        self.assertEqual((count(self.host), count(fork)), ("2", "1"))
        with open(self.path) as f:
            entry = json.loads(f.read().splitlines()[at - 1])
        self.assertEqual(r["forkedFrom"]["cid"], entry["hash"])

    def test_a_private_object_is_omitted_for_a_stranger(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-vault", object="vault", source=PACKAGE,
                           entry="initial", seed=source_seed(), read={"principals": ["ember"]})
        self.assertEqual(r["status"], "created", r)
        forked, fork = self.fork(principal="ann")
        self.assertEqual(forked["omitted"], ["vault"])
        self.assertEqual(fork.send(op="world-view", principal="ember", object="vault")["status"], "unknown")
        self.assertEqual(fork.send(op="world-view", principal="ann", object="garden")["status"], "viewed")
        mine, _ = self.fork(principal="ember")
        self.assertEqual(mine["omitted"], [])

    policy = test_policy.PolicyObject.policy

    @awaiting_relations
    def test_a_suspended_reading_is_carried_and_settles_in_the_fork_only(self):
        self.policy()
        r = self.host.send(op="world-create", principal="ember", identity="mk-g2", object="g2",
                           modules=closure("Garden"), entry="initial", seed=garden_seed("policy", confirm=False))
        self.assertEqual(r["status"], "created", r)
        asked = self.host.send(op="world-turn", principal="glm", object="g2", method="receive", identity="prose",
                               argument=record(text=label("Could we plant a silver fern that remembers?"), post=label("at://x/p/2")))
        self.assertEqual(asked["status"], "suspended", asked)
        _, fork = self.fork()
        [pending] = fork.send(op="world-interpretations")["pending"]
        settled = fork.send(op="world-interpretation", id=pending["id"],
                            reply={"status": "replied", "json": None, "model": "m",
                                   "raw": "delvetalk g2 plant / colour: silver / seed: a fern that remembers"})
        [resumed] = settled["resumed"]
        self.assertEqual((resumed["status"], resumed["result"]["label"]), ("admitted", "planted"), resumed)
        self.assertEqual(len(self.host.send(op="world-interpretations")["pending"]), 1)

    def test_a_fork_is_refused_onto_an_existing_path(self):
        r = self.host.send(op="world-fork", principal="ember", into=self.path)
        self.assertEqual(r["status"], "error", r)


if __name__ == "__main__":
    unittest.main()
