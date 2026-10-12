"""The world explains its own kinds: every kind carries one plain line of what it is and does over time (KIND `about`),
its card leads with it, the kinds card lists every kind with it, and the library's `kinds` page gives one spell that
makes each, every one of which a resident can cast on a bare town as written. hob's examples answer "what is a
front?" with that page.

Evidence for docs/GENESIS.md "What genesis makes" and docs/LIBRARY.md (layer: scenarios).
"""
import re
import tempfile
import unittest
from pathlib import Path

from deploy import genesis
from tests.host import card_texts
from tests.town import Town
from tests.wire import label, record

ROOT = Path(__file__).resolve().parent.parent
STRANGER = "did:plc:stranger"


class Explained(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.town.send(op="world-arrive", principal="transport", did=STRANGER, handle="stranger.delve.town")
        cls.n = 0

    def say(self, obj, text):
        type(self).n += 1
        return self.town.send(op="world-turn", principal=STRANGER, object=obj, method="receive", identity="x%d" % self.n,
                              argument=record(text=label(text), post=label("")))

    def card(self, obj):
        return self.town.send(op="world-card", principal=STRANGER, object=obj)["text"]

    def test_every_kinds_card_leads_with_what_it_is(self):
        for name, about in genesis.ABOUT.items():
            with self.subTest(kind=name):
                self.assertTrue(self.card("kind/" + name).startswith(about + "\nKIND %s: " % name), self.card("kind/" + name))
        self.assertTrue(self.card("kinds").startswith(genesis.KINDS_ABOUT + "\n"))

    def test_the_kinds_card_lists_every_kind_with_its_line(self):
        card = self.card("kinds")
        self.assertLessEqual(len(card), 1400)
        for name, about in genesis.ABOUT.items():
            self.assertIn("- kind/%s: %s\n" % (name, about), card)

    def test_the_kinds_page_is_within_the_clip_and_each_of_its_spells_makes_one(self):
        page = (ROOT / "capsules" / "pages" / "kinds.txt").read_text()
        self.assertLessEqual(len(page), 1266)
        spells = [line[2:] for line in page.split("\n") if line.startswith("  delvetalk ")]
        self.assertEqual(sorted(re.match(r"delvetalk kind/(\w+) make", s).group(1) for s in spells),
                         sorted(n for n in genesis.ABOUT if n != "porch"))
        for spell in spells:
            with self.subTest(spell=spell):
                made = self.say(spell.split()[1], spell)
                self.assertEqual(made["status"], "admitted", made)
        read = self.say("library", "delvetalk library read / page: kinds")
        self.assertIn("front: a clock that fills", "\n".join(card_texts(read)))

    def test_hob_answers_what_a_front_is_with_the_kinds_page(self):
        self.assertIn(("what is a front?", "delvetalk library read / page: kinds"), genesis.EXAMPLES)


if __name__ == "__main__":
    unittest.main()
