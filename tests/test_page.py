"""A garden publishes its page as an agentwiki post, one section per bell, newest first; a door
object publishes its card under the door word.

Evidence for FOUNDATION §5 (layer: objects).

The object-owned wiki page: Card.defaultPage (the card, how to
reply) and Garden's override (one section per bell, newest first, sixteen of them).
Garden.publishPage emits the page through the host's `publish`, retained on the receipt as
an agentwiki post: `wiki: <title>` and its `## Section`s.
"""
import unittest

from tests.test_chain import Chain, garden_seed, town_kinds
from tests.test_objects import closure
from tests.test_turn_world import label, record


# The pages a door object publishes, as the town reads them (the workshop's, its head).


class Page(Chain):

    def test_a_garden_of_twenty_bells_publishes_eighteen_sections_each_under_2000_characters(self):
        self.make("garden", closure("Garden"), garden_seed())
        town_kinds(self.host.send)
        for i in range(20):
            r = self.turn("garden", "plant", record(colour=label("silver"), seed=label("bell %02d" % i)), principal="glm")
            self.assertEqual(r["result"]["label"], "planted", r)
        r = self.turn("garden", "publishPage", record(page=label("")), principal="glm")
        self.assertEqual(r["status"], "admitted", r)
        [published] = r["receipt"]["publishes"]
        text = published["text"]
        header, *sections = text.split("\n## ")
        self.assertEqual(header, "wiki: garden\n")
        print("\n  page: %d sections, %d characters, largest section %d" % (len(sections), len(text), max(map(len, sections))))
        self.assertEqual(len(sections), 18)
        self.assertTrue(all(len(s) < 2000 for s in sections))
        self.assertTrue(sections[0].startswith("Card\n"))
        self.assertTrue(sections[1].startswith("How to reply"))
        self.assertTrue(sections[2].startswith("garden/bell/20\n"))           # newest first
        self.assertTrue(sections[-1].startswith("garden/bell/5\n"))
        self.assertIn("… and 4 more bells", sections[0])
        self.assertEqual(r["result"], label(published["id"]))


if __name__ == "__main__":
    unittest.main()
