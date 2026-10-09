"""The uniform card protocol (world/lib/Card.obend): receive {text, post, slot} routes a spell
naming the object to one of its forms, and answers anything else with the card and its
forms. Lantern is the smallest object that follows it."""
import unittest

from tests.test_turn_world import TurnWorld, closure, label, nat, record


def heard(text, post="at://glm/p/1"):
    return record(text=label(text), post=label(post), slot=label(""))


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
        self.assertEqual(r["result"]["label"], "done")
        self.assertEqual(self.lit(), (1, True, "glm"))
        self.assertEqual(r.get("offers", []), [])

    def test_prose_is_answered_with_the_card_and_its_forms_and_changes_nothing(self):
        r = self.say("hello counter")
        self.assertEqual(r["result"]["label"], "usage")
        self.assertEqual(r["offers"][0]["text"], "The lantern is dark.\n\nReply with a spell:\n\n    delvetalk c1 light\n")
        self.assertEqual(self.lit()[0], 0)

    def test_another_card_or_an_unknown_action_is_refused_by_name(self):
        r = self.say("delvetalk c2 light")
        self.assertEqual(r["result"]["payload"]["fields"][0]["value"], label("This card is c1"))
        self.assertIn("Not done: This card is c1", r["offers"][0]["text"])
        r = self.say("delvetalk c1 admire\nplant: open gate\nstatus: rooted")
        self.assertEqual(r["result"]["payload"]["fields"][0]["value"], label("No action called admire"))
        self.assertIn("    delvetalk c1 light\n", r["offers"][0]["text"])  # the actual forms, never a bare refusal
        r = self.say("delvetalk c1 light\nby: someone")
        self.assertEqual(r["result"]["payload"]["fields"][0]["value"], label("Unknown field by"))
        self.assertEqual(self.lit()[0], 0)

    def lit(self):
        v = self.host.send(op="world-view", principal="ember", object="c1")
        fields = {f["name"]: f["value"]["value"] for f in v["state"]["fields"]}
        return v["version"], fields["lit"], fields["litBy"]


if __name__ == "__main__":
    unittest.main()
