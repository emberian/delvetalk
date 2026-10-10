"""The object-owned wiki page (FOUNDATION section 4): Card.defaultPage (the card, how to
reply) and Garden's override (one section per bell, newest first, sixteen of them).
Garden.publish emits the page through the host's `publish`, retained on the receipt as
an agentwiki post: `wiki: <title>` and its `## Section`s."""
import unittest

from tests.test_chain import Chain, garden_seed
from tests.test_objects import closure
from tests.test_turn_world import label, record


class Page(Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def test_a_garden_of_twenty_bells_publishes_eighteen_sections_each_under_2000_characters(self):
        self.make("garden", closure("Garden"), garden_seed())
        for i in range(20):
            r = self.turn("garden", "plant", record(colour=label("silver"), seed=label("bell %02d" % i)), principal="glm")
            self.assertEqual(r["result"]["label"], "planted", r)
        r = self.turn("garden", "publish", principal="glm")
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

    def test_publish_page_posts_the_card_under_the_door_word_and_the_host_lists_it(self):
        """Genesis posts one card per door: publishPage titles the page by door().word."""
        self.make("plot", closure("Garden"), garden_seed())
        r = self.turn("plot", "publishPage", principal="ember")
        self.assertEqual(r["status"], "admitted", r)
        [published] = r["receipt"]["publishes"]
        self.assertTrue(published["text"].startswith("wiki: garden\n"), published["text"][:80])
        self.assertIn("    delvetalk plot plant\n", published["text"])
        listed = self.host.send(op="world-publications", principal="transport")
        self.assertEqual(listed["status"], "publications", listed)
        self.assertEqual([(p["object"], p["page"]) for p in listed["publications"]], [("plot", "garden")])
        for obj, module, seed in (("rooms", "Scene", record(title=label("The Moss Gate"))), ("workshop", "Workshop", record(title=label("Workshop")))):
            made = self.host.send(op="world-create", principal="ember", identity="mk-" + obj, object=obj, modules=closure(module), entry="initial", seed=seed)
            self.assertEqual(made["status"], "created", made)
            r = self.turn(obj, "publishPage", principal="ember")
            self.assertEqual(r["status"], "admitted", r)
            [published] = r["receipt"]["publishes"]
            print("\n--- %s page ---\n%s" % (obj, published["text"][:300]))
            self.assertTrue(published["text"].startswith("wiki: %s\n" % ("scene" if module == "Scene" else "workshop")), published["text"][:80])


if __name__ == "__main__":
    unittest.main()
