"""The world's laws admit rules and wants by their readers (OVERHAUL §2, conflict 8): a request of kind `rule` is
judged by each card's own law, and every law the world writes says `or request.kind == rule`, so a resident places a
rule or a want on the opener's garden, on another's bell and on a thing lying on the porch, and the rule fires under
the resident who placed it. A kind's text carries rules and wants through `under` to every instance, owned by the
kind's owner; a line in none of the three modalities is refused before the kind is made.

Evidence for OVERHAUL §2 and §5 step 4 (layer: objects).
"""
import unittest

from tests.test_scenarios import Arc, GLM, KIM
from tests.test_properties import OPENER


class Placing(Arc):
    def admitted(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def plant(self, who):
        self.admitted(self.say(who, "garden", "delvetalk garden plant\nseed: a bell for moths\ncolour: silver"))
        return [o for o in self.objects() if o.startswith("garden/bell/")][-1]

    def rows(self, card, op="world-rules"):
        return {r["name"]: r for r in self.town.send(op=op, principal=OPENER, object=card)["rows"]}

    def test_a_resident_places_rules_and_wants_on_cards_they_do_not_own(self):
        bell = self.plant(GLM)
        self.admitted(self.say(KIM, "garden", "delvetalk garden rule / name: fifth / when: count(new.things) >= 5 and count(old.things) <= 4 / then: delvetalk porch write / text: five bells; the sixth is not yet hung"))
        self.admitted(self.say(KIM, bell, "delvetalk %s rule / name: two / when: count(new.lines) >= 2 and count(old.lines) <= 1 / then: delvetalk me note / text: two rains" % bell))
        self.admitted(self.say(KIM, "porch/goblet", "delvetalk porch/goblet want / name: kept / when: new.keeper == \"\" / asks: delvetalk porch/goblet inspirit"))
        self.assertEqual(self.rows("garden")["fifth"]["owner"], KIM)
        self.assertEqual(self.rows("porch/goblet", "world-wants")["kept"]["asks"], "delvetalk porch/goblet inspirit")
        for i, who in enumerate([OPENER, GLM], 1):
            rained = self.admitted(self.say(who, bell, "delvetalk %s rain\ntext: drizzle %d" % (bell, i)))
        self.assertTrue(any("rule two of" in line and "fired" in line for line in rained["revealed"]), rained["revealed"])
        self.assertIn("two rains", [text for _, text in self.inbox(KIM)])

    def test_a_kind_carries_its_rules_and_wants_to_every_instance(self):
        law = ('law kept "a line is only added": insertOnly(lines)\n'
               'rule chimed "tells its kind\'s maker at the second line": count(new.lines) >= 2 and count(old.lines) <= 1 then delvetalk me note / text: chimed {request.object}\n'
               'want heard "a chime nobody has written in": count(new.lines) == 0 asks delvetalk {request.object} write')
        made = self.admitted(self.say(KIM, "kinds", "delvetalk kinds make\nname: chime\nof: record\nlaw: <<END\n%s\nEND" % law))
        self.assertIn("kind/chime", self.objects(), made)
        chime = self.admitted(self.say(GLM, "kind/chime", "delvetalk kind/chime make"))["receipt"]["outcome"]["creates"][0]["object"]
        wanted = self.rows(chime, "world-wants")["heard"]
        self.assertEqual((wanted["owner"], wanted["asks"]), (KIM, "delvetalk %s write" % chime))
        for i in (1, 2):
            self.admitted(self.say(GLM, chime, "delvetalk %s write\ntext: line %d" % (chime, i)))
        self.assertNotIn("heard", self.rows(chime, "world-wants"))
        self.assertEqual(self.rows(chime)["chimed"]["owner"], KIM)
        self.assertIn("chimed %s" % chime, [text for _, text in self.inbox(KIM)])

    def test_a_kind_text_line_in_no_modality_is_refused_before_anything_is_made(self):
        refused = self.say(KIM, "kinds", "delvetalk kinds make\nname: chime\nof: record\nlaw: when it rings, tell me")
        out = refused["receipt"]["outcome"]
        self.assertEqual((refused["status"], out["clause"]), ("refused", "badValue"), refused)
        self.assertIn("a rule ending then SPELL", out["reason"])
        self.assertNotIn("kind/chime", self.objects())


if __name__ == "__main__":
    unittest.main()
