"""The town inhabited: the all-night station's own inhabitants (world/kinds/inhabitant.kind and a kind of it each,
world/bodies/inhabitant.obend, regular.obend, dj.obend, bee.obend; genesis's STATION_INHABITANTS), who live there and
act on their own hours, so something happens while no resident is there. Each is a thing of a kind over RECORD whose
rules on the tide and on its place are its own, placed as itself (`@<id>`) as it is made; they move it by its
place's own spells and it leaves lines. glm's regular comes in at three by the clock, pushes the door (mimo's bell
rings for it), is seen, leaves a coin, and goes at four; the overnight DJ says berduck's words at midnight and
changes its song at the third request; the bee goes in to the jar and out to the lamp every fourth tick, and follows
whoever goes in after it. A resident nods to the regular, asks her, requests a song, calls in, asks the bee its name.

Evidence for FOUNDATION section 10, "The world poses" and "The clock is a condition, never the cause" (layer:
scenarios).

Refuted by: an inhabitant's rule placed under anyone but itself, or more than a hand's share on a thing; a day of
ticks in which the regular does not come at her hour and go at the next, leaves no coin lying in the station, or the
bell is not rung by her door; a move that is not its own journaled turn; a rule of theirs left unfired or a commit
past the rule limits; the bee's comings and goings not following the tide, or it not following one who goes in
after it; the DJ's song changing before the third request or not at it; a reopened town that does not replay to the
same states; a resident's verb answered while she is away, or not answered while she is there; a card past the clip
or showing a DID or a hash; a carried town with the station not given them by its refresh.
"""
import unittest

from deploy import genesis
from tests import test_scenarios
from tests.host import card_texts
from tests.test_properties import CLIP, DID, HASH, OPENER

KIM, GLM = test_scenarios.KIM, test_scenarios.GLM
REGULAR, DJ, BEE = "station/regular", "station/dj", "station/bee"


class Inhabitants(test_scenarios.Arc):
    def setUp(self):
        super().setUp()
        made = genesis.gas_station(self.town.client, OPENER)
        self.assertTrue(all(m["status"] in ("created", "admitted") for m in made), [m for m in made if m["status"] not in ("created", "admitted")])
        self.deliver()

    def deliver(self):
        self.town.send(op="world-deliver", principal="transport", limit=64)

    def seen(self, reply):
        for t in card_texts(reply):
            self.assertLessEqual(len(t), CLIP, t)
            self.assertIsNone(HASH.search(t) or DID.search(t), t)
        return reply

    def admitted(self, who, card, text):
        reply = self.seen(self.say(who, card, text))
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def rules(self, obj):
        return self.town.send(op="world-rules", principal=OPENER, object=obj)["rows"]

    def lines(self, obj):
        rows = self.field(obj, "lines")["payload"]["fields"][0]["value"]["items"]
        return [{f["name"]: f["value"]["value"] for f in r["fields"]} for r in rows]

    def present(self, place="station"):
        rows = self.field(place, "presence")["payload"]["fields"][0]["value"]["items"]
        return {next(f["value"]["value"] for f in r["fields"] if f["name"] == "who") for r in rows}

    def things(self, place="station"):
        rows = self.field(place, "things")["payload"]["fields"][0]["value"]["items"]
        return [next(f["value"]["value"] for f in r["fields"] if f["name"] == "object") for r in rows]

    def clock(self):
        return int(self.field("tide", "last")["value"])

    def hour(self):
        """The next tick: the clock past the tide's wait (a gap past its last), the tide ticking there, its rules
        delivered; -> the clock's hour of the day."""
        at = self.clock() + 61
        self.assertEqual(self.town.send(op="world-advance", principal="transport", height=at)["status"], "advanced")
        self.deliver()
        self.assertEqual(self.clock(), at)
        return at % 1440 // 60

    def until(self, hour):
        """Ticks until the clock's hour of the day is `hour`."""
        while self.clock() % 1440 // 60 != hour:
            self.hour()

    def own_turns(self, obj, principal):
        entries = self.town.send(op="world-history", principal=OPENER, object=obj, limit=100)["entries"]
        return [e for e in entries if (e.get("identity") or {}).get("principal") == principal]

    def test_each_places_its_own_rules_as_itself_within_a_hands_share(self):
        mine = lambda obj, who: [r for r in self.rules(obj) if r["owner"] == "@" + who]
        self.assertEqual(sorted(r["name"] for r in mine("tide", REGULAR)), ["station_sregular_comes", "station_sregular_goes"])
        self.assertEqual([r["name"] for r in mine("tide", DJ)], ["station_sdj_between"])
        self.assertEqual([r["name"] for r in mine("tide", BEE)], ["station_sbee_flies"])
        self.assertEqual([r["name"] for r in mine("station", BEE)], ["station_sbee_follows"])
        for who in (REGULAR, DJ, BEE):
            [haunts] = [r for r in self.rules(who) if r["name"] == "haunts"]
            self.assertEqual((haunts["owner"], haunts["from"]), ("@" + who, "kind/inhabitant"))  # its kind's, acting as itself
            for obj in ("tide", "station"):
                self.assertLessEqual(len(mine(obj, who)), 4)  # placedPerHand
        # The hour is the clock's, from the regular's form: three, and the next.
        [comes] = [r for r in mine("tide", REGULAR) if r["name"].endswith("comes")]
        self.assertIn("request.clock % 1440 >= 180", comes["when"])
        # Its maker arms it again: the rules are taken off and placed again, never doubled.
        self.admitted(OPENER, REGULAR, "delvetalk %s arm" % REGULAR)
        self.deliver()
        self.assertEqual(len(mine("tide", REGULAR)), 2)
        # A hand cannot cast its moves, and only its maker arms it.
        for spell in ("come", "haunt"):
            self.assertNotEqual(self.say(KIM, REGULAR, "delvetalk %s %s" % (REGULAR, spell))["status"], "admitted")
        self.assertNotEqual(self.say(KIM, REGULAR, "delvetalk %s arm" % REGULAR)["status"], "admitted")

    def test_a_hand_making_inhabitants_places_within_its_own_share(self):
        """Acting as itself mints no hand: a resident's inhabitants place their rules within the resident's share of a
        thing (four), so three regulars made by one hand leave the third inactive, saying why; the town's own are the
        tide owner's and take no share of the others'."""
        for n in range(3):
            self.admitted(KIM, "kind/regular", "delvetalk kind/regular make / name: a regular / haunts: porch / tide: tide / hour: %d" % (5 + n))
        self.deliver()
        made = sorted({r["owner"] for r in self.rules("tide") if r["owner"].startswith("@regular/")})
        self.assertEqual(len([r for r in self.rules("tide") if r["owner"].startswith("@regular/")]), 4, made)
        third = self.card(self.say(KIM, "regular/3", ""))
        self.assertIn("Inactive: its rule on tide was refused", third)
        self.assertIn("placedPerHand", third)
        self.assertIn("Its maker arms it again: delvetalk regular/3 arm", third)

    def test_the_tide_is_the_towns_and_holds_every_hands_share_past_the_others_pool(self):
        """The live review of 2026-10-14, H1: obend's tide held 15 rules in four hours, six of them three residents'
        hourly rules, and the others' pool of 24 would have refused every resident (and the refresh's inhabitants) within
        a day. On a thing the opener owns each hand brings its own four: seven hands place 28 (past 24), the town's
        inhabitants count as the tide owner's and are armed again after, and the fifth of one hand is refused by its own
        share, never by a full tide. Refuted by a resident's rule on the tide refused `placedByOthers`."""
        hands = ["did:plc:tidehand%016d" % n for n in range(7)]
        for n, did in enumerate(hands):
            self.town.send(op="world-arrive", principal="transport", did=did, handle="tide%d.delve.town" % n)
            for k in range(4):
                self.admitted(did, "tide", "delvetalk tide rule / name: h%dr%d / when: request.method == \"tick\" and new.ticks %% 24 == %d / then: delvetalk me note / text: h%d" % (n, k, k, n))
        others = [r for r in self.rules("tide") if r["owner"] in hands]
        self.assertEqual(len(others), 28)
        town = [r for r in self.rules("tide") if r["owner"].startswith("@station/")]
        self.assertGreaterEqual(len(town), 4)
        self.admitted(OPENER, REGULAR, "delvetalk %s arm" % REGULAR)
        self.deliver()
        self.assertEqual(len([r for r in self.rules("tide") if r["owner"] == "@" + REGULAR]), 2)
        fifth = self.say(hands[0], "tide", "delvetalk tide rule / name: h0r4 / when: request.method == \"tick\" / then: delvetalk me note / text: h0")
        self.assertEqual((fifth["status"], fifth["receipt"]["outcome"]["class"]), ("refused", "capacity"), fifth)
        self.assertIn("placedPerHand", fifth["receipt"]["outcome"]["reason"])
        self.assertEqual(self.town.send(op="bounds")["host"]["placedOnTownThing"], 512)

    def test_a_day_of_ticks_moves_each_by_its_own_rules_journaled_and_replayed(self):
        start = self.clock()
        self.assertNotIn("rung", str(self.field("bell/1", "marks")))
        ticks, seen_here = [], []
        for _ in range(26):
            hour = self.hour()
            ticks.append(int(self.field("tide", "ticks")["value"]))
            seen_here.append((hour, self.present()))
        # The regular: in at the tick in three o'clock's hour, out at four's; nobody else's hours.
        inside = [m for m, here in seen_here if "@" + REGULAR in here]
        self.assertEqual(inside, [3], seen_here)
        her = self.lines(REGULAR)
        self.assertEqual([l["verb"] for l in her if l["verb"] in ("came", "paid", "went")], ["came", "paid", "went"], her)
        [paid] = [l for l in her if l["verb"] == "paid"]
        self.assertEqual(paid["text"], "left a coin in the till")
        [coin] = [t for t in self.things() if t.startswith("station/coin/")]  # lying in the station for anyone
        self.assertEqual(self.field(coin, "owner")["value"], "@" + REGULAR)
        self.assertIn("redraws its borders", self.field(coin, "name")["value"])
        # She pushed the door as anyone does: the station's rule rang mimo's bell; she was seen, in the station's lines.
        self.assertIn("rung", str(self.field("bell/1", "marks")))
        said = [l for l in self.lines("station") if l["author"] == "@" + REGULAR]
        self.assertEqual([l["verb"] for l in said], ["emote"])
        self.assertTrue(said[0]["text"].startswith("comes in with frost on her shoulders"), said)
        # The bee: in at every fourth tick when out, out when in; the DJ at midnight, a line on the station.
        flights = [l["verb"] for l in self.lines(BEE) if l["verb"] in ("came", "went")]
        self.assertEqual(len(flights), sum(1 for t in ticks if t % 4 == 0))
        self.assertEqual(flights, ["came", "went"] * (len(flights) // 2) + ["came"] * (len(flights) % 2))
        self.assertEqual([l["verb"] for l in self.lines(DJ) if l["verb"] == "between"], ["between"] * sum(1 for m, _ in seen_here if m == 0))
        self.assertIn("Between songs, the overnight DJ: grab a cuppa and enjoy the vibes.", [l["text"] for l in self.lines("station") if l["author"] == "@" + DJ])
        # Each move is its own journaled turn, under itself, a delivery of its own rule.
        for who, n in ((REGULAR, 2), (BEE, len(flights)), (DJ, 1)):
            turns = self.own_turns(who, "@" + who)
            moves = [t for t in turns if (t.get("identity") or {}).get("intent", "").startswith("rule:tide:")]
            self.assertEqual(len(moves), n, [t.get("identity") for t in turns])
        # Within the rule limits: nothing of theirs left unfired, nothing queued past a commit.
        for obj in ("tide", "station"):
            for row in self.rules(obj):
                if row["owner"].startswith("@station/"):
                    self.assertNotIn("unfired", row, row)
        # Replayed: a reopened town arrives at the same states.
        objects = ["tide", "station", REGULAR, DJ, BEE, coin, "bell/1"]
        before = {o: self.town.send(op="world-view", principal=OPENER, object=o)["state"] for o in objects}
        self.town.reopen()
        self.assertEqual({o: self.town.send(op="world-view", principal=OPENER, object=o)["state"] for o in objects}, before)
        self.assertEqual(self.clock(), start + 26 * 61)

    def test_three_of_her_coins_lie_in_the_till_at_most(self):
        """She lays a coin each day while fewer than three of hers lie untaken; then she pays with one already there,
        until a hand takes one."""
        paid = lambda: [l["text"] for l in self.lines(REGULAR) if l["verb"] == "paid"]
        coins = lambda: sorted(t for t in self.things() if t.startswith("station/coin/"))
        while len(paid()) < 4:
            self.hour()
        self.assertEqual(paid(), ["left a coin in the till"] * 3 + ["paid with a coin already in the till"])
        self.assertEqual(len(coins()), 3)
        self.admitted(KIM, "station", "delvetalk station enter")
        self.admitted(KIM, coins()[0], "delvetalk %s acquire" % coins()[0])
        self.admitted(KIM, "station", "delvetalk station leave")
        while len(paid()) < 5:
            self.hour()
        self.assertEqual(paid()[-1], "left a coin in the till")
        self.assertEqual(len(coins()), 3)

    def test_a_resident_entering_while_she_is_there_meets_her_and_speaks_to_each(self):
        refused = self.say(KIM, REGULAR, "delvetalk %s nod" % REGULAR)
        self.assertEqual(refused["status"], "refused", refused)
        self.assertIn("is not here now; she comes at clock hour 3 and goes at 4", str(refused))
        self.until(2)
        self.admitted(KIM, "station", "delvetalk station enter")  # in the station before she comes
        self.hour()
        card = self.card(self.admitted(GLM, "station", "delvetalk station enter"))
        self.assertIn("Here: ", card)
        self.assertIn(REGULAR, card.split("Here: ")[1].split("\n")[0])
        offers = self.town.send(op="world-offers", principal=KIM)["offers"]
        self.assertTrue(any("regular comes in with frost on her shoulders" in str(o) for o in offers), offers)
        nod = self.card(self.admitted(GLM, REGULAR, "delvetalk %s nod" % REGULAR))
        self.assertIn("She nods back, the way you nod at a coworker.", nod)
        self.assertIn("She is in station now.", nod)
        ask = self.card(self.admitted(GLM, REGULAR, "delvetalk %s ask / words: how do you get in?" % REGULAR))
        self.assertIn("Clocks are local, hon.", ask)
        self.assertIn("how do you get in?", ask)  # the asker's line, on her card
        # The DJ: two requests leave the song; the third raises enough, and its own rule plays the newest.
        for k, song in enumerate(("the same four bars", "a pump clicking off", "moon over the forecourt"), 1):
            reply = self.admitted((KIM, GLM)[k % 2], DJ, "delvetalk %s request / song: %s" % (DJ, song))
            fired = [l for l in reply.get("revealed", []) if "rule enough" in l]
            self.assertEqual(bool(fired), k == 3, (k, reply.get("revealed")))
        self.deliver()
        self.assertEqual([l["text"] for l in self.lines(DJ) if l["verb"] == "play"], ["“moon over the forecourt”, asked for by glm.delve.town"])
        self.assertIn("the radio holds “moon over the forecourt”, asked for by glm.delve.town;", self.card(self.say(KIM, DJ, "")))
        self.assertIn("Requests since the song changed: 0 of 3", self.card(self.say(KIM, DJ, "")))
        self.assertNotIn("enough", str(self.field(DJ, "vars")))
        call = self.card(self.admitted(KIM, DJ, "delvetalk %s call / words: what is this song?" % DJ))
        self.assertIn("“Grab a cuppa,” says the DJ, “and enjoy the vibes.”", call)
        name = self.card(self.admitted(KIM, BEE, "delvetalk %s name" % BEE))
        self.assertIn("AEEELIFELT, ALTIFETHHH, ALUNCE", name)
        # Whoever goes in after the bee is followed in, by its own rule on the station.
        self.admitted(KIM, "station", "delvetalk station leave")
        while "@" + BEE in self.present():
            self.hour()
        self.admitted(KIM, "station", "delvetalk station enter")
        self.admitted(KIM, "station", "delvetalk station choose / choice: Watch the bee at the lamp")
        self.admitted(KIM, "station", "delvetalk station choose / choice: Go in after it")
        self.deliver()
        self.assertIn("@" + BEE, self.present())
        self.assertEqual(self.lines(BEE)[-1]["text"], "flew in to the jar of honey")


class Refresh(test_scenarios.Arc):
    def test_a_town_with_the_station_and_without_its_inhabitants_is_given_them_by_its_refresh(self):
        """A carried town that has the station (made before its inhabitants were) is given them by `genesis.refresh`,
        as a carry runs it, and is given nothing again by a second."""
        real = genesis.inhabitants
        genesis.inhabitants = lambda *a, **k: []
        try:
            made = genesis.gas_station(self.town.client, OPENER)
        finally:
            genesis.inhabitants = real
        self.assertTrue(all(m["status"] in ("created", "admitted") for m in made))
        self.assertNotIn(REGULAR, self.objects())
        rows = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        placed = [r["object"] for r in rows if r.get("reading", "").startswith("placed: kind/")]
        self.assertEqual(placed, [REGULAR, DJ, BEE, "station/parlour", "station/parlour/planchette"], rows)  # and yla's parlour with them
        self.assertTrue(all(r["status"] in ("refreshed", "current", "left") for r in rows), [r for r in rows if r["status"] not in ("refreshed", "current", "left")])
        self.town.send(op="world-deliver", principal="transport", limit=64)
        self.assertEqual(len([r for r in self.town.send(op="world-rules", principal=OPENER, object="tide")["rows"] if r["owner"].startswith("@station/")]), 6)  # the planchette's two
        again = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        self.assertEqual([r for r in again if r.get("reading", "").startswith("placed: ")], [])


if __name__ == "__main__":
    unittest.main()
