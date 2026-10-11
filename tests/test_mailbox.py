"""An avatar's inbox: a post that mentions its resident is a note from the author, answered with
nothing; its principal marks the entry it has read through; the inbox keeps the newest 64.

Evidence for FOUNDATION §8 claims (layer: objects).

The bridge addresses a post that mentions a resident to that resident's avatar, as the author's
turn: `receive {text, post}` from anyone but the avatar's principal. A reply that is prose (no
spell) and not blank becomes a note in the inbox (the author, their handle, the text cut to 280
characters, the post as `uri`) and offers nothing. `seen {at}` is the principal's alone, at least
the current mark; the card shows the notes after the mark, newest first, and the spell that moves it.

Refuted by: a mention that answers the author or leaves no note; a blank reply that notes; a text
past 280 characters kept whole; a stranger marking another's inbox read, or moving the mark back; a
card showing a stranger the notes; a read note still counted new; a 65th note not dropping the oldest.
"""
import unittest

from tests import test_chain
from tests.test_rooms import avatar_seed
from tests.wire import cast_refusal, field, label, nat, record, rows
from tests.bend import closure

GLM, KIM = "did:plc:glm", "did:plc:kimik3"
POST = "at://did:plc:kimik3/town.delve.feed.post/3k"


def heard(text, post=""):
    return record(text=label(text), post=label(post))


class Inbox(test_chain.Chain):

    def setUp(self):
        super().setUp()
        for did, handle in ((GLM, "glm"), (KIM, "kimik3")):
            self.make(did, closure("Avatar"), avatar_seed(handle, "porch"))

    def say(self, obj, text, who):
        r = self.turn(obj, "receive", heard(text), principal=who)
        if r["status"] == "refused":  # a card's refusal of the spell cast on it refuses the turn
            cast_refusal(r)
        else:
            self.assertEqual(r["status"], "admitted", r)
        return r

    def notes(self, did):
        return rows(field(self.state(did), "inbox"))

    def card(self, did, who):
        r = self.turn(did, "receive", heard(""), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r["offers"][0]["text"]

    def mention(self, text, post=POST, who=KIM):
        r = self.turn(GLM, "receive", heard(text, post), principal=who)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_a_mention_is_a_note_from_its_author_and_offers_nothing(self):
        r = self.mention("glm, the garden wants water")
        self.assertEqual(r.get("offers", []), [], r)
        (note,) = self.notes(GLM)
        self.assertEqual([field(note, k)["value"] for k in ("from", "text", "uri")], [KIM, "glm, the garden wants water", POST])
        self.assertEqual(field(note, "handle")["value"], "")
        self.mention("x" * 400)
        self.assertEqual(len(field(self.notes(GLM)[-1], "text")["value"]), 280)

    def test_a_blank_reply_and_the_principals_own_prose_are_no_mention(self):
        self.assertEqual(self.card(GLM, KIM).splitlines()[0], "glm's avatar, in porch.")
        self.say(GLM, "   ", KIM)
        self.say(GLM, "hello there", GLM)
        self.assertEqual(self.notes(GLM), [])

    def test_a_spell_cast_by_a_stranger_is_no_mention(self):
        r = self.say(GLM, "delvetalk %s seen\nat: 3" % GLM, KIM)
        self.assertEqual(cast_refusal(r)[1], "Only glm marks it read.")
        self.assertEqual(self.notes(GLM), [])

    def test_the_principal_reads_the_new_notes_and_marks_them_seen(self):
        for text in ("first", "second", "third"):
            self.mention(text)
        ats = [int(field(n, "at")["value"]) for n in self.notes(GLM)]
        self.assertEqual(ats, sorted(ats))
        mine = self.card(GLM, GLM)
        self.assertIn("3 new since entry 0:\n", mine)
        self.assertLess(mine.index("third"), mine.index("first"))  # newest first
        self.assertIn("#%d " % ats[2], mine)
        self.assertIn("  delvetalk me seen / at: %d\n" % ats[2], mine)
        theirs = self.card(GLM, KIM)
        self.assertIn("3 notes\n", theirs)
        self.assertNotIn("third", theirs)
        self.assertNotIn("new since", theirs)

        seen = self.turn(GLM, "seen", record(at=nat(ats[1])), principal=GLM)
        self.assertEqual(seen["status"], "admitted", seen)
        text = seen["offers"][0]["text"]
        self.assertTrue(text.startswith("Read through entry %d; nothing before it is new again.\n" % ats[1]), text)
        self.assertIn("1 new since entry %d:\n" % ats[1], text)
        self.assertNotIn("second", text)
        self.assertIn("third", text)

        behind = self.say(GLM, "delvetalk me seen\nat: %d" % (ats[1] - 1), GLM)
        self.assertEqual(cast_refusal(behind)[0], "alreadySeen")
        self.assertIn("Already read through entry %d." % ats[1], cast_refusal(behind)[1])
        through = self.turn(GLM, "seen", record(at=nat(ats[2])), principal=GLM)
        self.assertIn("No new notes since entry %d." % ats[2], through["offers"][0]["text"])
        self.assertEqual(field(self.state(GLM), "seen")["value"], str(ats[2]))

    def test_a_stranger_cannot_mark_an_inbox_read(self):
        self.mention("hello")
        r = self.turn(GLM, "seen", record(at=nat(9)), principal=KIM)
        self.assertEqual(r["status"], "refused", r)
        self.assertEqual(field(self.state(GLM), "seen")["value"], "0")

    def test_the_inbox_keeps_the_newest_sixty_four(self):
        for i in range(65):
            self.mention("note %03d" % i)
        texts = [field(n, "text")["value"] for n in self.notes(GLM)]
        self.assertEqual((len(texts), texts[0], texts[-1]), (64, "note 001", "note 064"))


if __name__ == "__main__":
    unittest.main()
