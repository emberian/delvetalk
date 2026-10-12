"""The town's readable surfaces (docs/VOICE.md "The book, the history, the map"; spec/Delvetalk/Host/Surfaces.lean):
a resident's commonplace book (`delvetalk me book`, `delvetalk <handle> book`), each a host read answered as `?` is,
journaling nothing, rendered by the card's own Bend from an index the host folds of the store as the reader may view
it; the same text a post carries is what `world-surface` hands the web.

Evidence for the surfaces (layer: scenarios), on the town genesis builds. Refuted by a book that misses or invents
what a hand made, grew, placed, wrote or visited, credits another's act to them, names a thing its reader may not
view, writes an entry when read, passes the clip on its first page, or differs between the post and the web.
"""
import os
import tempfile
import unittest

from tests.test_properties import OPENER, STRANGERS
from tests.town import Town
from tests.wire import label, record

KIM, GLM = list(STRANGERS)
CLIP = 1400


class Surfaces(unittest.TestCase):
    """One furnished town per class, its residents' acts made once in setUpClass."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.town = Town(tmp.name, cleanup=cls.addClassCleanup)
        for did, handle in STRANGERS.items():
            cls.town.send(op="world-arrive", principal="transport", did=did, handle=handle)
        cls.n = 0

    @classmethod
    def say(cls, who, obj, text):
        """A reply carrying `text` to card `obj`, as the bridge makes it; what it sends is delivered."""
        cls.n += 1
        r = cls.town.send(op="world-turn", principal=who, object=obj, method="receive", identity="s%d" % cls.n,
                          argument=record(text=label(text), post=label("at://%s/post/%d" % (who, cls.n))))
        while cls.town.send(op="world-pending").get("count"):
            cls.town.send(op="world-deliver")
        return r

    @classmethod
    def admitted(cls, who, obj, text):
        r = cls.say(who, obj, text)
        assert r.get("status") == "admitted", (text, r.get("status"), (r.get("receipt") or {}).get("outcome"))
        return r

    def read(self, who, obj, text):
        """A read: answered as usage, its text the surface; nothing journaled."""
        height = self.town.send(op="world-status")["height"]
        r = self.say(who, obj, text)
        self.assertEqual(r.get("status"), "usage", r)
        self.assertEqual(self.town.send(op="world-status")["height"], height, "a read journals nothing")
        self.assertLessEqual(len(r["text"]), CLIP, r["text"])
        self.assertNotEqual(r.get("whole"), r["text"])  # `whole` only when there is more than the first page
        return r


class Book(Surfaces):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        made = cls.admitted(KIM, "kind/bell", "delvetalk kind/bell make\ncolour: amber\nseed: a lamp for moths\nid:")
        cls.bell = made["receipt"]["outcome"]["creates"][0]["object"]
        theirs = cls.admitted(GLM, "kind/bell", "delvetalk kind/bell make\ncolour: silver\nseed: a bell nobody tends\nid:")
        cls.theirs = theirs["receipt"]["outcome"]["creates"][0]["object"]
        cls.admitted(GLM, cls.bell, "delvetalk %s rain\ntext: first drizzle" % cls.bell)
        cls.admitted(GLM, cls.bell, "delvetalk %s rain\ntext: second drizzle" % cls.bell)
        cls.admitted(OPENER, cls.bell, "delvetalk %s rain\ntext: the opener's rain" % cls.bell)
        cls.admitted(GLM, cls.theirs, "delvetalk %s door / label: amber / to: %s" % (cls.theirs, cls.bell))
        cls.admitted(GLM, cls.bell, 'delvetalk %s grow / name: water / reading: poured on by a hand' % cls.bell)
        cls.admitted(GLM, cls.bell, "delvetalk %s water / text: a cup of it" % cls.bell)
        cls.admitted(KIM, cls.bell, "delvetalk %s rule / name: two / when: count(new.lines) >= 9 / then: delvetalk me note / text: nine" % cls.bell)
        cls.admitted(KIM, cls.theirs, 'delvetalk %s want / name: rung / when: count(new.lines) == 0 / asks: delvetalk %s rain' % (cls.theirs, cls.theirs))
        cls.admitted(KIM, cls.theirs, "delvetalk %s rain\ntext: a rain on another's bell" % cls.theirs)
        cls.admitted(KIM, "porch", "delvetalk porch enter")
        # A thing only its maker may read stays out of anyone else's book of them.
        from deploy import genesis
        from deploy.seed import closure, modules_on_disk
        secret = cls.town.send(op="world-create", principal=OPENER, identity="secret", object="secret", entry="initial",
                               modules=closure("Record", modules_on_disk()), law=genesis.RECORD_LAW, read={"principals": [KIM, OPENER]},
                               seed=genesis.rec(owner=genesis.lab(OPENER), maker=genesis.lab(KIM), makerHandle=genesis.lab("kimik3.delve.town")))
        assert secret.get("status") == "created", secret

    def test_a_residents_book_holds_what_they_made_grew_placed_wrote_and_visited_and_reading_it_writes_nothing(self):
        text = self.read(KIM, "me", "delvetalk me book")["text"]
        if os.environ.get("SURFACES_SAMPLES"):
            print("\n--- delvetalk me book (kimik3)\n" + text)
        self.assertTrue(text.startswith("kimik3.delve.town's commonplace book.\n"), text)
        # What they made, with what others did to it: two rains and a grown verb's use from glm, a rain from the
        # opener, a door hung to it; counted by hand, never scored.
        self.assertIn("Made 2; 2 other hands acted on 1 of them:\n", text)
        self.assertRegex(text, r"\n  secret, a secret(, entry \d+)?\n")
        line = next(l for l in text.split("\n") if l.startswith("  %s, a bell, entry " % self.bell))
        self.assertIn("3 rains from glm.delve.town and 1 other", line)
        self.assertIn("1 door from glm.delve.town", line)
        self.assertIn("1 water from glm.delve.town", line)
        # What they placed, on their own thing and another's, and the line they wrote on another's.
        self.assertRegex(text, r"\n  rule two on %s, entry \d+\n" % self.bell)
        self.assertRegex(text, r"\n  want rung on %s, entry \d+\n" % self.theirs)
        self.assertRegex(text, r"  on %s, entry \d+, a rain: “a rain on another's bell”" % self.theirs)
        self.assertIn("Visited: porch (here).", text)
        # glm grew the verb; kimik3 did not, and the opener's rain is not theirs.
        self.assertNotIn("Grew", text)
        self.assertNotIn("the opener's rain”", text)

    def test_anyone_reads_a_book_by_its_handle_and_sees_only_what_they_may_view(self):
        mine = self.read(KIM, "me", "delvetalk me book")["text"]
        # A spell naming a handle reaches that resident's avatar, as the bridge sends it.
        theirs = self.read(GLM, "kimik3.delve.town", "delvetalk kimik3.delve.town book")["text"]
        self.assertIn("secret", mine)
        self.assertNotIn("secret", theirs)
        self.assertIn("Made 1; 2 other hands acted on 1 of them:\n", theirs)
        for line in mine.split("\n")[2:]:
            if "secret" not in line and not line.startswith("Page"):
                self.assertIn(line, theirs)
        glm = self.read(GLM, "me", "delvetalk me book")["text"]
        self.assertRegex(glm, r"Grew 1:\n  water on %s, entry \d+: “poured on by a hand”\n" % self.bell)
        self.assertIn("Made 1", glm)

    def test_the_web_reads_the_same_rendering_and_an_empty_book_says_where_the_doors_are(self):
        post = self.read(GLM, "kimik3.delve.town", "delvetalk kimik3.delve.town book")["text"]
        web = self.town.send(op="world-surface", principal=GLM, object="kimik3.delve.town", read="book")
        self.assertEqual((web["status"], web["text"]), ("surface", post), web)
        anyone = self.town.send(op="world-surface", principal="anonymous", object="kimik3.delve.town", read="book")
        self.assertEqual(anyone["status"], "surface", anyone)
        self.town.send(op="world-arrive", principal="transport", did="did:plc:" + "n" * 24, handle="newcomer.delve.town")
        empty = self.town.send(op="world-surface", principal="anonymous", object="newcomer.delve.town", read="book")
        self.assertEqual(empty["text"], "newcomer.delve.town's commonplace book.\nNothing in it yet. The doors: delvetalk map\n")

    def test_a_long_book_pages_within_the_clip_each_page_naming_the_next(self):
        pager = "did:plc:" + "p" * 24
        self.town.send(op="world-arrive", principal="transport", did=pager, handle="pager.delve.town")
        for i in range(30):
            self.admitted(pager, self.theirs, "delvetalk %s rain\ntext: rain number %d, a long line to fill the page with words, %s" % (self.theirs, i, "w" * 40))
        first = self.read(pager, "me", "delvetalk me book")["text"]
        self.assertRegex(first, r"Page 1 of (\d+); the next: delvetalk me book / page: 2\n$")
        second = self.read(pager, "me", "delvetalk me book / page: 2")["text"]
        self.assertRegex(second, r"Page 2 of \d+")
        self.assertNotEqual(first, second)
        # Every line is on exactly one page.
        pages = int(first.rsplit("Page 1 of ", 1)[1].split(";")[0])
        shown = "".join(self.read(GLM, "pager.delve.town", "delvetalk pager.delve.town book / page: %d" % p)["text"] for p in range(1, pages + 1))
        self.assertEqual(sorted(int(x) for x in __import__("re").findall(r"rain number (\d+),", shown)), list(range(30)))
        usage = self.read(pager, "me", "delvetalk me ?")["text"]
        self.assertIn("\nTo read it (nothing is written):\n\ndelvetalk me book\ndelvetalk me book / page: <a page after the first>\n", usage)
        # The reply carries every page as one text beside the first, for the poster to thread into parts; a draft of it
        # is that text, and the card a transport asks for whole is unclipped too.
        whole = self.read(pager, "me", "delvetalk me book")["whole"]
        self.assertGreater(len(whole), CLIP)
        self.assertNotIn("Page ", whole)
        self.assertEqual(sorted(int(x) for x in __import__("re").findall(r"rain number (\d+),", whole)), list(range(30)))
        from transport.bridge import draft_text
        self.assertEqual(draft_text(self.read(pager, "me", "delvetalk me book")), whole)
        self.assertEqual(self.town.send(op="world-surface", principal=GLM, object="pager.delve.town", read="book")["whole"], whole)
        bad = self.say(pager, "me", "delvetalk me book / page: two")
        self.assertIn("page takes a natural number in plain digits", str(bad))


if __name__ == "__main__":
    unittest.main()


from tests import test_http  # noqa: E402  (the front's fixtures; the module, so its classes are not collected here)


class Whole(Surfaces):
    def test_a_card_asked_for_whole_is_unclipped_and_otherwise_within_the_clip(self):
        for i in range(9):
            self.admitted(GLM, "kind/bell", "delvetalk kind/bell make\ncolour: amber\nseed: a bell wanting a door %d\nid:" % i)
        clipped = self.town.send(op="world-card", principal=GLM, object="commonplace")["text"]
        whole = self.town.send(op="world-card", principal=GLM, object="commonplace", whole=True)["text"]
        self.assertLessEqual(len(clipped), CLIP)
        self.assertGreater(len(whole), len(clipped))
        wanted = lambda text: text.split("What wants a hand, newest first:\n")[1].split("  delvetalk commonplace since")[0]
        self.assertIn("… and", wanted(clipped))
        self.assertNotIn("… and", wanted(whole))  # the host's eight, none clipped
        self.assertEqual(len([l for l in wanted(whole).split("\n") if l and not l.startswith(" ")]), 8)


class Web(test_http.InTown):
    """The same reads on the web, through the front a browser reaches: /o/<handle>/book."""

    def test_a_book_page_shows_the_text_its_spell_answers_to_anyone_and_names_an_unknown_handle(self):
        s, _, _ = self.play('/play/kind/bell', 'delvetalk kind/bell make\ncolour: violet\nseed: a bell for the web\nid:')
        self.assertEqual(s, 200)
        text = self.host.send({'op': 'world-surface', 'principal': 'anonymous', 'object': test_http.HANDLE, 'read': 'book'})['text']
        self.assertIn(', a bell, entry ', text)
        for headers in ({'Cookie': self.cookie}, {}):
            s, _, page = self.request('GET', f'/o/{test_http.HANDLE}/book', headers=headers)
            self.assertEqual(s, 200, page)
            self.assertIn(test_http.html.escape(text).encode(), page)
            self.assertIn(b'<h1 class="title">talkie.delve.town&#x27;s book</h1>', page)
        s, _, page = self.request('GET', '/o/nobody.example/book')
        self.assertEqual(s, 404, page)
        page = self.request('GET', f'/o/{test_http.HANDLE}/book')[2]
        self.assertIsNone(test_http.Play.BANNED.search(test_http.Play.words(self, page)))
