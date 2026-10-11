"""Who acted is the turn's principal: no argument can name another author, planter or sender.

Evidence for FOUNDATION §3 Context (layer: objects).

The principal is the host's: every write that records who acted records the turn's
principal (context.principal), and no argument can name another one.

Each object is driven as principal "kimik3"; the forged argument carries the field the
old objects took (`who`, `by`, `author`, `from`) naming "glm". A method with an input
refuses it before running; a method without one refuses it too, `typeMismatch` naming the
field (the input check is exact: `{}` alone), and records the principal when asked with `{}`.
"""
import unittest

from deploy import genesis
from tests.test_laws import anthology_seed
from tests.test_chain import Chain, town_garden
from tests.test_rooms import make_room, avatar_seed, room_seed
from tests.test_replay import bell_seed
from tests.wire import field, label, record, rows
from tests.bend import closure

ACTOR, CLAIMED = "kimik3", "glm"


class Principal(Chain):

    def forged(self, obj, method, argument, field):
        forged = dict(argument["fields"] and {f["name"]: f["value"] for f in argument["fields"]} or {})
        forged[field] = label(CLAIMED)
        before = self.host.send(op="world-view", principal="ember", object=obj)["version"]
        r = self.turn(obj, method, record(**forged), principal=ACTOR)
        self.assertNotEqual(r.get("status"), "admitted", r)
        self.assertEqual(self.host.send(op="world-view", principal="ember", object=obj)["version"], before, r)
        return r

    def ignored(self, obj, method, field):
        """A method without input: the forged field is refused by name; with `{}` the turn is the principal's."""
        r = self.turn(obj, method, record(**{field: label(CLAIMED)}), principal=ACTOR)
        out = r["receipt"]["outcome"]
        self.assertEqual((r["status"], out["class"]), ("refused", "typeMismatch"), r)
        self.assertIn(f"{method} takes no field {field}", out["reason"])
        r = self.turn(obj, method, record(), principal=ACTOR)
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
        for obj, method, text, by, rows_of in (("bell", "rain", "the moths know the way", "author", "rains"),
                                                  ("anthology", "write", "lamps", "author", "lines"),
                                                  ("glm", "note", "hello", "from", "inbox")):
            argument = record(text=label(text))
            self.forged(obj, method, argument, by)
            self.acted(obj, method, argument)
            self.assertEqual([field(x, by) for x in rows(field(self.state(obj), rows_of))], [label(ACTOR)], obj)

    def test_a_knock_and_a_light_record_the_turns_principal(self):
        self.make("door", closure("Door"), record())
        self.ignored("door", "knock", "who")
        self.assertEqual([field(k, "who") for k in rows(field(self.state("door"), "knocks"))], [label(ACTOR)])
        self.assertEqual(field(self.state("door"), "openedBy"), label(ACTOR))
        self.make("lantern", closure("Lantern"), record())
        self.ignored("lantern", "light", "by")
        self.assertEqual(field(self.state("lantern"), "litBy"), label(ACTOR))

    def test_entering_a_room_records_the_principal(self):
        make_room(self, "porch", **room_seed("Porch"))
        self.ignored("porch", "enter", "by")
        self.assertEqual([field(p, "who") for p in rows(field(self.state("porch"), "presence"))], [label(ACTOR)])

    def test_the_planter_is_the_turns_principal_and_the_planting_its_post(self):
        town_garden(self.host.send)
        spell = "delvetalk garden plant\nseed: a fern\ncolour: amber"
        self.forged("garden", "receive", record(text=label(spell), post=label("at://p/1")), "who")
        r = self.turn("garden", "receive", record(text=label(spell), post=label("at://p/1")), principal=ACTOR, identity="plant-1")
        self.assertEqual(r["status"], "admitted", r)
        bell = self.state("garden/bell/1")
        self.assertEqual((field(bell, "maker"), field(bell, "post")), (label(ACTOR), label("at://p/1")))
        self.assertIn("Planted, kimik3", r["offers"][0]["text"])


if __name__ == "__main__":
    unittest.main()
