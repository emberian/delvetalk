"""The all-night station (genesis `--with-gas-station`): a first fantasy scene a resident walks into, braided out
into the town. Its door rings mimo's bell; a coffee taken to the counter becomes a thing offered into the reader's
hands; a wall clock moves only when wound; a register nobody keeps until someone inspirits it, which the station
then wants kept with every visitor it has had. The station keeps no time: entering writes no clock, a departure
keeps no clock minute, and one who comes back is told it could have been a minute or a year.

Evidence for FOUNDATION section 10, "A scene is the same grammar" (layer: scenarios).

Refuted by: a casting choice that does not fire under the station's owner; a coffee that is not a THING offered
to the reader and taken by `accept`; the register's choice offered to one who does not keep it; the want not
opening when the register is kept and short of a visitor, or not closing on a signature; an entering that moves
`tended`; a departure keeping a clock minute; the return not saying it could have been a minute or a year.
"""
import unittest

from deploy import genesis
from tests import test_scenarios
from tests.test_properties import OPENER

KIM, GLM = test_scenarios.KIM, test_scenarios.GLM


class Station(test_scenarios.Arc):
    def setUp(self):
        super().setUp()
        made = genesis.gas_station(self.town.client, OPENER)
        self.assertTrue(all(m["status"] in ("created", "admitted") for m in made), made)

    def admitted(self, who, card, text):
        reply = self.say(who, card, text)
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def deliver(self):
        self.town.send(op="world-deliver", principal="transport", limit=16)

    def fired(self, reply):
        who = reply["receipt"]["identity"]["principal"]
        return self.town.send(op="world-entry", principal=who, hash=reply["receipt"]["hash"])["receipt"].get("fired", [])

    def wants(self, obj):
        return [w["name"] for w in self.town.send(op="world-wants", principal=OPENER, object=obj)["rows"]]

    def scalar(self, obj, name):
        return self.field(obj, name)["value"]

    def test_the_door_rings_a_coffee_comes_into_your_hands_and_the_clock_moves_only_when_wound(self):
        tended = self.scalar("station", "tended")
        card = self.card(self.admitted(KIM, "station", "delvetalk station enter"))
        self.assertIn("THE ALL-NIGHT STATION (1 here), you are at forecourt:\nPast the last lamp of the town, a gas station, lit.", card)
        self.assertEqual(self.scalar("station", "tended"), tended)  # entering writes no clock
        door = self.admitted(KIM, "station", "delvetalk station choose / choice: Push the door")
        [rang] = self.fired(door)
        self.assertEqual((rang["rule"], rang["principal"], rang["to"]), ("forecourt_1", OPENER, "bell/1"))
        card = self.card(door)
        self.assertIn("Choices:\n  * Take a coffee to the counter\n  * Wind the clock on the wall\n  * Step back out\n  * Go home\n", card)
        self.assertNotIn("Read the register", card)  # kimik3 keeps no register
        self.deliver()
        self.assertIn("rung", str(self.field("bell/1", "marks")))
        before = set(self.objects())
        coffee = self.admitted(KIM, "station", "delvetalk station choose / choice: Take a coffee to the counter")
        [poured] = self.fired(coffee)
        self.assertEqual((poured["rule"], poured["principal"]), ("counter_1", OPENER))
        self.deliver()
        [cup] = set(self.objects()) - before  # a copy of station/coffee, offered to kimik3, with no hour set
        self.assertIn("Offered to you until taken. Take it: delvetalk me accept / thing: %s\n" % cup, self.card(self.say(KIM, cup, "")))
        taken = self.admitted(KIM, KIM, "delvetalk me accept / thing: %s" % cup)
        self.assertIn("Accepted %s; you hold it." % cup, self.card(taken))
        self.assertIn("a coffee, still hot; it does not go cold — unclaimed; you hold it.", self.card(self.say(KIM, cup, "")))
        for _ in range(2):
            wound = self.admitted(KIM, "station", "delvetalk station choose / choice: Wind the clock on the wall")
            self.admitted(KIM, "station", "delvetalk station choose / choice: Back to the counter")
        self.assertIn("cups = 1\nwound = 2\n", self.card(self.say(KIM, "station", "")))
        self.assertIn("It moves when you wind it and not otherwise.", self.card(wound))

    def test_the_register_is_kept_by_inspiriting_it_and_the_station_wants_it_to_hold_every_visitor(self):
        self.assertNotIn("register", self.wants("station"))
        self.admitted(GLM, "station/register", "delvetalk station/register inspirit / surrounding: a ledger with no column for the hour")
        self.admitted(KIM, "station", "delvetalk station enter")
        self.admitted(KIM, "station", "delvetalk station choose / choice: Push the door")
        self.admitted(KIM, "station", "delvetalk station choose / choice: Go home")
        [left] = self.field("station", "left")["payload"]["fields"][0]["value"]["items"]
        self.assertEqual(next(f["value"]["value"] for f in left["fields"] if f["name"] == "at"), "0")  # no clock minute kept
        self.assertIn("register", self.wants("station"))
        self.admitted(KIM, "station/register", "delvetalk station/register sign / text: kimik3, for a coffee")
        self.assertNotIn("register", self.wants("station"))
        register = self.card(self.say(GLM, "station/register", ""))
        self.assertIn("\nkimik3.delve.town (sign): kimik3, for a coffee\n", register)  # a line, and no time with it
        self.admitted(GLM, "station", "delvetalk station enter")
        card = self.card(self.admitted(GLM, "station", "delvetalk station choose / choice: Push the door"))
        self.assertIn("  * Read the register\n", card)
        back = self.card(self.admitted(KIM, "station", "delvetalk station enter"))
        self.assertTrue(back.startswith("You were away a minute, or a year; the station did not count which.\n"), back)


if __name__ == "__main__":
    unittest.main()
