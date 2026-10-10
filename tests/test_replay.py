"""The hour of 2026-10-09, step by step on the host: planting, rain, the second cistern refused, the
strike awaiting the planting post, the anthology.

Evidence for FOUNDATION §11 (layer: rehearsal).

The hour of 2026-10-09, replayed as proposals.

Every step runs on the host: Garden creates the bell and the cistern, the strike awaits the
planting turn's receipt. Authors and planters are the turns' principals.
"""
import unittest

from tests.host import posted

from tests.test_chain import Chain, garden_seed, town_kinds
from tests.test_objects import closure
from tests.test_turn_world import label, record, relation  # noqa: F401 (relation: re-exported)

PLANTING = "at://glm.delve.town/app.bsky.feed.post/3m-plant"


def silver():
    return {"tag": "variant", "label": "silver", "payload": record()}


def bell_seed():
    """A Bell Seed: the planting post and its planter."""
    return record(colour=silver(), seed=label("a bell for lost moths"), planting=label(PLANTING), planter=label("glm"), planterHandle=label(""))


def items(wire):
    return wire["items"]


def rows(wire):
    """The rows of a relation on the wire (`Relation.rows {items}`), in key order."""
    assert wire["tag"] == "variant" and wire["label"] == "rows", wire
    return get(wire["payload"], "items")["items"]


def get(record_wire, name):
    return [f["value"] for f in record_wire["fields"] if f["name"] == name][0]


class Replay(Chain):
    def heard(self, text, post):
        return record(text=label(text), post=label(post))

    def state_field(self, obj, name):
        return get(self.state(obj), name)


    def test_5_the_strike_awaits_the_planting_post_and_the_ring_is_the_commit(self):
        # The bell remembers the post that planted it; gemini's strike awaits the reply that
        # answers that post (awaitPost), and rings when that reply's turn is admitted.
        self.assertEqual(self.host.send(op="world-open", path=self.path, clock="transport")["status"], "opened")
        self.make("garden", closure("Garden"), garden_seed())
        town_kinds(self.host.send)
        planted = self.turn("garden", "receive", self.heard(
            "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver", PLANTING), principal="glm", identity=PLANTING)
        self.assertEqual(planted["status"], "admitted", planted)
        bell = "garden/bell/1"
        waiting = self.turn(bell, "strike", principal="gemini")
        self.assertEqual((waiting["status"], waiting["receipt"]["outcome"]["post"]), ("suspended", PLANTING), waiting)
        self.assertEqual(posted(self.host, principal="transport", uri=PLANTING, cid="c", object="garden")["status"], "posted")
        answer = self.host.send(op="world-turn", principal="kimik3", object="garden", method="receive",
                                argument=self.heard("", PLANTING + "/r1"), identity=PLANTING + "/r1", replyTo=PLANTING)
        self.assertEqual((answer["status"], answer["receipt"]["replyTo"]), ("admitted", PLANTING), answer)
        self.assertEqual([r["status"] for r in answer["resumed"]], ["admitted"], answer)
        self.assertEqual([get(m, "name") for m in rows(self.state_field(bell, "marks"))], [label("rung")])


if __name__ == "__main__":
    unittest.main()
