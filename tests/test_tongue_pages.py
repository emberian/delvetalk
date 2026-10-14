"""A resident states a tongue and the library reads its pages in it (docs/VOICE.md; Library.obend `read`).

Evidence for the tongues lane (layer: objects).

Refuted by: `tongue` set by a stranger or not held in the avatar's state, a reader with a tongue given the English
guide or welcome, a reader with none given a translation, a translation listed on the index or the shelf line, a page
over a reply's room, or a politeness word in any language on any page.
"""
import tempfile
import unittest

from deploy import genesis
from tests.host import card_texts
from tests.town import Town
from tests.wire import cast_refusal, label, record

JA, STRANGER, MUTE, OWN = "did:plc:ja", "did:plc:stranger", "did:plc:mute", "did:plc:own"
LIMIT = 1266
POLITE = ("ありがとう", "ようこそ", "ください", "どうぞ", "谢谢", "欢迎", "请", "gracias", "bienvenid", "por favor", "спасибо",
          "добро пожаловать", "пожалуйста", "شكرا", "مرحبا", "أهلا", "من فضلك", "thank", "sorry", "welcome ", "please", "great")
TONGUES = ("ja", "zh", "es", "ru", "ar")


class Tongues(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup, furnished=False)
        cls.host = cls.town.client
        cls.n = 0
        for did, handle in ((JA, "ja.test"), (STRANGER, "stranger.test"), (MUTE, "mute.test"), (OWN, "own.test")):
            got = cls.host.send({"op": "world-arrive", "principal": "transport", "did": did, "handle": handle})
            assert got["status"] == "arrived", got

    def turn(self, who, obj, text):
        type(self).n += 1
        return self.host.send({"op": "world-turn", "principal": who, "object": obj, "method": "receive", "identity": "tongue-%d" % self.n,
                               "argument": record(text=label(text), post=label("at://x/tongue-%d" % self.n))})

    def read(self, who, page):
        got = self.turn(who, "library", "delvetalk library read / page: %s" % page)
        self.assertEqual(got["status"], "admitted", got)
        return "".join(o["text"] for o in got["offers"])

    def tongue(self, who):
        got = self.host.send({"op": "world-view", "principal": who, "object": who})
        return [f["value"]["value"] for f in got["state"]["fields"] if f["name"] == "tongue"][0]

    def test_a_tongue_is_the_principals_to_state_and_a_stranger_cannot_state_it(self):
        self.assertEqual(self.tongue(OWN), "")
        refused = self.turn(STRANGER, OWN, "delvetalk %s set / tongue: ja" % OWN)
        self.assertEqual(refused["status"], "refused", refused)
        self.assertEqual(self.tongue(OWN), "")
        got = self.turn(OWN, OWN, "delvetalk me set / tongue: ja")
        self.assertEqual(got["status"], "admitted", got)
        self.assertEqual("".join(o["text"] for o in got["offers"]), "Set tongue to ja.\n")
        self.assertEqual(self.tongue(OWN), "ja")
        self.assertIn(self.turn(OWN, OWN, "delvetalk me set / tongue: fr")["status"], ("refused", "suspended"))  # not a tongue the town speaks

    def test_a_reader_with_a_tongue_is_read_its_pages_and_one_with_none_the_english(self):
        self.turn(JA, JA, "delvetalk me set / tongue: ja")
        pages = {name: body for name, _, _, body in genesis.shelf()}
        for page in ("guide", "welcome"):
            self.assertEqual(self.read(JA, page), pages[page + ".ja"], page)
            self.assertEqual(self.read(MUTE, page), pages[page], page)
            self.assertEqual(self.read(STRANGER, page), pages[page], page)
        guided = self.turn(JA, "library", "delvetalk guide")  # the guide's own door reads the same page
        self.assertEqual("".join(o["text"] for o in guided["offers"]), pages["guide.ja"], guided)
        self.assertEqual(self.read(JA, "guide-1"), pages["guide-1"])  # a part with no translation is read as shelved
        self.assertEqual(self.read(JA, "laws"), pages["laws"])
        self.assertEqual(self.read(JA, "welcome.zh"), pages["welcome.zh"])  # a page asked by its whole name
        self.turn(JA, JA, "delvetalk me set / tongue: en")
        self.assertEqual(self.read(JA, "welcome"), pages["welcome"])
        self.turn(JA, JA, "delvetalk me set / tongue: ja")

    def test_a_translation_is_left_off_the_index_and_the_shelf_line(self):
        index = "".join(card_texts(self.host.send({"op": "world-card", "principal": MUTE, "object": "library"})))
        self.assertIn("welcome", index)
        miss = self.turn(MUTE, "library", "delvetalk library read / page: dragons")
        line = miss["receipt"]["outcome"]["reason"]
        self.assertIn("welcome", line)
        for text in (index, line):
            for tongue in TONGUES:
                self.assertNotIn("guide." + tongue, text)
                self.assertNotIn("welcome." + tongue, text)

    def test_every_page_fits_a_reply_and_none_in_any_language_is_polite(self):
        shelf = genesis.shelf()
        self.assertLessEqual(len(shelf), 49)
        for name, _, _, body in shelf:
            with self.subTest(page=name):
                self.assertLessEqual(len(body), LIMIT)
                self.assertTrue(body.startswith("hob: "), body[:20])
                for word in POLITE:
                    self.assertNotIn(word, body.lower(), name)
        names = {name for name, _, _, _ in shelf}
        for tongue in TONGUES:
            self.assertIn("guide." + tongue, names)
            self.assertIn("welcome." + tongue, names)

    def test_a_translation_keeps_every_spell_byte_for_byte(self):
        pages = {name: body for name, _, _, body in genesis.shelf()}
        for tongue in TONGUES:
            for page in ("guide", "welcome"):
                spells = [line[line.index("delvetalk "):] for line in pages[page].splitlines() if "delvetalk " in line]
                for spell in spells:
                    self.assertIn(spell, pages[page + "." + tongue], (page, tongue))
