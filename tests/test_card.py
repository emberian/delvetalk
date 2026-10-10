"""The card protocol: a spell naming the card runs its action, an empty reply gets the card, prose
addressed to nobody gets nothing.

Evidence for FOUNDATION §5 (layer: objects).

The uniform card protocol (world/lib/Card.obend): receive {text, post} routes a spell
naming the object to one of its forms, and answers anything else with the card and its
forms. Lantern is the smallest object that follows it.
"""
import unittest

from tests.host import HostCase
from tests.test_turn_world import TurnWorld, closure, label, nat, record


def heard(text, post="at://glm/p/1"):
    return record(text=label(text), post=label(post))


class Receive(TurnWorld):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-c1", object="c1", modules=closure("Lantern"),
                           entry="initial", seed=record(lit={"tag": "boolean", "value": False}, litBy=label("")))
        self.assertEqual(r["status"], "created", r)

    def say(self, text):
        r = self.turn("c1", "receive", heard(text), principal="glm")
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_a_spell_naming_the_card_and_an_action_runs_it(self):
        r = self.say("quoting the invitation\ndelvetalk c1 light")
        self.assertEqual(r["result"], {"tag": "boolean", "value": True})  # the method's own result
        self.assertEqual(self.lit(), (1, True, "glm"))
        self.assertEqual(r.get("offers", []), [])

    def test_prose_is_not_addressed_and_gets_nothing_and_an_empty_reply_the_card(self):
        """Run 5, finding 2: a card answers prose that names none of its forms, fields or actions
        with no offer at all, so nothing is drafted; an empty reply still asks for the card."""
        r = self.say("hello counter, what a lovely thread")
        self.assertEqual((r["result"]["label"], r.get("offers", [])), ("silent", []))
        r = self.say("")
        self.assertEqual(r["result"]["label"], "usage")
        self.assertEqual(r["offers"][0]["text"], "The lantern is dark.\n\nReply with a spell:\n\n    delvetalk c1 light\n")
        self.assertEqual(self.lit()[0], 0)

    def test_another_card_or_an_unknown_action_is_refused_by_name(self):
        """The host reads the spell (the lantern speaks the message dialect): a misfit is a refused
        turn of class badSpell with its clause, reason and hint, the hint the spell to send."""
        for i, (text, clause, reason) in enumerate([("delvetalk c2 light", "otherCard", "There is no card c2; the directory lists the doors."),
                                                    ("delvetalk c1 admire\nplant: open gate\nstatus: rooted", "noAction", "c1 has no spell admire; it has these:"),
                                                    ("delvetalk c1 light\nby: someone", "unknownField", "No field by in this spell; it takes none.")]):
            r = self.turn("c1", "receive", heard(text), principal="glm", identity="bad%d" % i)
            out = r["receipt"]["outcome"]
            self.assertEqual((r["status"], out["class"], out["clause"], out["reason"]), ("refused", "badSpell", clause, reason), r)
            self.assertIn("delvetalk c1 light", out["hint"])  # the actual forms, never a bare refusal
        self.assertEqual(self.lit()[0], 0)

    def lit(self):
        v = self.host.send(op="world-view", principal="ember", object="c1")
        fields = {f["name"]: f["value"].get("value") for f in v["state"]["fields"]}
        return v["version"], fields["lit"], fields["litBy"]


if __name__ == "__main__":
    unittest.main()


class CounterCard(TurnWorld):
    """Counter, the host suites' reference object, follows the protocol too."""

    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-k", object="k", modules=closure("Counter"),
                           entry="initial", seed=record(count=nat(0)))
        self.assertEqual(r["status"], "created", r)

    def test_a_bump_spell_bumps_an_empty_reply_shows_the_count_and_prose_gets_nothing(self):
        r = self.turn("k", "receive", heard("delvetalk k bump"), principal="glm")
        self.assertEqual((r["status"], r["result"], r.get("offers", [])), ("admitted", nat(1), []), r)
        r = self.turn("k", "receive", heard(""), principal="glm")
        self.assertEqual(r["offers"][0]["text"], "Count: 1\nReply with a spell:\n\n    delvetalk k bump\n")
        self.assertEqual(self.turn("k", "receive", heard("how many?"), principal="glm").get("offers", []), [])
        self.assertEqual(self.turn("k", "bump")["result"], nat(2))
