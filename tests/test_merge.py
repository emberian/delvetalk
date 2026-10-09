"""The page's merge (FOUNDATION section 4): the garden's human owner replies `merge` to its posted
page, and receive {text: "merge", post, slot} records that post as pageCheckpoint; the card says
"page checkpointed at <post>". A merge from anyone else, or naming no post, is refused by name and
writes nothing; the Garden's law refuses the same write proposed directly. Card.isMerge and
Card.merge are the default any object with a page uses.

Refuted by: a stranger's merge or forged write moving pageCheckpoint; the owner's not moving it."""
import unittest

from tests import test_chain
from tests.test_chain import garden_seed
from tests.test_objects import closure
from tests.test_turn_world import label, record

PAGE = "at://did:plc:ember/town.delve.feed.post/page1"


def heard(text, post=PAGE):
    return record(text=label(text), post=label(post), slot=label(""))


class Merge(test_chain.Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def setUp(self):
        super().setUp()
        self.make("garden", closure("Garden"), garden_seed())

    def field(self, name):
        return [f["value"]["value"] for f in self.state("garden")["fields"] if f["name"] == name][0]

    def version(self):
        return self.host.send(op="world-view", principal="ember", object="garden")["version"]

    def test_the_owners_merge_checkpoints_the_page(self):
        r = self.turn("garden", "receive", heard("  merge \n"), principal="ember")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "merged"), r)
        self.assertEqual(r["offers"][0]["text"], "Page checkpointed at %s.\n" % PAGE)
        self.assertEqual(self.field("pageCheckpoint"), PAGE)
        card = self.turn("garden", "receive", heard(""), principal="glm")["offers"][0]["text"]
        print("\n--- garden after a merge ---\n" + card)
        self.assertIn("page checkpointed at %s\n" % PAGE, card)

    def test_a_merge_from_anyone_else_or_without_a_post_is_refused_by_name(self):
        r = self.turn("garden", "receive", heard("merge"), principal="glm")
        self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "refused"), r)
        self.assertEqual(r["result"]["payload"]["fields"][0]["value"], label("Only the page's owner, ember, merges it."))
        r = self.turn("garden", "receive", heard("merge", post=""), principal="ember")
        self.assertEqual(r["result"]["payload"]["fields"][0]["value"], label("A merge names the post it answers."))
        self.assertEqual((self.version(), self.field("pageCheckpoint")), (0, ""))
        # "merge" inside prose is prose, not a merge.
        r = self.turn("garden", "receive", heard("merge this please"), principal="ember")
        self.assertNotEqual(r["result"]["label"], "merged")

    def test_the_law_refuses_a_forged_checkpoint(self):
        keep = {"tag": "variant", "label": "keep", "payload": record()}
        r = self.host.send(op="world-propose", principal="glm", identity="forged", roots=[{"object": "garden", "version": 0}],
                           writes=[{"object": "garden", "edits": [record(planted=keep, confirm=keep, pending=keep, children=keep,
                                    pageCheckpoint={"tag": "variant", "label": "set", "payload": record(value=label("at://forged"))})]}])
        self.assertEqual((r["status"], r["receipt"]["outcome"]["class"], r["receipt"]["outcome"].get("clause")),
                         ("refused", "lawRefused", "owner"), r)


if __name__ == "__main__":
    unittest.main()
