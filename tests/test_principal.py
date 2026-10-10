"""The principal is the host's: every write that records who acted records the turn's
principal (context.principal), and no argument can name another one.

Each object is driven as principal "kimik3"; the forged argument carries the field the
old objects took (`who`, `by`, `author`, `from`) naming "glm". A method with an input
refuses it before running ({'class': 'evaluation', 'reason': 'applied package refused by
Mini type checker'}); a method without one never sees it, and records the principal.
"""
import unittest

from tests.host import awaiting_relations
from tests.test_chain import Chain, garden_seed, reference
from tests.test_objects import closure
from tests.test_places import avatar_seed, names, place_seed
from tests.test_replay import bell_seed, get, items, rows
from tests.test_turn_world import label, record

ACTOR, CLAIMED = "kimik3", "glm"


class Principal(Chain):
    test_ring_then_open_then_light = None
    test_a_tick_cycle_ends_in_a_budget_exhausted_refusal = None

    def forged(self, obj, method, argument, field):
        forged = dict(argument["fields"] and {f["name"]: f["value"] for f in argument["fields"]} or {})
        forged[field] = label(CLAIMED)
        r = self.turn(obj, method, record(**forged), principal=ACTOR)
        self.assertNotEqual(r.get("status"), "admitted", r)
        self.assertEqual(self.host.send(op="world-view", principal="ember", object=obj)["version"], 0, r)
        return r

    def ignored(self, obj, method, field):
        """A method without input: the forged field is not seen; the turn is the principal's."""
        r = self.turn(obj, method, record(**{field: label(CLAIMED)}), principal=ACTOR)
        self.assertEqual(r["status"], "admitted", r)
        return r

    def acted(self, obj, method, argument=None):
        r = self.turn(obj, method, argument or record(), principal=ACTOR)
        self.assertEqual(r["status"], "admitted", r)
        return r

    @awaiting_relations
    def test_a_rain_is_authored_by_the_turns_principal(self):
        self.make("bell", closure("Bell"), bell_seed())
        argument = record(text=label("the moths know the way"))
        print("\n  forged rain:", self.forged("bell", "rain", argument, "author"))
        self.acted("bell", "rain", argument)
        self.assertEqual([get(r, "author") for r in rows(get(self.state("bell"), "rains"))], [label(ACTOR)])

    def test_a_submission_is_authored_by_the_turns_principal(self):
        # Anthology declares a law, so it is made with world-create (whole state) by its owner.
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Anthology"),
                           entry="initial", seed=record(owner=label("ember"), proposals={"tag": "list", "items": []}))
        self.assertEqual(r["status"], "created", r)
        argument = record(line=label("lamps"))
        self.forged("anthology", "submit", argument, "author")
        self.acted("anthology", "submit", argument)
        self.assertEqual([get(p, "author") for p in items(get(self.state("anthology"), "proposals"))], [label(ACTOR)])

    def test_a_note_is_from_the_turns_principal(self):
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        argument = record(text=label("hello"))
        self.forged("glm", "note", argument, "from")
        self.acted("glm", "note", argument)
        self.assertEqual([get(n, "from") for n in items(get(self.state("glm"), "inbox"))], [label(ACTOR)])

    def test_a_knock_and_a_light_record_the_turns_principal(self):
        self.make("door", closure("Door"), record())
        self.ignored("door", "knock", "who")
        self.assertEqual([get(k, "who") for k in items(get(self.state("door"), "knocks"))], [label(ACTOR)])
        self.assertEqual(get(self.state("door"), "openedBy"), label(ACTOR))
        self.make("lantern", closure("Lantern"), record())
        self.ignored("lantern", "light", "by")
        self.assertEqual(get(self.state("lantern"), "litBy"), label(ACTOR))

    def test_entering_a_place_records_the_principals_avatar(self):
        self.make("porch", closure("Place"), place_seed("Porch"))
        self.ignored("porch", "enter", "by")
        self.assertEqual(names(get(self.state("porch"), "present")), [ACTOR])

    def test_the_planter_is_the_turns_principal_and_the_planting_its_post(self):
        self.make("garden", closure("Garden"), garden_seed())
        spell = "delvetalk garden plant\nseed: a fern\ncolour: amber"
        self.forged("garden", "receive", record(text=label(spell), post=label("at://p/1"), slot=label("")), "who")
        r = self.turn("garden", "receive", record(text=label(spell), post=label("at://p/1"), slot=label("")), principal=ACTOR, identity="plant-1")
        self.assertEqual(r["result"]["label"], "planted", r)
        bell = self.state("garden/bell/1")
        self.assertEqual((get(bell, "planter"), get(bell, "planting")), (label(ACTOR), label("at://p/1")))
        self.assertIn("Planted for kimik3", r["offers"][0]["text"])


if __name__ == "__main__":
    unittest.main()
