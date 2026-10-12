"""A card's renderer keeps the whole card under Card.limit(context), one budget across its fixed head and its lists.

Evidence for the card budget convention (world/lib/Card.obend `limit`, `left`, `clippedWithin`; layer: objects).

Refuted by: a Library index of 32 long-titled pages, a Workshop holding many long-named proposals, or a Thing with a
400-character description and long lines its grown verb left, whose card passes the 1,400-character reply less the
receipt line, or whose closing law spell the clip dropped.
"""
import unittest

from tests.test_chain import Chain
from tests.test_workshop import BLOCK
from tests.bend import MODULES, closure
from tests.wire import label, nat, record


def limit(object_id):
    return 1400 - (2 * len(object_id) + 120)


class CardBudgets(Chain):
    def card(self, name, principal="glm"):
        reply = self.turn(name, "receive", record(text=label(""), post=label("")), principal=principal)
        self.assertEqual(reply["status"], "admitted", reply)
        return reply["offers"][0]["text"]

    def test_a_library_of_32_long_titled_pages_renders_within_the_limit_and_keeps_its_law_line(self):
        self.make("library", closure("Library"), record(owner=label("ember"), ownerHandle=label("")))
        for i in range(32):
            kind = "walk" if i % 8 == 7 else "page"
            reply = self.turn("library", "shelve", record(name=label("page-%02d" % i), kind={"tag": "variant", "label": kind, "payload": record()},
                                                          title=label(("T%02d " % i) + "x" * 76),
                                                          body=label("body")), principal="ember", identity="shelve-%d" % i)
            self.assertEqual(reply["status"], "admitted", reply)
        text = self.card("library")
        self.assertLessEqual(len(text), limit("library"), text)
        self.assertIn("A card's law as the host has it: delvetalk library laws / card: bell/1\n", text)
        self.assertIn("… and ", text)

    def test_a_workshop_holding_many_long_named_proposals_renders_within_the_limit(self):
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))
        source = open(MODULES["Counter"]).read().replace("record State:", 'law owner: request.kind == 0 or request.subject == "glm"\nrecord State:', 1)
        made = self.host.send(op="world-create", principal="glm", identity="mk-t", object="a-target-card-with-a-long-id-for-the-line", entry="initial",
                              modules=closure("Counter", override={"Counter": source}), seed=record(count=nat(0)))
        self.assertEqual(made["status"], "created", made)
        for i in range(12):
            who = "a-proposer-with-a-rather-long-name-%02d" % i
            reply = self.turn("workshop", "receive", record(text=label("delvetalk workshop propose\ntarget: a-target-card-with-a-long-id-for-the-line\n```obend\n%s```\n" % BLOCK),
                                                            post=label("at://x/%d" % i)), principal=who, identity="held-%d" % i)
            self.assertEqual(reply["status"], "admitted", reply)
        text = self.card("workshop")
        self.assertIn("Held (", text)
        self.assertLessEqual(len(text), limit("workshop"), text)

    def test_a_thing_with_a_long_description_and_long_grown_lines_renders_within_the_limit(self):
        self.make("thing", closure("Thing"), record(owner=label("glm"), name=label("n" * 64), description=label("d" * 400)))
        say = lambda text, i: self.turn("thing", "receive", record(text=label(text), post=label("")), principal="glm", identity="t-%d" % i)
        grown = say("delvetalk thing grow\nname: shine\nreading: a gesture of light", 0)
        self.assertEqual(grown["status"], "admitted", grown)
        for i in range(1, 5):
            reply = say("delvetalk thing shine\ntext: %d %s" % (i, "s" * 270), i)
            self.assertEqual(reply["status"], "admitted", reply)
            self.assertLessEqual(len(reply["offers"][0]["text"]), limit("thing"), reply)
        text = self.card("thing", principal="kim")
        self.assertLessEqual(len(text.split("\nReply with a spell:")[0]), limit("thing"), text)
        self.assertIn("4 " + "s" * 270, text)  # the newest line leads


if __name__ == "__main__":
    unittest.main()
