"""Makers hear that their things were used: a line another hand writes on a RECORD (a write, a rain, a pour, a grown
verb), a grown verb used or an inspiriting on a THING, and a door a record hangs to a thing each send `heard {thing,
verb}` to the thing's maker's avatar, run as that hand; the avatar keeps it (`heard`), and one spell (`delvetalk me set
/ hear: no`) stops it. A send, not a rule: a rule's spell would name the hand by DID in every reply it reveals.

- Rain: a stranger's rain on a resident's bell is heard by the bell's maker, with the verb and the hand by handle; the
  maker's own rain is not.
- Verb: a grown verb another hand uses is heard by its name.
- Inspirit: the opener hears that a porch thing it laid there was inspirited.
- Door: a door another hand hangs to a thing is heard as `door`.
- Forgery: a hand's own turn of `heard` is refused by name.
- Hush: with `hear: no` nothing more is kept; `hear: yes` hears again.

Evidence for OVERHAUL §2 (rules on things) and §3 (Avatar's notes) (layer: scenarios).
"""
import unittest

from tests.test_scenarios import Arc, GLM, KIM
from tests.test_properties import OPENER, STRANGERS
from tests.wire import label, record


class Attention(Arc):
    def admitted(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def made(self, who, kind, extra):
        reply = self.admitted(self.say(who, kind, "delvetalk %s make\n%s" % (kind, extra)))
        return reply["receipt"]["outcome"]["creates"][0]["object"]

    def bell(self, who):
        return self.made(who, "kind/bell", "colour: amber\nseed: a bell for moths")

    def rain(self, who, bell, text):
        return self.admitted(self.say(who, bell, "delvetalk %s rain\ntext: %s" % (bell, text)))

    def heard(self, did):
        rows = self.field(did, "heard")["payload"]["fields"][0]["value"]["items"]
        return [tuple(next(f["value"]["value"] for f in r["fields"] if f["name"] == k) for k in ("thing", "verb", "by", "handle")) for r in rows]


class Heard(Attention):
    def test_a_strangers_rain_is_heard_by_the_bells_maker_and_the_makers_own_is_not(self):
        bell = self.bell(KIM)
        self.rain(KIM, bell, "my own")
        self.assertEqual(self.heard(KIM), [])
        rained = self.rain(GLM, bell, "a stranger's")
        self.assertNotIn("did:", "".join(rained.get("revealed", [])))
        self.assertEqual(self.heard(KIM), [(bell, "rain", GLM, STRANGERS[GLM])])
        self.assertEqual(self.heard(GLM), [])

    def test_a_grown_verb_another_hand_uses_is_heard_by_its_name(self):
        bell = self.bell(KIM)
        self.admitted(self.say(GLM, bell, "delvetalk %s grow\nname: water\nreading: poured on by a hand" % bell))
        self.admitted(self.say(GLM, bell, "delvetalk %s water\ntext: a cupful" % bell))
        self.assertEqual(self.heard(KIM), [(bell, "water", GLM, STRANGERS[GLM])])

    def test_the_opener_hears_a_porch_thing_inspirited(self):
        self.admitted(self.say(GLM, "porch/goblet", "delvetalk porch/goblet inspirit\nsurrounding: whatever the last guest left unsaid"))
        self.assertIn(("porch/goblet", "inspirit", GLM, STRANGERS[GLM]), self.heard(OPENER))

    def test_a_door_hung_to_a_thing_is_heard_by_its_maker(self):
        bell = self.bell(KIM)
        shelf = self.made(GLM, "kind/record", "")
        self.admitted(self.say(GLM, shelf, "delvetalk %s door / label: kim's bell / to: %s" % (shelf, bell)))
        self.assertEqual(self.heard(KIM), [(bell, "door", GLM, STRANGERS[GLM])])
        # A door to one's own thing is nobody else's act.
        mine = self.made(KIM, "kind/record", "")
        self.admitted(self.say(KIM, mine, "delvetalk %s door / label: my bell / to: %s" % (mine, bell)))
        self.assertEqual(len(self.heard(KIM)), 1)

    def test_a_hand_casting_heard_itself_is_refused_by_name(self):
        bell = self.bell(KIM)
        forged = self.turn(GLM, KIM, "heard", record(thing=label(bell), verb=label("rain")))
        self.assertEqual(self.outcome(forged), ("refused", "cardRefused"), forged)
        self.assertEqual(forged["receipt"]["outcome"]["clause"], "heard")
        self.assertEqual(self.heard(KIM), [])

    def test_hear_no_stops_it_and_hear_yes_hears_again(self):
        bell = self.bell(KIM)
        self.admitted(self.say(KIM, "me", "delvetalk me set\nhear: no"))
        self.rain(GLM, bell, "unheard")
        self.assertEqual(self.heard(KIM), [])
        self.admitted(self.say(KIM, "me", "delvetalk me set\nhear: yes"))
        self.rain(GLM, bell, "heard")
        self.assertEqual(self.heard(KIM), [(bell, "rain", GLM, STRANGERS[GLM])])


if __name__ == "__main__":
    unittest.main()
