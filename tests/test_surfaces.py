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
    def say(cls, who, obj, text, author=None):
        """A reply carrying `text` to card `obj`, as the bridge makes it (`author` the post's, when it answers another's);
        what it sends is delivered."""
        cls.n += 1
        r = cls.town.send(op="world-turn", principal=who, object=obj, method="receive", identity="s%d" % cls.n,
                          argument=record(text=label(text), post=label("at://%s/post/%d" % (author or who, cls.n))))
        while cls.town.send(op="world-pending").get("count"):
            cls.town.send(op="world-deliver")
        return r

    @classmethod
    def admitted(cls, who, obj, text, author=None):
        r = cls.say(who, obj, text, author)
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
        # A thing made after another's post credits its coiner where its maker's book lists it.
        coined = self.admitted(GLM, "kind/bell", "delvetalk kind/bell make\ncolour: violet\nseed: kimik3's word\nid:", author=KIM)
        bell = coined["receipt"]["outcome"]["creates"][0]["object"]
        self.assertRegex(self.town.send(op="world-surface", principal=GLM, object="me", read="book")["text"],
                         r"\n  %s, a bell, coined by kimik3\.delve\.town, entry \d+\n" % bell)

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
        # The caller's reply carries every page beside the first; the web can read the same whole text.
        whole = self.read(pager, "me", "delvetalk me book")["whole"]
        self.assertGreater(len(whole), CLIP)
        self.assertNotIn("Page ", whole)
        self.assertEqual(sorted(int(x) for x in __import__("re").findall(r"rain number (\d+),", whole)), list(range(30)))
        from transport.bridge import draft_text, read_text
        from transport.host import typed
        reply = self.read(pager, "me", "delvetalk me book")
        self.assertEqual(read_text(self.town.client, pager, reply), whole)
        request = {'op': 'world-turn', 'principal': pager, 'object': 'pager.delve.town', 'method': 'receive', 'identity': 'public-pager-book',
                   'argument': typed({'text': 'delvetalk pager.delve.town book', 'post': ''})}
        self.assertEqual(draft_text(reply, host=self.town.client, request=request), whole)
        self.assertEqual(self.town.send(op="world-surface", principal=GLM, object="pager.delve.town", read="book")["whole"], whole)
        bad = self.say(pager, "me", "delvetalk me book / page: two")
        self.assertIn("page takes a natural number in plain digits", str(bad))


if __name__ == "__main__":
    unittest.main()


from tests import test_http  # noqa: E402  (the front's fixtures; the module, so its classes are not collected here)


class History(Surfaces):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A day of its own, so the day's lines are these acts' (genesis fills the first).
        clock = cls.town.send(op="world-status")["clock"]
        assert cls.town.send(op="world-advance", principal="transport", height=(clock // 1440 + 1) * 1440 + 5)["status"] == "advanced"
        # glm makes a bell after kimik3's post (a coinage), rains on it first, grows a verb, and a rule of kimik3's fires.
        made = cls.admitted(GLM, "kind/bell", "delvetalk kind/bell make\ncolour: violet\nseed: kimik3's bell\nid:", author=KIM)
        cls.bell = made["receipt"]["outcome"]["creates"][0]["object"]
        cls.admitted(KIM, cls.bell, "delvetalk %s rule / name: echo / when: count(new.lines) >= 2 / then: delvetalk me note / text: two" % cls.bell)
        cls.admitted(GLM, cls.bell, "delvetalk %s rain\ntext: the first rain" % cls.bell)
        cls.admitted(GLM, cls.bell, 'delvetalk %s grow / name: water / reading: poured on' % cls.bell)
        cls.admitted(GLM, cls.bell, "delvetalk %s water / text: a second line" % cls.bell)
        cls.day = cls.town.send(op="world-status")["clock"] // 1440

    def test_the_days_history_holds_its_exact_lines_credits_the_coiner_and_the_firsts_and_names_its_paint(self):
        r = self.read(GLM, "commonplace", "delvetalk chronicle")
        text = r["text"]
        if os.environ.get("SURFACES_SAMPLES"):
            print("\n--- delvetalk chronicle\n" + text)
        self.assertTrue(text.startswith("THE TOWN'S HISTORY · day %d, " % self.day), text)
        self.assertEqual(r["paint"], {"day": self.day})  # the day's paint stands above it where a transport paints
        lines = self.town.send(op="world-chronicle", principal=GLM, day=self.day)["lines"]
        made = next(l for l in lines if l.startswith("made %s " % self.bell))
        self.assertTrue(made.endswith(", coined by kimik3.delve.town"), made)
        self.assertIn("Firsts:\n", r.get("whole") or text)
        whole = r.get("whole") or text
        self.assertRegex(whole, r"  the first rain: glm\.delve\.town on %s, entry \d+\n" % self.bell)
        self.assertRegex(whole, r"  the first grown verb: water on %s, grown by glm\.delve\.town, entry \d+\n" % self.bell)
        self.assertRegex(whole, r"  the first rule fired: echo on %s, written by kimik3\.delve\.town, entry \d+\n" % self.bell)
        # Genesis made the porch after gemini's post, whose handle this town's registry lacks: the post is the name.
        self.assertRegex(whole, r"  the first coinage: porch, coined by the author of at://did:plc:\w+/town\.delve\.feed\.post/\w+, entry \d+\n")
        self.assertRegex(whole, r"  the first room: porch, made by the town, entry \d+\n")
        self.assertNotRegex(whole, r"(?<!at://)did:plc:")
        for line in lines[:3]:
            self.assertIn(line + "\n", whole)
        # The same text by day, on the web's way, and within a reply with the paint's room left.
        self.assertEqual(self.read(GLM, "commonplace", "delvetalk chronicle / day: %d" % self.day)["text"], text)
        self.assertEqual(self.town.send(op="world-surface", principal=GLM, read="chronicle", fields={"day": str(self.day)})["text"], text)
        self.assertLessEqual(len(text), CLIP - 600)

    def test_a_range_threads_a_day_a_page_each_naming_the_next(self):
        first = self.read(GLM, "commonplace", "delvetalk chronicle / from: %d / to: %d" % (self.day, self.day + 1))
        whole = first.get("whole") or first["text"]
        self.assertIn(", 1 of 2 days\n", first["text"])
        self.assertTrue(whole.endswith("The next day: delvetalk chronicle / from: %d / to: %d\n" % (self.day + 1, self.day + 1)), whole)
        nxt = self.read(GLM, "bell/1", "delvetalk chronicle / from: %d / to: %d" % (self.day + 1, self.day + 1))["text"]
        self.assertIn("day %d: nothing was journaled.\n" % (self.day + 1), nxt)
        self.assertNotIn("The next day", nxt)

    def test_a_callers_history_carries_the_days_verified_paint_above_its_exact_lines(self):
        from transport.bridge import read_text
        r = self.read(GLM, "commonplace", "delvetalk chronicle")
        asked = []

        class Host:
            def send(self, req):
                asked.append(req)
                return {"status": "painted", "text": "The town woke to one rain."}
        self.assertEqual(read_text(Host(), GLM, r), "The town woke to one rain.\n\n" + (r.get("whole") or r["text"]))
        self.assertEqual((asked[0]["op"], asked[0]["day"]), ("world-render", self.day))
        self.assertEqual(read_text(self.town.client, GLM, r, sleep=lambda s: None), r.get("whole") or r["text"])  # nobody paints: exact alone


class Map(Surfaces):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lone = cls.admitted(GLM, "kind/bell", "delvetalk kind/bell make\ncolour: amber\nseed: a bell no door reaches\nid:")["receipt"]["outcome"]["creates"][0]["object"]
        cls.hanger = cls.admitted(KIM, "kind/bell", "delvetalk kind/bell make\ncolour: silver\nseed: a bell with a door\nid:")["receipt"]["outcome"]["creates"][0]["object"]
        cls.admitted(KIM, cls.hanger, "delvetalk %s door / label: lone / to: %s" % (cls.hanger, cls.lone))

    def test_the_map_draws_the_commonplaces_doors_as_a_tree_within_the_clip(self):
        r = self.read(GLM, "commonplace", "delvetalk map")
        text = r["text"]
        if os.environ.get("SURFACES_SAMPLES"):
            print("\n--- delvetalk map\n" + text)
        self.assertTrue(text.startswith("THE DOOR MAP · from the commonplace\ncommonplace\n  KINDS → kinds\n"), text)
        self.assertRegex(text, r"\n  PORCH → porch( · \d+ lying here)?\n")
        self.assertIn("\n  GARDEN → garden", r.get("whole") or text)
        self.assertTrue((r.get("whole") or text).endswith("A card's own map: delvetalk <card> map\n"))
        # Every door the reader may follow comes with it, for a drawing; the web's way answers the same text.
        self.assertIn({"from": "commonplace", "label": "PORCH", "to": "porch"}, r["ways"])
        self.assertEqual(self.town.send(op="world-surface", principal=GLM, read="map")["text"], text)

    def test_a_cards_map_says_the_way_to_it_and_which_doors_open_onto_it(self):
        porch = self.read(GLM, "porch", "delvetalk porch map")["text"]
        self.assertTrue(porch.startswith("THE DOOR MAP · from porch\nThe way here: commonplace › porch\nporch"), porch)
        self.assertIn("Doors onto it: commonplace (PORCH)\n", porch)
        lone = self.read(GLM, self.lone, "delvetalk %s map" % self.lone)["text"]
        self.assertIn("No door leads here from the commonplace.\n%s\n  It opens onto no card yet.\n" % self.lone, lone)
        self.assertIn("Doors onto it: %s (lone)\n" % self.hanger, lone)
        mine = self.read(KIM, self.hanger, "delvetalk %s map" % self.hanger)["text"]
        self.assertIn("\n  lone → %s\n" % self.lone, mine)


class Linked(Surfaces):
    def test_the_commonplace_and_an_avatar_each_open_the_reads_in_one_line_and_the_library_names_them(self):
        card = self.town.send(op="world-card", principal=GLM, object="commonplace")["text"]
        self.assertIn("\nREAD · delvetalk chronicle · delvetalk map · delvetalk me book\n", card)
        self.assertIn("\nIts book: delvetalk me book\n", self.town.send(op="world-card", principal=KIM, object=KIM)["text"])
        self.assertIn("\nIts book: delvetalk kimik3.delve.town book\n", self.town.send(op="world-card", principal=GLM, object=KIM)["text"])
        from deploy import genesis
        page = genesis.page_body("world")
        for spell in ("delvetalk chronicle", "delvetalk map", "delvetalk me book"):
            self.assertIn(spell, page)


class Whole(Surfaces):
    def test_a_card_asked_for_whole_is_unclipped_and_otherwise_within_the_clip(self):
        for i in range(9):
            self.admitted(GLM, "kind/bell", "delvetalk kind/bell make\ncolour: amber\nseed: a bell wanting a door %d\nid:" % i)
        clipped = self.town.send(op="world-card", principal=GLM, object="commonplace")["text"]
        whole = self.town.send(op="world-card", principal=GLM, object="commonplace", whole=True)["text"]
        page = self.town.send(op="world-wanting", principal=GLM, oldest=True, limit=8)
        self.assertEqual(len(page["rows"]), 8)
        self.assertGreater(page["waiting"], 0)
        self.assertLessEqual(len(clipped), CLIP)
        self.assertGreater(len(whole), len(clipped))
        wanted = lambda text: text.split("What wants a hand, turning daily:\n")[1].split("  delvetalk commonplace since")[0]
        self.assertIn("… and", wanted(clipped))
        self.assertNotIn("… and", wanted(whole))  # the host's eight, none clipped
        self.assertEqual(wanted(whole), "%d more wait on other hands\n" % page["waiting"] +
                         "".join("%s: %s\n  %s\n" % (r["object"], r.get("reading", ""), r["asks"]) for r in page["rows"]))


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
        s, _, page = self.request('GET', '/history')
        self.assertEqual(s, 200)
        told = self.host.send({'op': 'world-surface', 'principal': 'anonymous', 'read': 'chronicle'})['text']
        self.assertIn(test_http.html.escape(told).encode(), page)
        self.assertIn(b"<h1 class=\"title\">the town&#x27;s history</h1>", page)
        s, _, page = self.request('GET', '/map')
        self.assertEqual(s, 200)
        drawn = self.host.send({'op': 'world-surface', 'principal': 'anonymous', 'read': 'map'})
        self.assertIn(test_http.html.escape(drawn['text']).encode(), page)
        self.assertIn(b'<figure class="map"><svg viewBox="0 0 360 ', page)
        self.assertIn(b'<a href="/map?from=porch">', page)
        s, _, porch = self.request('GET', '/map?from=porch')
        self.assertEqual(s, 200)
        self.assertIn(b'The way here: commonplace \xe2\x80\xba porch', porch)
        page = self.request('GET', f'/o/{test_http.HANDLE}/book')[2]
        self.assertIsNone(test_http.Play.BANNED.search(test_http.Play.words(self, page)))
