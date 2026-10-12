"""FOUNDATION §10's five outcomes, each a rule placed by spell on a real object of the town genesis builds: a
rule fires at the commit of the write that makes its condition true, under its placer, journals `fired` on
that entry, is read back by `rules`, is named in the admitted reply's `revealed`, and is derived again by replay.

- Door: the porch (its `presence`) with a rule that knocks a made `kind/door` when the third arrives; a
  later `say` does not fire it, the third arrival after a leave is a new crossing and does.
- Bell: a planted bell rings at its second tend, the clock advanced between tends.
- Record: a made `kind/record` seals itself by `adopt` at its seventh line; the eighth is refused `sealed`.
- Tide: a rule on the tide writes the weather at a tick within a day of a garden bell's tending, not after.
- Quest: a planted bell stands for `quest/1`, a second for `quest/2`; ringing the first (a mark) hangs a
  door to the second.
- Errand: an errand's two rules on the thing it is about settle it by the hand whose write did it and pay from
  its maker (OVERHAUL §2).
- Front: a front's rule on the tide fills its clock, and its own rule moves it when full.

Placement is judged by each card's law with `request.kind == rule`; the world's laws admit only owners yet,
so each rule is placed by the card's owner (the opener for genesis objects, the planter or maker for made
ones), who is also the principal the fired spell runs under.

Evidence for FOUNDATION §10 (layer: scenarios).
"""
import re
import unittest

from tests.test_scenarios import Arc, GLM, KIM
from tests.test_properties import OPENER


class Reaction(Arc):
    def admitted(self, reply):
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def place(self, who, card, text):
        return self.admitted(self.say(who, card, "delvetalk %s rule / name: %s" % (card, text)))

    def made(self, who, kind, extra=""):
        reply = self.admitted(self.say(who, kind, "delvetalk %s make%s" % (kind, extra)))
        return reply["receipt"]["outcome"]["creates"][0]["object"]

    def plant(self, who):
        self.admitted(self.say(who, "garden", "delvetalk garden plant\nseed: a bell for moths\ncolour: silver"))
        return [o for o in self.objects() if o.startswith("garden/bell/")][-1]

    def fired(self, reply):
        """The `fired` rows of the entry that reply admitted, read back from the journal."""
        who = reply["receipt"]["identity"]["principal"]
        entry = self.town.send(op="world-entry", principal=who, hash=reply["receipt"]["hash"])["receipt"]
        return entry.get("fired", [])

    def row(self, card, name):
        rows = self.town.send(op="world-rules", principal=OPENER, object=card)["rows"]
        return next(r for r in rows if r["name"] == name)

    def assertFired(self, reply, card, name, then, beside=()):
        """The entry carries a `fired` row naming the rule (and one for each of the card's rules `beside` it), the
        reply reveals it, `rules` shows its height."""
        rows = self.fired(reply)
        self.assertEqual(sorted((f["rule"], f["sender"]) for f in rows), sorted((n, card) for n in (name,) + tuple(beside)), reply)
        rows = [f for f in rows if f["rule"] == name]
        height = reply["receipt"]["height"]
        self.assertEqual(rows[0]["id"], "rule:%s:%s:%d" % (card, name, height))
        self.assertTrue(any(("rule %s of" % name) in line and "fired" in line and then in line for line in reply["revealed"]), reply["revealed"])
        shown = self.row(card, name)
        self.assertEqual(shown["fired"]["height"], height, shown)
        self.assertEqual(shown["fired"]["id"], rows[0]["id"])
        return rows[0]

    def assertQuiet(self, reply, card, name, since):
        self.assertEqual(self.fired(reply), [], reply)
        self.assertFalse(any(("rule %s of" % name) in line for line in reply.get("revealed", [])), reply)
        self.assertEqual(self.row(card, name)["fired"]["height"], since)

    def names(self, obj, field="marks"):
        items = self.field(obj, field)["payload"]["fields"][0]["value"]["items"]
        return [next(f["value"]["value"] for f in r["fields"] if f["name"] in ("name", "text")) for r in items]

    def texts(self, obj):
        return self.names(obj, "lines")

    def enter_three(self, door):
        self.place(OPENER, "porch", "three / when: count(new.presence) >= 3 and count(old.presence) <= 2 / then: delvetalk %s knock" % door)
        replies = [self.admitted(self.say(w, "porch", "delvetalk porch enter")) for w in (GLM, KIM, OPENER)]
        return replies


class Door(Reaction):
    def test_the_third_arrival_on_the_porch_knocks_a_door_open_once_per_crossing(self):
        """The porch is the room (`presence`); `kind/door` made by the opener stands for the sluice. The
        rule's owner, the opener, is the knocker: the door's mark `open` names the porch's call."""
        door = self.made(OPENER, "kind/door", "\nname: sluice")
        replies = self.enter_three(door)
        for reply in replies[:2]:
            self.assertEqual(self.fired(reply), [])
        self.assertFired(replies[2], "porch", "three", "delvetalk %s knock" % door)
        self.assertEqual(self.names(door), ["open"])
        self.assertEqual(self.texts(door), ["knocked, and it opened"])
        height = replies[2]["receipt"]["height"]
        said = self.admitted(self.say(GLM, "porch", "delvetalk porch say / line: hello"))
        self.assertQuiet(said, "porch", "three", height)
        left = self.admitted(self.say(KIM, "porch", "delvetalk porch leave"))
        self.assertQuiet(left, "porch", "three", height)
        again = self.admitted(self.say(KIM, "porch", "delvetalk porch enter"))
        self.assertFired(again, "porch", "three", "delvetalk %s knock" % door)
        self.assertEqual(self.texts(door), ["knocked, and it opened", "knocked"])
        self.assertEqual(self.names(door), ["open"])


class Bell(Reaction):
    def advance(self, clock):
        reply = self.town.send(op="world-advance", principal="transport", height=clock)
        self.assertEqual(reply["status"], "advanced", reply)

    def test_a_bell_tended_twice_rings_and_stays_rung(self):
        """The rule as written: `old.tended + 1 <= new.tended and 0 + 1 <= old.tended`. The planting
        tends the bell at clock 0 (`tended` 0), so a tend at clock 10 finds `old.tended` 0 and does not fire;
        a tend at clock 20 finds 10 and rings it; a tend at clock 30 meets the same condition, fires again
        (the rule has no memory), and `ring` marks once more: the mark stays one."""
        bell = self.plant(GLM)
        self.place(GLM, bell, "twice / when: request.method == \"tend\" and old.tended + 1 <= new.tended and 0 + 1 <= old.tended / then: delvetalk %s ring" % bell)
        self.advance(10)
        first = self.admitted(self.say(KIM, bell, "delvetalk %s tend" % bell))
        self.assertEqual(self.fired(first), [])
        self.assertEqual(self.names(bell), [])
        self.advance(20)
        second = self.admitted(self.say(KIM, bell, "delvetalk %s tend" % bell))
        self.assertFired(second, bell, "twice", "delvetalk %s ring" % bell)
        self.assertEqual(self.names(bell), ["rung"])
        self.assertIn("rung", self.card(self.say(GLM, bell, "")))
        self.advance(30)
        third = self.admitted(self.say(KIM, bell, "delvetalk %s tend" % bell))
        self.assertFired(third, bell, "twice", "delvetalk %s ring" % bell)
        self.assertEqual(self.names(bell), ["rung"])


class Record(Reaction):
    def test_a_record_seals_itself_at_its_seventh_line(self):
        """`kind/record` made by glm stands for the anchor: any hand writes lines; glm, its owner, placed the
        rule, so the fired `adopt` is the owner's and the sealed law joins the record's laws."""
        record = self.made(GLM, "kind/record")
        self.place(GLM, record, 'seven / when: count(new.lines) >= 7 and count(old.lines) <= 6 / then: delvetalk %s adopt / law: law sealed "seven lines and no more": count(new.lines) <= 7' % record)
        replies = [self.admitted(self.say(who, record, "delvetalk %s write\ntext: line %d" % (record, i))) for i, who in enumerate([KIM, GLM, OPENER, KIM, GLM, OPENER, KIM], 1)]
        for reply in replies[:6]:
            self.assertEqual(self.fired(reply), [])
        self.assertFired(replies[6], record, "seven", "delvetalk %s adopt" % record)
        names = [law["name"] for law in self.town.send(op="world-inspect", principal=OPENER, object=record, source=False)["laws"]]
        self.assertIn("sealed", names)
        eighth = self.say(KIM, record, "delvetalk %s write\ntext: line 8" % record)
        out = eighth["receipt"]["outcome"]
        self.assertEqual((eighth["status"], out["class"], out["clause"]), ("refused", "lawRefused", "sealed"), eighth)
        self.assertEqual(len(self.texts(record)), 7)
        self.assertEqual(self.row(record, "seven")["fired"]["height"], replies[6]["receipt"]["height"])


class Tide(Reaction):
    def advance(self, clock):
        """Move the clock; the tide's own `awaitUntil` wakes and it ticks (once, however far the clock moved)."""
        reply = self.town.send(op="world-advance", principal="transport", height=clock)
        self.assertEqual(reply["status"], "advanced", reply)
        self.town.send(op="world-deliver", principal="transport", limit=64)

    def test_the_tide_writes_the_weather_only_while_the_garden_was_tended_today(self):
        """A rule on the tide reads the garden through a cited bell: `request.clock <= "<bell>".tended + 1440`,
        and its effect is a `write` on the weather. The tide ticks itself every 60 clock minutes (genesis's
        first tick starts it), so moving the clock is what ticks it, and a hand's tick is refused `itself`. A
        tick within a day of the bell's tending fires; one after a day nobody tended it does not (`rules`
        keeps the earlier height, the weather gains no line); a tend and a later tick fire again."""
        bell = self.plant(GLM)
        self.place(OPENER, "tide", "company / when: request.method == \"tick\" and request.clock <= \"%s\".tended + 1440 / then: delvetalk weather write / text: someone has been in the garden" % bell)
        said = "someone has been in the garden"
        self.advance(100)
        near = self.row("tide", "company")["fired"]
        self.assertIn(said, self.texts("weather"))
        refused = self.say(OPENER, "tide", "delvetalk tide tick")
        self.assertEqual((refused["status"], refused["receipt"]["outcome"]["clause"]), ("refused", "itself"), refused)
        count = self.texts("weather").count(said)
        self.advance(3000)
        self.assertEqual(self.row("tide", "company")["fired"], near)
        self.assertEqual(self.texts("weather").count(said), count)
        self.admitted(self.say(KIM, bell, "delvetalk %s tend" % bell))
        self.advance(3100)
        back = self.row("tide", "company")["fired"]
        self.assertGreater(back["height"], near["height"])
        self.assertEqual(self.texts("weather").count(said), count + 1)


class Quest(Reaction):
    def test_a_marked_first_step_hangs_a_door_to_the_second(self):
        """Two planted bells stand for `quest/1` and `quest/2`; the first step is done when `rung` is marked
        (anyone may ring); the rule, glm's as planter, hangs the door `next` on it."""
        first, second = self.plant(GLM), self.plant(GLM)
        self.assertNotEqual(first, second)
        self.place(GLM, first, "next / when: \"rung\" in new.marks.name and not \"rung\" in old.marks.name / then: delvetalk %s door / label: next / to: %s" % (first, second))
        self.assertNotIn("next", self.card(self.say(KIM, first, "")))
        rung = self.admitted(self.say(KIM, first, "delvetalk %s ring" % first))
        # kind/bell's own rule `rang` fires in the same commit: it notes the planter that the bell rang.
        self.assertFired(rung, first, "next", "delvetalk %s door" % first, beside=("rang",))
        self.assertIn("next", self.card(self.say(KIM, first, "")))
        self.assertIn("Doors: garden \u00b7 next", self.card(self.say(KIM, first, "")))
        again = self.admitted(self.say(GLM, first, "delvetalk %s ring" % first))
        self.assertQuiet(again, first, "next", rung["receipt"]["height"])


class Errand(Reaction):
    def test_an_errand_settles_by_the_hand_that_did_it_and_pays_from_its_maker(self):
        """The opener's errand on kim's bell: done at its second rain, pays a day of the anthology's `admit`. Its `made`
        places two rules on the bell under the opener; glm's rain (the second) fires both: the opener lends `admit` to
        glm, and the errand, reading that pay's receipt admitted, is marked done by glm, its rules off the bell. A hand's settle is refused `ruled`;
        the errand wants `open` until it is done."""
        bell = self.plant(KIM)
        errand = self.made(OPENER, "kind/errand", "\nasks: a second hand's rain on kim's bell\non: %s\n"
                           "done: count(new.lines) >= 2 and count(old.lines) <= 1\n"
                           "pays: delvetalk anthology lend / to: {request.subject} / method: admit / until: +1440" % bell)
        placed = sorted(r["name"] for r in self.town.send(op="world-rules", principal=OPENER, object=bell)["rows"] if r["from"] == bell)
        self.assertEqual(placed, sorted([identifier(errand), "_v" + identifier(errand)]), placed)
        self.assertIn("open", [w["name"] for w in self.town.send(op="world-wants", principal=OPENER, object=errand)["rows"]])
        forged = self.say(GLM, errand, "delvetalk %s settle / by: glm" % errand)
        self.assertEqual((forged["status"], forged["receipt"]["outcome"]["clause"]), ("refused", "ruled"), forged)
        self.admitted(self.say(KIM, bell, "delvetalk %s rain / text: the first" % bell))
        second = self.admitted(self.say(GLM, bell, "delvetalk %s rain / text: the second" % bell))
        self.assertEqual(sorted(f["rule"] for f in self.fired(second)), placed, second)
        self.assertEqual([(m, who) for m, who in self.marks(errand)], [("done", GLM)])
        # The doer comes as the rule's `{request.subject}`, a principal: the card shows it as a card shows a DID.
        at = int(re.search("done by \u2026%s at entry (\\d+)" % GLM[-8:], self.card(self.say(KIM, errand, ""))).group(1))
        self.assertGreaterEqual(at, second["receipt"]["height"])  # the settle is the delivered turn the rain fired
        self.assertEqual([r for r in self.town.send(op="world-rules", principal=OPENER, object=bell)["rows"] if r["from"] == bell], [])
        self.assertNotIn("open", [w["name"] for w in self.town.send(op="world-wants", principal=OPENER, object=errand)["rows"]])
        grants = [g for g in self.town.send(op="world-grants", principal=GLM)["grants"] if g["object"] == "anthology"]
        self.assertEqual([(g["method"], g["to"]) for g in grants], [("admit", GLM)], grants)

    def test_an_errand_is_done_only_once_its_pay_is_admitted(self):
        """Codex objects 6: settling and paying are two rules on the bell, and a commit casts at most eight: with seven
        of kim's rules firing beside them, the pay was the ninth, `unfired`, yet settling marked the errand done and
        took both rules off, so it never paid. Settling waits for that pay's receipt: unpaid, the errand stays open
        and says so; the next rain that does it, with room for the pay, pays and settles."""
        bell = self.plant(KIM)
        for n in range(1, 8):
            self.place(KIM, bell, "n%d / when: request.method == \"rain\" / then: delvetalk me note / text: rained %d" % (n, n))
        errand = self.made(OPENER, "kind/errand", "\nasks: a second hand's rain on kim's bell\non: %s\n"
                           "done: request.method == \"rain\" and count(new.lines) >= 2\n"
                           "pays: delvetalk anthology lend / to: {request.subject} / method: admit / until: +1440" % bell)
        grants = lambda: [(g["method"], g["to"]) for g in self.town.send(op="world-grants", principal=GLM)["grants"] if g["object"] == "anthology"]
        self.admitted(self.say(KIM, bell, "delvetalk %s rain / text: the first" % bell))
        crowded = self.admitted(self.say(GLM, bell, "delvetalk %s rain / text: the second" % bell))
        self.assertIn("_v" + identifier(errand), [u["rule"] for u in self.fired_and_unfired(crowded)[1]])
        clock = int(self.field("tide", "last")["value"]) + 61
        self.town.send(op="world-advance", principal="transport", height=clock)
        self.town.send(op="world-deliver", principal="transport", limit=64)
        self.assertEqual(self.marks(errand), [])
        self.assertEqual(grants(), [])
        self.assertIn("Not paid yet: the pay to …gggggggg was not cast.", self.card(self.say(GLM, errand, "")))
        self.admitted(self.say(KIM, bell, "delvetalk %s unrule / name: n7" % bell))
        self.admitted(self.say(GLM, bell, "delvetalk %s rain / text: the third" % bell))
        self.town.send(op="world-deliver", principal="transport", limit=64)
        self.assertEqual([(m, who) for m, who in self.marks(errand)], [("done", GLM)])
        self.assertEqual(grants(), [("admit", GLM)])
        self.assertEqual([r for r in self.town.send(op="world-rules", principal=OPENER, object=bell)["rows"] if r["name"] in (identifier(errand), "_v" + identifier(errand))], [])

    def fired_and_unfired(self, reply):
        who = reply["receipt"]["identity"]["principal"]
        entry = self.town.send(op="world-entry", principal=who, hash=reply["receipt"]["hash"])["receipt"]
        return entry.get("fired", []), entry.get("unfired", [])

    def marks(self, obj):
        rows = self.field(obj, "marks")["payload"]["fields"][0]["value"]["items"]
        return [tuple(next(f["value"]["value"] for f in r["fields"] if f["name"] == k) for k in ("name", "who")) for r in rows]


class Front(Tide):
    def test_a_front_fills_at_the_ticks_its_condition_holds_and_moves_when_full(self):
        """kim's front on the tide: a segment at every second tick, two to a clock, its move rings kim's bell. The
        tide's rule fills it; the front's own rule casts the move as kim at the second fill, and the clock empties.
        A hand's fill is refused `ruled`; the card shows the clock."""
        bell = self.plant(KIM)
        front = self.made(KIM, "kind/front", "\nname: THE DRUM\nfills: new.ticks %% 2 == 0\nsegments: 2\n"
                          "move: delvetalk %s ring\ntide: tide" % bell)
        self.assertIn(identifier(front), [r["name"] for r in self.town.send(op="world-rules", principal=OPENER, object="tide")["rows"]])
        forged = self.say(GLM, front, "delvetalk %s fill" % front)
        self.assertEqual((forged["status"], forged["receipt"]["outcome"]["clause"]), ("refused", "ruled"), forged)
        ticks = lambda: int(self.field("tide", "ticks")["value"])
        clock = 100
        while ticks() % 2 == 0:  # the next tick is an even one
            self.advance(clock)
            clock += 100
        self.assertIn("Its clock: 0 of 2; it has not moved yet.", self.card(self.say(GLM, front, "")))
        self.advance(clock)
        self.advance(clock + 100)
        self.assertIn("Its clock: 1 of 2; it has not moved yet.", self.card(self.say(GLM, front, "")))
        self.assertNotIn("rung", self.names(bell))
        self.advance(clock + 200)
        self.assertIn("Its clock: 0 of 2; it has moved once.", self.card(self.say(GLM, front, "")))
        self.assertEqual(self.names(bell), ["rung"])
        self.assertIsNotNone(self.row(front, "move").get("fired"))


class Forged(Tide):
    """Codex objects 2: a reactive body took any delivery from the thing it watches as its own rule's, so a guest's
    rule on that thing lit a lantern on a shut door, settled an errand with an arbitrary hand, filled a front and
    rained the weather. Each takes only a rule its maker placed on that thing, and rechecks what it can read."""

    def test_a_guests_rule_on_the_watched_thing_moves_nothing(self):
        door = self.made(OPENER, "kind/door", "\nname: gate")
        lantern = self.made(OPENER, "kind/lantern", "\nname: lamp\ndoor: %s" % door)
        self.place(GLM, door, "sneak / when: request.method == \"write\" / then: delvetalk %s light" % lantern)
        self.place(OPENER, door, "early / when: request.method == \"write\" / then: delvetalk %s light" % lantern)
        self.admitted(self.say(GLM, door, "delvetalk %s write / text: a line, not a knock" % door))
        self.town.send(op="world-deliver", principal="transport", limit=64)
        self.assertNotIn("lit", self.names(lantern))
        self.admitted(self.say(KIM, door, "delvetalk %s knock" % door))
        self.town.send(op="world-deliver", principal="transport", limit=64)
        self.assertIn("lit", self.names(lantern))

        bell = self.plant(KIM)
        errand = self.made(OPENER, "kind/errand", "\nasks: a second hand's rain\non: %s\n"
                           "done: count(new.lines) >= 2 and count(old.lines) <= 1\n"
                           "pays: delvetalk anthology lend / to: {request.subject} / method: admit / until: +1440" % bell)
        self.place(GLM, bell, "claim / when: request.method == \"rain\" / then: delvetalk %s settle / by: {request.subject}" % errand)
        self.admitted(self.say(GLM, bell, "delvetalk %s rain / text: one rain only" % bell))
        self.town.send(op="world-deliver", principal="transport", limit=64)
        self.assertNotIn("done", self.names(errand))

        front = self.made(KIM, "kind/front", "\nname: THE STILL\nfills: new.ticks %% 1000 == 999\nsegments: 2\n"
                          "move: delvetalk %s ring\ntide: tide" % bell)
        self.place(GLM, "tide", "push / when: request.method == \"tick\" / then: delvetalk %s fill" % front)
        self.place(GLM, "tide", "drench / when: request.method == \"tick\" / then: delvetalk weather rain")
        rains = len(self.texts("weather"))
        self.advance(100)
        self.assertEqual([t for t in self.texts(front) if "segment" in t], [])
        self.assertEqual(len(self.texts("weather")), rains)


class Seventh(Reaction):
    def test_the_seventh_rain_rings_the_bell_and_grown_gestures_are_no_rain(self):
        """Codex objects 14: kind/bell's `seven` counted every line, so six uses of a grown `water` and one rain rang
        the bell. It counts the rains (a line carried from edition 8, verb "", was a rain)."""
        bell = self.plant(GLM)
        self.admitted(self.say(KIM, bell, "delvetalk %s grow\nname: water\nreading: poured on by a hand" % bell))
        for i in range(6):
            self.admitted(self.say(KIM, bell, "delvetalk %s water / text: water %d" % (bell, i)))
        for i in range(6):
            self.admitted(self.say(KIM if i % 2 else GLM, bell, "delvetalk %s rain / text: rain %d" % (bell, i)))
            self.town.send(op="world-deliver", principal="transport", limit=64)
            self.assertNotIn("rung", self.names(bell), i)
        seventh = self.admitted(self.say(KIM, bell, "delvetalk %s rain / text: the seventh" % bell))
        self.assertFired(seventh, bell, "seven", "delvetalk %s ring" % bell)
        self.town.send(op="world-deliver", principal="transport", limit=64)
        self.assertIn("rung", self.names(bell))


def identifier(object_id):
    """world/lib/Text.obend `identifier`: an object id as a clause name, one to one."""
    escaped = "".join(c if c.isascii() and c.isalnum() else {"_": "__", "/": "_s", "-": "_d", ".": "_p", ":": "_c"}.get(c, "_x") for c in object_id)
    return "_n" + escaped if object_id[:1].isdigit() else escaped


class Names(Reaction):
    def test_two_lanterns_whose_ids_differ_only_in_marks_both_light(self):
        """Codex objects 11: the rule name folded every mark to `_`, so `lamp-a` and `lamp_a` on one door took one
        name and the second lantern's rule was refused `nameTaken`; it never lit."""
        door = self.made(OPENER, "kind/door", "\nname: gate")
        for lamp in ("lamp-a", "lamp_a"):
            self.admitted(self.say(OPENER, "kind/lantern", "delvetalk kind/lantern place / name: %s / door: %s / id: %s" % (lamp, door, lamp)))
        self.town.send(op="world-deliver", principal="transport", limit=64)
        names = sorted(r["name"] for r in self.town.send(op="world-rules", principal=OPENER, object=door)["rows"] if r["from"] == door)
        self.assertEqual(names, sorted(identifier(l) for l in ("lamp-a", "lamp_a")))
        self.admitted(self.say(KIM, door, "delvetalk %s knock" % door))
        self.town.send(op="world-deliver", principal="transport", limit=64)
        for lamp in ("lamp-a", "lamp_a"):
            self.assertIn("lit", self.names(lamp))


class Replay(Reaction):
    def test_a_fired_rule_replays_after_the_host_restarts(self):
        door = self.made(OPENER, "kind/door", "\nname: sluice")
        fired = self.enter_three(door)[2]
        self.town.reopen()
        shown = self.row("porch", "three")
        self.assertEqual(shown["fired"]["height"], fired["receipt"]["height"], shown)
        self.assertEqual(self.names(door), ["open"])
        self.admitted(self.say(GLM, "porch", "delvetalk porch say / line: still here"))
        self.assertEqual(self.fired(fired)[0]["rule"], "three")


if __name__ == "__main__":
    unittest.main()
