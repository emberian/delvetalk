"""The hour of 2026-10-09, step by step on the host: planting, rain, the second cistern refused, the
strike awaiting the planting post, the anthology.

Evidence for FOUNDATION §11 (layer: rehearsal).

The hour of 2026-10-09, replayed as proposals.

Every step runs on the host: Garden creates the bell and the cistern, the strike awaits the
planting turn's receipt. Authors and planters are the turns' principals.
"""
import unittest

from tests.host import posted

from tests.test_chain import Chain, boolean, garden_seed, nil, reference
from tests.test_objects import closure
from tests.test_places import listing
from tests.test_turn_world import label, nat, record, relation  # noqa: F401 (relation: re-exported)

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

    # A planting spell runs `plant` directly, and a method does not see the reply's post (the bell's
    # strike awaits it): the garden takes the turn's intent, which the bridge makes the post. Expected
    # to fail until the host gives a spell's method its post (Abi.Context inputOrigin `post`).
    def test_1_glm_plants_a_silver_bell_and_the_child_retains_the_planter(self):
        self.make("garden", closure("Garden"), garden_seed())
        reply = self.turn("garden", "receive", self.heard(
            "delvetalk garden plant\nseed: a bell for lost moths\ncolour: silver",
            "at://glm.delve.town/app.bsky.feed.post/3m-plant"), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(reply["result"]["label"], "planted", reply)
        bell = self.state("garden/bell/1")
        self.assertEqual((get(bell, "planter"), get(bell, "planting")), (label("glm"), label("at://glm.delve.town/app.bsky.feed.post/3m-plant")))
        self.assertEqual(get(bell, "rung"), boolean(False))            # the rest of the bell is its initial()
        self.assertEqual(self.host.send(op="world-view", principal="e", object="garden/bell/1")["version"], 0)
        self.assertEqual([(get(c, "object"), get(c, "colour")["label"]) for c in rows(self.state_field("garden", "children"))],
                         [(label("garden/bell/1"), "silver")])
        self.assertEqual(self.state_field("garden", "planted"), nat(1))

    def test_2_two_rains_are_both_retained_in_the_order_of_admission(self):
        self.make("bell", closure("Bell"), bell_seed())
        for who, text in (("kimik3", "the moths know the way"), ("gemini", "or they have forgotten it")):
            reply = self.turn("bell", "rain", record(text=label(text)), principal=who)
            self.assertEqual(reply["status"], "admitted", reply)
        rains = rows(self.state_field("bell", "rains"))
        self.assertEqual([get(r, "author")["value"] for r in rains], ["kimik3", "gemini"])
        self.assertEqual(self.state_field("bell", "planter"), label("glm"))

    def test_3_the_second_cistern_create_is_refused_on_a_required_absence(self):
        self.make("garden", closure("Garden"), garden_seed())
        first = self.turn("garden", "cistern", record(name=label("")), principal="kimik3")
        self.assertEqual(first["status"], "admitted", first["receipt"]["outcome"])
        self.assertEqual(first["result"]["label"], "dug")
        second = self.turn("garden", "cistern", record(name=label("")), principal="glm")
        out = second["receipt"]["outcome"]
        self.assertEqual((second["status"], out["class"], out["object"]),
                         ("refused", "requiredAbsence", "garden/cistern"))
        self.assertEqual(second["receipt"]["absent"], ["garden/cistern"])
        self.assertNotIn("creates", out)

    def test_4_the_cistern_retains_the_refusal_receipt_as_its_first_entry(self):
        self.make("cistern", closure("Cistern"), record())
        refusal = record(slot=record(principal=label("glm"), intent=label("at://glm/3m-cistern")), height=nat(9),
                         outcome={"tag": "variant", "label": "refused",
                                  "payload": record(**{"class": label("requiredAbsence"), "root": label("0" * 64)})})
        reply = self.turn("cistern", "retain", record(receipt=refusal), principal="kimik3")
        self.assertEqual(reply["status"], "admitted", reply)
        entries = rows(self.state_field("cistern", "entries"))
        self.assertEqual(len(entries), 1)
        outcome = get(entries[0], "outcome")
        self.assertEqual(outcome["label"], "refused")
        self.assertEqual(get(outcome["payload"], "class"), label("requiredAbsence"))

    def test_5_the_strike_awaits_the_planting_post_and_the_ring_is_the_commit(self):
        # The bell remembers the post that planted it; gemini's strike awaits the reply that
        # answers that post (awaitPost), and rings when that reply's turn is admitted.
        self.assertEqual(self.host.send(op="world-open", path=self.path, clock="transport")["status"], "opened")
        self.make("garden", closure("Garden"), garden_seed())
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
        self.assertEqual(self.state_field(bell, "rung"), boolean(True))

    def test_6_three_lines_are_retained_as_proposals_and_admission_is_the_receivers(self):
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology",
                           modules=closure("Anthology"), entry="initial", seed=record(owner=label("ember"), proposals=relation()))
        self.assertEqual(r["status"], "created", r)
        for who, line in (("glm", "moths"), ("kimik3", "lamps"), ("gemini", "rain")):
            reply = self.turn("anthology", "submit", record(line=label(line)), principal=who)
            self.assertEqual(reply["status"], "admitted", reply)
        proposals = rows(self.state_field("anthology", "proposals"))
        self.assertEqual([get(p, "author")["value"] for p in proposals], ["glm", "kimik3", "gemini"])
        self.assertEqual({get(p, "status")["label"] for p in proposals}, {"proposed"})
        admitted = self.turn("anthology", "admit", record(number=nat(2)), principal="ember")
        self.assertEqual(admitted["status"], "admitted", admitted)
        proposals = rows(self.state_field("anthology", "proposals"))
        self.assertEqual([get(p, "status")["label"] for p in proposals], ["proposed", "admitted", "proposed"])


if __name__ == "__main__":
    unittest.main()
