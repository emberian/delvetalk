"""The weather rains on every bell of a full garden, not on the first thirty-two it can send to.

Evidence for docs/METAPHYSICS.md section 7.4 (layer: scenarios). A turn holds at most 32 sends
(Limits.sendsPerTurn) and reads each candidate's kind, so a rain turn takes sixteen candidates and a self-sent
`drizzle` carries on from where it stopped; the last writes the weather's line and the forecast.

Refuted by: a bell of a garden holding 32 bells (or more) that the rain left without the weather's line.
"""
import unittest

from tests.test_properties import OPENER
from tests.test_scenarios import Arc, GLM
from tests.wire import label, record


class Weather(Arc):
    def deliver(self):
        for _ in range(16):  # the tide's own wake stays pending, so this walks the deliveries a few rounds
            self.town.send(op="world-deliver", principal="transport", limit=16)

    def rains(self, bell):
        state = self.town.send(op="world-view", principal=OPENER, object=bell)["state"]
        lines = next(f["value"] for f in state["fields"] if f["name"] == "lines")["payload"]["fields"][0]["value"]["items"]
        return [next(f["value"]["value"] for f in row["fields"] if f["name"] == "text") for row in lines]

    def test_a_garden_of_thirty_two_bells_is_rained_on_in_every_bell(self):
        for i in range(32):
            planted = self.say(GLM, "garden", "delvetalk garden plant\nseed: bell %d\ncolour: silver" % i)
            self.assertEqual(planted["status"], "admitted", planted)
        bells = sorted(o for o in self.objects() if o.startswith("garden/bell/"))
        self.assertEqual(len(bells), 32)
        placed = self.say(OPENER, "tide", "delvetalk tide rule\nname: soon\nwhen: request.method == \"tick\"\nthen: delvetalk garden/weather rain")
        self.assertEqual(placed["status"], "admitted", placed)
        tended = self.say(GLM, "garden", "delvetalk garden tend")
        self.assertEqual(tended["status"], "admitted", tended)
        clock = self.town.send(op="world-status").get("clock", 0)
        self.assertEqual(self.town.send(op="world-advance", principal="transport", height=clock + 61)["status"], "advanced")
        self.deliver()
        dry = [b for b in bells if not any(t.startswith("garden/weather's rain") for t in self.rains(b))]
        self.assertEqual(dry, [])
        lines = self.rains("garden/weather")
        self.assertTrue(any(t.endswith(" on 32") for t in lines), lines)


if __name__ == "__main__":
    unittest.main()
