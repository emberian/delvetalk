"""The world moves between posts (docs/GENESIS.md "Motion"): genesis places, as ordinary kind instances, the weather over
the porch and the porch's lamp, a front; each places its rule on the tide, readable there and on its own card. At the
day's turn (every twenty-fourth tick) one of them moves: the weather rains on the porch's bells when someone entered the
porch that day, and a bell nobody has been near takes nothing; the lamp burns a segment lower when nobody did. The
porch's entering tends it, which is what both read. bell/1's clapper want says, in its reading and its spell, that a
clapper is a verb the first hand grows.

Evidence for OVERHAUL §2 (fronts; the weather daily) and TENURE's initiative (layer: scenarios).
"""
import unittest

from tests.test_scenarios import Arc, GLM
from tests.test_properties import OPENER


class Motion(Arc):
    def deliver(self):
        for _ in range(16):
            self.town.send(op="world-deliver", principal="transport", limit=16)
            if not self.town.send(op="world-pending").get("count"):
                return

    def ticks(self):
        return int(self.field("tide", "ticks")["value"])

    def advance(self, clock):
        self.assertEqual(self.town.send(op="world-advance", principal="transport", height=clock)["status"], "advanced")
        self.deliver()

    def to_tick(self, tick):
        """The tide walked an hour at a time (a jump ticks once) until it has ticked `tick` times; the clock now."""
        clock = self.town.send(op="world-status").get("clock", 0)
        while self.ticks() < tick:
            clock += 61
            self.advance(clock)
        return clock

    def lines(self, obj):
        rows = self.field(obj, "lines")["payload"]["fields"][0]["value"]["items"]
        return [next(f["value"]["value"] for f in r["fields"] if f["name"] == "text") for r in rows]

    def say_card(self, obj):
        return self.card(self.say(GLM, obj, ""))


class Seeded(Motion):
    def test_the_weather_and_the_lamp_hold_their_rules_on_the_tide_and_say_what_they_are(self):
        rules = {r["name"]: r for r in self.town.send(op="world-rules", principal=OPENER, object="tide")["rows"]}
        self.assertIn("weather", rules)
        self.assertIn("porch_slamp", rules)
        weather = self.say_card("weather")
        self.assertIn("WEATHER over porch, made by the town: once a clock day, while someone has been at porch that day, "
                      "it rains on every bell porch holds or hangs a door to, by its rule on tide:\n  delvetalk tide rules\n", weather)
        lamp = self.say_card("porch/lamp")
        self.assertIn("THE PORCH'S LAMP, a front set by the town: a slow pressure with a clock that fills while its condition "
                      "holds, and moves when full. Its clock: 0 of 4; it has not moved yet.", lamp)
        self.assertIn("When full: delvetalk porch write / text: the porch's lamp has burned down: four days and nobody came", lamp)

    def test_bell_1_wants_its_clapper_grown_as_a_verb(self):
        wants = self.say(GLM, "bell/1", "delvetalk bell/1 wants")["text"]
        self.assertIn("no clapper hangs in it yet: a verb, not a thing; the first hand grows hang, then hangs one", wants)
        self.assertIn("delvetalk bell/1 grow / name: hang / reading: hangs a clapper in it, in words\n", wants)


class Day(Motion):
    def test_a_day_someone_entered_the_porch_rains_on_its_tended_bell_and_leaves_the_lamp(self):
        clock = self.to_tick(23)
        self.assertEqual(self.say(GLM, "porch", "delvetalk porch enter")["status"], "admitted")
        self.assertEqual(self.say(GLM, "bell/1", "delvetalk bell/1 rain\ntext: a hand's rain")["status"], "admitted")
        clock += 200  # one jump past the day since genesis (it ticks once), within the day of the entering
        self.advance(clock)
        self.assertEqual(self.ticks(), 24)
        self.assertIn("weather's rain, clock %d" % clock, self.lines("bell/1"))
        # bell/2 was planted at genesis and nobody has been near it for a day: it takes nothing.
        self.assertEqual(self.lines("bell/2"), [])
        self.assertEqual(self.lines("weather"), ["rain at clock %d on 2" % clock])
        self.assertIn("Its clock: 0 of 4", self.say_card("porch/lamp"))

    def test_a_day_nobody_entered_the_porch_burns_the_lamp_lower_and_rains_on_nothing(self):
        clock = self.to_tick(23)
        self.advance(clock + 2000)  # one jump past the day: nobody has entered the porch since genesis
        self.assertEqual(self.ticks(), 24)
        self.assertEqual(self.lines("weather"), [])
        self.assertIn("Its clock: 1 of 4; it has not moved yet.", self.say_card("porch/lamp"))


if __name__ == "__main__":
    unittest.main()
