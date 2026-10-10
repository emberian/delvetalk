"""textHasAny finds whole words in one pass, its tariff linear in the text and the word list.

Evidence for FOUNDATION §1 (layer: kernel).

`textHasAny(text, words)`: whether any of the words is a whole word of the text (words
are maximal runs of ASCII letters, digits and non-ASCII scalars; ASCII letters compare
lowercased). One pass over each text: its tariff is linear in the text plus the word list,
where walking the text through Bend list functions cost about 200,000 ticks for an
1,800-character reply.

    python3 -m unittest tests.test_text_words -v
"""
import time
import unittest

from tests.test_turn import Host, label, library_modules

SOURCE = """edition ObjectiveBend 1
import ./List.obend as Lists
def names() -> Lists.List<String>:
  Lists.List.cons({head: "hello", tail: Lists.List.cons({head: "Directory", tail: Lists.List.cons({head: "porch", tail: Lists.List.cons({head: "lantern", tail: Lists.List.cons({head: "bell", tail: Lists.List.cons({head: "garden", tail: Lists.List.cons({head: "moth", tail: Lists.List.cons({head: "tide", tail: Lists.List.cons({head: "wake", tail: Lists.List.cons({head: "café", tail: Lists.List.nil({})})})})})})})})})})})
def check(text: String) -> Bool:
  textHasAny(text, names())
"""


class TextHasAny(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()
        reply = cls.h.send({"op": "compile", "entry": "check",
                            "modules": library_modules("List") + [{"name": "Package", "source": SOURCE}]})
        assert reply["status"] == "compiled", reply
        cls.art = reply["artifact"]

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def check(self, text):
        reply = self.h.send({"op": "run", "artifact": self.art, "arguments": [label(text)]})
        self.assertEqual(reply["status"], "finished", reply)
        return reply["value"]["value"], reply["ticksUsed"]

    def test_whole_words_case_folded_punctuation_separates(self):
        self.assertTrue(self.check("Hello, town!")[0])
        self.assertTrue(self.check("to the DIRECTORY.")[0])
        self.assertTrue(self.check("un café?")[0])
        self.assertFalse(self.check("bells and gardens")[0])  # whole words only
        self.assertFalse(self.check("")[0])
        self.assertTrue(self.check("the-moth-said")[0])

    def test_a_long_reply_is_checked_in_under_ten_thousand_ticks(self):
        reply = ("I keep thinking about the lighthouse and whether anyone hears the sea at night. " * 22)[:1800]
        found, ticks = self.check(reply)
        self.assertFalse(found)
        self.assertLess(ticks, 10000, ticks)
        found, ticks = self.check(reply[:-10] + " lantern.")
        self.assertTrue(found)
        self.assertLess(ticks, 10000, ticks)


MANY = """edition ObjectiveBend 1
import ./List.obend as Lists
def many(text: String, words: String) -> Bool:
  textHasAny(text, Lists.List.cons({head: words, tail: Lists.List.nil({})}))
"""


class ManyWords(unittest.TestCase):
    def test_many_words_against_many_words_is_linear_work(self):
        # Refuted by list membership per text word: 30,000 `a` words against 30,000 `b`
        # words is 900 million failed comparisons (seconds) under a tariff of 240,001 ticks.
        h = Host()
        self.addCleanup(h.close)
        reply = h.send({"op": "compile", "entry": "many",
                        "modules": library_modules("List") + [{"name": "Package", "source": MANY}]})
        self.assertEqual(reply["status"], "compiled", reply)
        art = reply["artifact"]
        n = 30000
        walls = []
        for text, words in (("a " * n, "b " * n), ("a " * n + "b", "b " * n)):
            began = time.monotonic()
            ran = h.send({"op": "run", "artifact": art, "arguments": [label(text), label(words)],
                          "limits": {"ticks": "1000000"}})
            walls.append(time.monotonic() - began)
            self.assertEqual(ran["status"], "finished", ran)
        self.assertEqual(ran["value"]["value"], True)
        print("\n  textHasAny, 30,000 words against 30,000: %.3f s, %.3f s" % tuple(walls))
        self.assertLess(max(walls), 0.5, walls)


if __name__ == "__main__":
    unittest.main()
