"""Who acted is the turn's principal: no argument can name another author, planter or sender.

Evidence for FOUNDATION §3 Context (layer: objects).

The principal is the host's: every write that records who acted records the turn's
principal (context.principal), and no argument can name another one.

Each object is driven as principal "kimik3"; the forged argument carries the field the
old objects took (`who`, `by`, `author`, `from`) naming "glm". A method with an input
refuses it before running ({'class': 'evaluation', 'reason': 'applied package refused by
Mini type checker'}); a method without one never sees it, and records the principal.
"""
import unittest

from deploy import genesis
from tests.test_laws import anthology_seed
from tests.test_chain import Chain, garden_seed, town_kinds
from tests.test_objects import closure
from tests.test_places import make_place, avatar_seed, names, place_seed
from tests.test_replay import bell_seed, get, rows
from tests.test_turn_world import label, record

ACTOR, CLAIMED = "kimik3", "glm"


class Principal(Chain):

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

    def test_a_rain_a_line_and_a_note_are_the_turns_principals(self):
        # Record's creator passes its law, so it is made with world-create (whole state) by its owner.
        self.make("bell", closure("Bell"), bell_seed())
        r = self.host.send(op="world-create", principal="ember", identity="mk-anthology", object="anthology", modules=closure("Record"),
                           entry="initial", seed=anthology_seed("ember"), law=genesis.RECORD_LAW)
        self.assertEqual(r["status"], "created", r)
        self.make("glm", closure("Avatar"), avatar_seed("glm", "porch"))
        for obj, method, text, field, rows_of in (("bell", "rain", "the moths know the way", "author", "rains"),
                                                  ("anthology", "write", "lamps", "author", "lines"),
                                                  ("glm", "note", "hello", "from", "inbox")):
            argument = record(text=label(text))
            self.forged(obj, method, argument, field)
            self.acted(obj, method, argument)
            self.assertEqual([get(x, field) for x in rows(get(self.state(obj), rows_of))], [label(ACTOR)], obj)

    def test_a_knock_and_a_light_record_the_turns_principal(self):
        self.make("door", closure("Door"), record())
        self.ignored("door", "knock", "who")
        self.assertEqual([get(k, "who") for k in rows(get(self.state("door"), "knocks"))], [label(ACTOR)])
        self.assertEqual(get(self.state("door"), "openedBy"), label(ACTOR))
        self.make("lantern", closure("Lantern"), record())
        self.ignored("lantern", "light", "by")
        self.assertEqual(get(self.state("lantern"), "litBy"), label(ACTOR))

    def test_entering_a_place_records_the_principals_avatar(self):
        make_place(self, "porch", place_seed("Porch"))
        self.ignored("porch", "enter", "by")
        self.assertEqual(names(get(self.state("porch"), "present")), [ACTOR])

    # A planting spell runs `plant` directly, and a method does not see the reply's post (the bell's
    # strike awaits it): the garden takes the turn's intent, which the bridge makes the post. Expected
    # to fail until the host gives a spell's method its post (Abi.Context inputOrigin `post`).
    def test_the_planter_is_the_turns_principal_and_the_planting_its_post(self):
        self.make("garden", closure("Garden"), garden_seed())
        town_kinds(self.host.send)
        spell = "delvetalk garden plant\nseed: a fern\ncolour: amber"
        self.forged("garden", "receive", record(text=label(spell), post=label("at://p/1")), "who")
        r = self.turn("garden", "receive", record(text=label(spell), post=label("at://p/1")), principal=ACTOR, identity="plant-1")
        self.assertEqual(r["result"]["label"], "planted", r)
        bell = self.state("garden/bell/1")
        self.assertEqual((get(bell, "maker"), get(bell, "post")), (label(ACTOR), label("at://p/1")))
        self.assertIn("Planted, kimik3", r["offers"][0]["text"])


if __name__ == "__main__":
    unittest.main()
