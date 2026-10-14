"""Claude grew sit and call on room/4 and fold: grown verbs must be offered exactly like a form.

Refuted by a grown verb absent from inspect's offered forms, HTTP actions, `?`
or `verbs` on a plain room, a spween room or a bell with its own actions.
"""
import tempfile
import unittest

from tests.town import Town
from tests.wire import label, record
from transport.http import actions


class CardVerbs(unittest.TestCase):
    """Claude grew sit and call on room/4 and fold: each must be offered exactly like a form."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.town = Town(tmp.name, cleanup=self.addCleanup, furnished=False)

    def say(self, thing, text, who="glm", status="admitted"):
        reply = self.town.send(op="world-turn", principal=who, object=thing,
                               method="receive", argument=record(text=label(text), post=label("")),
                               identity="card-verbs-" + str(self.town.send(op="world-status")["height"]))
        self.assertEqual(reply["status"], status, reply)
        return reply

    def made(self, kind, fields):
        reply = self.say(kind, "delvetalk " + kind + " make / " + fields)
        return reply["receipt"]["outcome"]["creates"][0]["object"]

    def assert_surfaces(self, thing, declared, grown, who="kimi"):
        seen = self.town.send(op="world-inspect", principal=who, object=thing)
        controls = {a["name"]: a for a in actions("/AGENTS.md", thing, seen)}
        usage = self.say(thing, f"delvetalk {thing} ?", who, status="usage")["text"]
        verbs = self.say(thing, f"delvetalk {thing} verbs", who, status="usage")["text"]
        self.assertIn(declared, seen["offered"])
        self.assertEqual(controls[declared]["spell"], seen["templates"][declared])
        self.assertIn(seen["templates"][declared].rstrip(), usage)
        declared_line = next(line for line in verbs.splitlines() if line.startswith("Declared by its kind:"))
        self.assertIn(declared, declared_line)
        for name, takes in grown:
            self.assertIn(name, seen["offered"])
            self.assertEqual(controls[name]["spell"], seen["templates"][name])
            self.assertIn(seen["templates"][name].rstrip(), usage)
            self.assertIn(f"» {name} (grown by glm, entry ", verbs)
            self.assertNotIn(name, declared_line)
            self.assertIn(f"delvetalk {thing} {name}" + (" / text: <a line>" if takes else ""), verbs)

    def test_plain_and_spween_rooms_offer_sit_and_call_exactly_like_forms(self):
        for scene in ("", " / spween: A moss gate, ajar."):
            with self.subTest(scene=bool(scene)):
                room = self.made("kind/room", "name: the sitting room" + scene)
                for name, takes in (("sit", "text"), ("call", "")):
                    self.say(room, f"delvetalk {room} grow / name: {name} / reading: {name}s here / takes: {takes}")
                grown = (("sit", True), ("call", False))
                self.assert_surfaces(room, "enter", grown)
                self.say(room, f"delvetalk {room} enter", "kimi")
                self.assert_surfaces(room, "say", grown)

    def test_bell_with_its_own_actions_offers_fold_exactly_like_a_form(self):
        bell = self.made("kind/bell", "colour: amber / seed: a bell to fold")
        self.say(bell, f"delvetalk {bell} grow / name: fold / reading: folds / takes: text")
        self.assert_surfaces(bell, "rain", (("fold", True),))


if __name__ == "__main__":
    unittest.main()
