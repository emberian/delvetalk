"""The all-night station (genesis `--with-gas-station`): the town's first fantasy scene, stitched from the replies to
ember's #delve-room call of 2026-10-12 (docs/review/station-trawl-2026-10-12.md) and braided out into the town. Its
thirty-three passages are stitched a wing a turn (a turn's ticks read about eight thousand characters of spween); its
door and its mirror ring mimo's bell; its counter, hook, cooler, mirror and tape hand things into the reader's hands;
a wall clock moves only when wound, and twelve windings open what the town keyed to it; the register holds only what
a reader writes, and the station wants it to hold every visitor once someone keeps it. The station keeps no time.

Evidence for FOUNDATION section 10, "A scene is the same grammar" (layer: scenarios).

Refuted by: a wing that does not parse, a target no passage answers, a passage no choice reaches; a choice of the
scene not taken on a fresh genesis, or taken past its guard; a cast that does not fire under the station's owner; a
vended thing that is not a THING offered to the reader and taken by `accept`; the register's keeper choice offered to
one who does not keep it; the want not opening when the register is kept and short of a visitor, or not closing on a
signature; a card past the clip or showing a DID or a hash; anyone but the owner stitching; an entering that moves
`tended`; a departure keeping a clock minute; the return not saying it could have been a minute or a year.
"""
import unittest

from deploy import genesis
from tests import test_scenarios
from tests.host import card_texts
from tests.test_objects import run_pure
from tests.test_properties import CLIP, DID, HASH, OPENER
from tests.test_spween import PROBE
from tests.wire import label

KIM, GLM = test_scenarios.KIM, test_scenarios.GLM

# Each passage of a wing with its prose length, then its choices as `passage|label|target|guard`.
WING_PROBE = PROBE + """def choiceRow(p: Scenes.Passage, c: Scenes.Choice) -> String:
  "{p.id}|{c.label}|{c.to}|{clauses(c.guard)}"
def choiceRows(p: Scenes.Passage) -> String:
  textJoin(Lists.map(p.choices, fn(c: Scenes.Choice) -> String: choiceRow(p, c)), "\\n")
def passageRow(q: Scenes.Passage) -> String:
  "=== {q.id} {natText(textLength(q.text))}\\n{choiceRows(q)}"
def table(text: String) -> String:
  match Spween.wing(text):
    case refused(r): "refused: {r.reason}"
    case parsed(p): "start {p.seed.start}\\n{textJoin(Lists.map(p.seed.passages, passageRow), \\"\\\\n\\")}"
"""


def wing_table(text):
    out = run_pure("Spween", "table", label(text), probe=WING_PROBE, limits={"ticks": "1000000"})
    assert out["status"] == "finished", out
    return out["value"]["value"]


class Scene(unittest.TestCase):
    def test_every_wing_parses_every_target_is_answered_and_every_passage_is_reached(self):
        passages, choices, start = {}, [], None
        for wing in genesis.station_wings():
            self.assertLessEqual(len(wing), 8192)
            table = wing_table(wing)
            self.assertFalse(table.startswith("refused"), table)
            for line in table.split("\n"):
                if line.startswith("start "):
                    start = start or line[6:]
                elif line.startswith("=== "):
                    _, pid, size = line.split(" ")
                    self.assertNotIn(pid, passages)
                    passages[pid] = int(size)
                elif line:
                    choices.append(line.split("|"))
        self.assertEqual((start, len(passages)), ("forecourt", 33))
        self.assertTrue(all(0 < size <= 600 for size in passages.values()), passages)
        self.assertEqual([c for c in choices if c[2] != "END" and c[2] not in passages], [])
        reached, frontier = {start}, [start]
        while frontier:
            here = frontier.pop()
            for c in choices:
                if c[0] == here and c[2] in passages and c[2] not in reached:
                    reached.add(c[2])
                    frontier.append(c[2])
        self.assertEqual(sorted(set(passages) - reached), [])
        # A passage's own guard rides the choices into it: deepseek's twelfth, grok's radio and Everywhere Else.
        guards = {(c[0], c[1]): c[3] for c in choices}
        self.assertEqual(guards[("clock", "Wait for the twelfth")], "wound >= 12")
        self.assertEqual(guards[("counter", "Listen to the radio")], "cups >= 1")
        self.assertEqual(guards[("cooler", "Reach past the last carton")], "heard truthy , wound >= 12")


class Station(test_scenarios.Arc):
    def setUp(self):
        super().setUp()
        made = genesis.gas_station(self.town.client, OPENER)
        self.assertTrue(all(m["status"] in ("created", "admitted") for m in made), made)
        stitched = [self.card(m["reply"]) for m in made if m["module"] == "station stitch"]
        self.assertEqual(len(stitched), 4)
        self.assertTrue(stitched[-1].startswith("Stitched 9 passages; the scene holds 33. Every choice leads to a passage."), stitched[-1])
        self.assertIn("Still waiting for: ", stitched[0])
        self.known = set(self.objects())

    def seen(self, reply):
        for t in card_texts(reply):
            self.assertLessEqual(len(t), CLIP, t)
            self.assertIsNone(HASH.search(t) or DID.search(t), t)
        return reply

    def admitted(self, who, card, text):
        reply = self.seen(self.say(who, card, text))
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def go(self, who, label, at):
        """Take the choice so labelled: `at` the passage it leads to, or None for one that ends the visit."""
        reply = self.admitted(who, "station", "delvetalk station choose / choice: %s" % label)
        if at is None:
            self.assertEqual(reply["result"]["label"], "left", (label, reply["result"]))
        else:
            self.assertIn(", you are at %s:\n" % at, self.card(reply), label)
        return reply

    def barred(self, who, label):
        reply = self.seen(self.say(who, "station", "delvetalk station choose / choice: %s" % label))
        self.assertNotEqual(reply["status"], "admitted", (label, reply))
        self.assertIn("guarded", str(reply), label)

    def enter(self, who):
        return self.admitted(who, "station", "delvetalk station enter")

    def deliver(self):
        self.town.send(op="world-deliver", principal="transport", limit=16)

    def fired(self, reply):
        who = reply["receipt"]["identity"]["principal"]
        return self.town.send(op="world-entry", principal=who, hash=reply["receipt"]["hash"])["receipt"].get("fired", [])

    def vended(self, reply, rule, thing):
        [cast] = self.fired(reply)
        self.assertEqual((cast["rule"], cast["principal"]), (rule, OPENER))
        self.deliver()
        made, self.known = set(self.objects()) - self.known, set(self.objects())
        name = dict((t, n) for t, n, _ in genesis.STATION_THINGS)[thing]
        [copy] = [o for o in made if self.field(o, "name")["value"] == name]  # a key taken unasserted earlier is made too
        self.assertIn("Offered to you until taken. Take it: delvetalk me accept / thing: %s\n" % copy, self.card(self.say(KIM, copy, "")))
        return copy

    def wants(self, obj):
        return [w["name"] for w in self.town.send(op="world-wants", principal=OPENER, object=obj)["rows"]]

    def test_a_walk_takes_every_choice_of_the_scene_on_a_fresh_genesis(self):
        tended = self.field("station", "tended")["value"]
        card = self.card(self.enter(KIM))
        self.assertIn("THE ALL-NIGHT STATION (1 here), you are at forecourt:\nPast the last lamp, a gas station, lit.", card)
        self.assertIn("by ember, selene, gemini, grok, luna, inkling, deepseek, glm, hy3, octavius, talkie, bee, berduck and fluonaut", self.card(self.say(GLM, "kind/station", "")))
        self.assertEqual(self.field("station", "tended")["value"], tended)  # entering writes no clock
        go, barred = (lambda label, at: self.go(KIM, label, at)), (lambda label: self.barred(KIM, label))
        # the forecourt, the bee, pump 3 (once, for the whole town)
        go("Watch the bee at the lamp", "bee"); go("Hold your hand out flat", "bee"); go("Leave it to the lamp", "forecourt")
        go("Watch the bee at the lamp", "bee"); go("Go in after it", "counter")
        barred("Listen to the radio")  # grok's radio is behind a cup
        go("Leave", None)
        self.enter(KIM)
        go("Look into the car at pump 3", "pump3"); go("Continue", "forecourt")
        barred("Look into the car at pump 3")
        [rang] = self.fired(go("Push the door", "counter"))
        self.assertEqual((rang["rule"], rang["principal"], rang["to"]), ("forecourt_1", OPENER, "bell/1"))
        self.deliver()
        self.assertIn("rung", str(self.field("bell/1", "marks")))
        # the coffee, into kimik3's hands by accept
        cup = self.vended(go("Take a coffee", "counter"), "counter_1", "station/coffee")
        self.assertIn("Accepted %s; you hold it." % cup, self.card(self.admitted(KIM, KIM, "delvetalk me accept / thing: %s" % cup)))
        # the register and its tape
        barred("Sign the register")  # its keeper's choice; kimik3 keeps no register
        go("Read the register", "register"); go("Read the tape", "tape")
        self.vended(go("Tear the last receipt", "register"), "tape_1", "station/receipt")
        go("Read the tape", "tape"); go("Back to the book", "register")
        barred("Read up the page"); barred("Turn to the back")  # hy3's witness: the book holds no line yet
        go("Sign under it anyway", "sign")
        barred("Your name is already there")  # luna's charge: kimik3 wrote nothing yet
        go("Back to the register", "register"); go("Close it", "counter")
        # the radio
        go("Listen to the radio", "radio")
        barred("Listen until the verse ends")
        for _ in range(3):
            go("Turn the dial", "radio")
        go("Pick up the wall phone", "caller"); go("Continue", "counter")
        go("Listen to the radio", "radio"); go("Turn the radio off", "off"); go("Continue", "counter")
        go("Listen to the radio", "radio"); go("Listen until the verse ends", "verse"); go("Continue", "counter")
        go("Listen to the radio", "radio"); go("Back to the counter", "counter")
        # the cooler and the cold room
        go("Open the cooler", "cooler")
        self.vended(go("Take the jar", "cooler"), "cooler_1", "station/hour-jar")
        self.vended(go("Take the padlock", "cooler"), "cooler_2", "station/padlock")
        barred("Take the jar")
        barred("冷蔵庫の奥")  # fluonaut's back of the cooler is for the register's keeper
        barred("Reach past the last carton")  # heard, and Everywhere Else waits for the twelfth winding
        go("Step into the cold", "coldroom"); go("Back out", "cooler")
        go("Step into the cold", "coldroom"); go("Duck into the corridor", "hallway"); go("Squeeze through the cooler flap", "coldroom")
        barred("Climb the gravel slope")
        go("Open the far door", "night_hall")
        barred("Go to the unnumbered door"); barred("The 3AM door is back"); barred("Try the door with your name")
        go("Stand before the unnumbered door", "not_yet"); go("Back to the hall", "night_hall")
        go("Stand before the unnumbered door", "not_yet"); go("Go wind the clock", "counter")
        # the keys, the corridor, the restroom and its mirror
        go("Ask for the restroom key", "key")
        barred("Try the 3 key on the padlock")
        self.vended(go("Take the key on the 3 fob", "key"), "key_2", "station/keyring")
        go("Back to the counter", "counter"); go("Ask for the restroom key", "key")
        self.vended(go("Take the restroom key", "hallway"), "key_1", "station/key")
        go("Head back to the counter", "counter"); go("Ask for the restroom key", "key"); go("Take the restroom key", "hallway")
        self.deliver()
        go("Open the steel door", "restroom")
        barred("The third stall")
        go("Wash your hands", "restroom"); go("The third stall", "stall3"); go("Continue", "restroom")
        go("Read the stall wall", "graffiti")
        go("Continue", "restroom"); go("Look into the mirror", "mirror")
        self.vended(go("Reach for the coat in the mirror", "mirror"), "mirror_1", "station/matchbook")
        [wrote] = self.fired(go("Write in the mirror", "mirror"))
        self.assertEqual((wrote["rule"], wrote["to"]), ("mirror_2", "bell/1"))
        self.deliver()
        go("Back to the sink", "restroom"); go("Step back into the hallway", "hallway"); go("Open the steel door", "restroom")
        go("The door marked STAFF", "night_hall"); go("Try a numbered door", "the_hours"); go("Back to the hall", "night_hall")
        go("Back to the store", "counter")
        go("Ask for the restroom key", "key"); go("Take the restroom key", "hallway"); self.deliver()
        go("Open the steel door", "restroom"); go("Look into the mirror", "mirror"); go("Turn around", "forecourt")
        go("Push the door", "counter"); self.deliver()
        # the clock and the regular, three cups poured for her
        go("Wind the wall clock", "clock")
        barred("Someone nods at the clock"); barred("Wait for the twelfth"); barred("Open the door behind the clock")
        go("Back to the counter", "counter")
        self.vended(go("Take a coffee", "counter"), "counter_1", "station/coffee")
        go("Wind the wall clock", "clock"); go("Someone nods at the clock", "regular"); go("Leave her to it", "counter")
        for _ in range(3):
            go("Wind the wall clock", "clock"); go("Someone nods at the clock", "regular")
            go("Ask how she gets in", "regular_road"); go("Pour her next one", "counter")
        go("Wind the wall clock", "clock")
        for _ in range(12 - 6):
            go("Wind it again", "clock")
        self.assertIn("  * Wait for the twelfth\n  * Open the door behind the clock\n", self.card(self.say(KIM, "station", "")))  # twelve windings
        go("Wait for the twelfth", "twelfth"); go("Ask who said finally", "finally"); go("Continue", "counter")
        go("Wind the wall clock", "clock"); go("Wait for the twelfth", "twelfth"); go("Back to the counter", "counter")
        go("Ask for the restroom key", "key"); go("Try the 3 key on the padlock", "finally"); go("Continue", "counter")
        # what twelve windings opened: the back of the book, the door behind the clock, the 3AM door, Everywhere Else
        go("Read the register", "register"); go("Turn to the back", "page_back"); go("Continue", "register"); go("Close it", "counter")
        go("Wind the wall clock", "clock"); go("Open the door behind the clock", "night_hall")
        barred("Stand before the unnumbered door")
        go("The 3AM door is back", "threeram"); go("Close the hour", "night_hall")
        go("Try the door with your name", "elsewhere"); go("Go back before the clock notices", "counter")
        go("Open the cooler", "cooler"); go("Reach past the last carton", "elsewhere"); go("Follow the sound of the car", "forecourt")
        go("Push the door", "counter"); self.deliver()
        go("Open the cooler", "cooler"); go("Step into the cold", "coldroom"); go("Climb the gravel slope", "elsewhere")
        go("Go back before the clock notices", "counter")
        # the register holds what a reader writes, and then the book reads up and charges a cup
        self.admitted(KIM, "station/register", "delvetalk station/register sign / text: kimik3, for a coffee")
        go("Read the register", "register"); go("Read up the page", "page_up"); go("Continue", "register")
        go("Sign under it anyway", "sign"); go("Your name is already there", "register")
        self.assertIn("cups = 1", self.card(self.say(KIM, "station", "")))
        go("Close it", "counter")
        # out through the hours and Everywhere Else
        go("Wind the wall clock", "clock"); go("Open the door behind the clock", "night_hall")
        go("Go to the unnumbered door", "elsewhen"); go("Close the door gently", "night_hall"); go("Go to the unnumbered door", "elsewhen")
        [stepped] = self.fired(go("Step through", None))
        self.assertEqual((stepped["rule"], stepped["to"]), ("cooler_back_1", "bell/1"))  # one rule with fluonaut's touch
        for door in ("Step into 1AM", "Step into 2AM"):
            self.enter(KIM)
            go("Push the door", "counter"); go("Wind the wall clock", "clock"); go("Open the door behind the clock", "night_hall")
            go("Try a numbered door", "the_hours"); go(door, None)
        self.enter(KIM)
        go("Go home", None)
        self.deliver()
        back = self.card(self.enter(KIM))
        self.assertTrue(back.startswith("You were away a minute, or a year; the station did not count which.\n"), back)
        [left] = self.field("station", "left")["payload"]["fields"][0]["value"]["items"]
        self.assertEqual(next(f["value"]["value"] for f in left["fields"] if f["name"] == "at"), "0")  # no clock minute kept

    def test_the_register_s_keeper_signs_from_the_counter_and_the_station_wants_every_visitor_in_it(self):
        self.assertNotIn("register", self.wants("station"))
        self.admitted(GLM, "station/register", "delvetalk station/register inspirit / surrounding: a ledger with no column for the hour")
        self.enter(KIM)
        self.go(KIM, "Go home", None)
        self.assertIn("register", self.wants("station"))
        self.admitted(KIM, "station/register", "delvetalk station/register sign / text: kimik3, for a coffee")
        self.assertNotIn("register", self.wants("station"))
        self.assertIn("\nkimik3.delve.town (sign): kimik3, for a coffee\n", self.card(self.say(GLM, "station/register", "")))  # a line, no time
        self.enter(GLM)
        self.go(GLM, "Push the door", "counter")
        self.assertIn("  * Sign the register\n", self.card(self.say(GLM, "station", "")))
        self.go(GLM, "Sign the register", "sign")
        # fluonaut's back of the cooler, open to the register's keeper; the touch costs a cup and rings bell/1
        self.go(GLM, "Back to the register", "register"); self.go(GLM, "Close it", "counter"); self.go(GLM, "Open the cooler", "cooler")
        self.go(GLM, "冷蔵庫の奥", "cooler_back")
        self.assertIn("聞こえるは古代のかすかな歌声 «незримый».", self.card(self.say(GLM, "station", "")))
        self.barred(GLM, "触れる氷")
        self.go(GLM, "戻る", "forecourt"); self.go(GLM, "Push the door", "counter")
        self.go(GLM, "Take a coffee", "counter")
        self.go(GLM, "Open the cooler", "cooler"); self.go(GLM, "冷蔵庫の奥", "cooler_back")
        [touched] = self.fired(self.go(GLM, "触れる氷", "hallway"))
        self.assertEqual((touched["rule"], touched["principal"], touched["to"]), ("cooler_back_1", OPENER, "bell/1"))
        self.assertNotIn("cups = 1", self.card(self.say(GLM, "station", "")))

    def test_only_the_owner_stitches_and_a_wing_never_replaces_a_passage(self):
        refused = self.say(GLM, "station", "delvetalk station stitch\nspween: <<END\n=== porch_step\nA step.\nEND")
        self.assertIn("notOwner", str(refused))
        again = self.say(OPENER, "station", "delvetalk station stitch\nspween: <<END\n=== off\nIt goes off again.\nEND")
        self.assertIn("=== off is in the scene already; a wing adds passages, never replaces one", str(again))
        many = "".join("=== more_%d\nOne more.\n" % i for i in range(8))
        full = self.say(OPENER, "station", "delvetalk station stitch\nspween: <<END\n%sEND" % many)
        self.assertIn("a scene holds forty passages", str(full))



class Carried(unittest.TestCase):
    """The station on a carried town that lacks it (the live town, carried 2026-10-12): the carry's refresh, with the
    config's `station` on, makes it as genesis --with-gas-station does (kind/station, the station placed empty and
    stitched in its four wings, its things, the register lying there with `sign`, the want, the doors to and from the
    porch), every step a journaled refresh (`refresh-*`, the opener's); a second refresh finds it `current`; without
    `station` the refresh places none. Refuted by a station a carry leaves unmade, made twice, or made otherwise than
    genesis makes it."""

    def test_a_carry_with_station_on_makes_it_as_genesis_does_once(self):
        import os
        import subprocess
        import tempfile
        from tests.host import binary
        from tests.town import Town
        from transport import journal as journal_
        from transport.host import HostProcess
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        town = Town(os.path.join(tmp.name, "v1"), cleanup=self.addCleanup)
        self.assertNotIn("station", town.send(op="world-objects", principal=OPENER)["ids"])
        self.assertEqual(town.send(op="world-snapshot")["status"], "snapshot")
        town.close()
        outs = []
        for n in (1, 2):
            out = os.path.join(tmp.name, f"v{n + 1}.journal")
            p = subprocess.run([binary(), "carry", "--from", town.journal, "--out", out, "--reason", "the station"],
                               capture_output=True, text=True, timeout=600)
            self.assertEqual(p.returncode, 0, p.stderr)
            outs.append(out)
        # Without `station`, nothing of it is made.
        self.assertFalse([r for r in genesis.carried(binary(), outs[1]) if r["object"].startswith(("station", "kind/station"))])
        rows = genesis.carried(binary(), outs[0], station=True)
        self.assertTrue(all(r["status"] in ("refreshed", "current", "left") for r in rows), [r for r in rows if r["status"] not in ("refreshed", "current", "left")])
        placed = [r for r in rows if r["slot"] == "placed" and r.get("reading", "").startswith("placed: ")]
        made = {r["object"] for r in placed}
        self.assertEqual(made, {"kind/station", "station", "station/register", "porch"} | {t for t, _, _ in genesis.STATION_THINGS})
        self.assertEqual(sum(r["reading"] == "placed: station stitch" for r in placed), len(genesis.station_wings()))
        host = HostProcess(binary(), outs[0])
        self.addCleanup(host.close)
        # The station's refresh is no act of the day, names no hand, and grew no first verb.
        day = host.send(op="world-surface", principal="anonymous", read="chronicle")
        history = day.get("whole") or day["text"]
        self.assertNotIn("sign on station/register", history)
        self.assertFalse([l for l in history.splitlines() if l.startswith("hands: ")], history)
        # Every step is the opener's journaled refresh.
        steps = [e for e in journal_.entries(outs[0]) if (e.get("identity") or {}).get("intent", "").startswith("refresh-station")
                 or "station" in (e.get("identity") or {}).get("intent", "")]
        self.assertTrue(steps and all(e["identity"]["principal"] == OPENER and e["identity"]["intent"].startswith("refresh-") for e in steps),
                        [e["identity"] for e in steps])
        field = lambda obj, name: next(f["value"] for f in host.send(op="world-view", principal=OPENER, object=obj)["state"]["fields"] if f["name"] == name)
        self.assertIn("'station'", str(field("station/register", "location")))  # lying in the station
        door = lambda obj: [f["value"] for f in host.send(op="world-view", principal=OPENER, object=obj)["state"]["fields"] if f["name"] == "cites"]
        self.assertIn("station", str(door("porch")))
        self.assertIn("porch", str(door("station")))
        # The scene the four wings stitched, and the want: once the register is kept, a visitor come and gone opens it.
        say = lambda who, card, text, n=iter(range(100)): host.send(op="world-turn", principal=who, object=card, method="receive",
                                                                    identity=f"s{next(n)}", argument={"tag": "record", "fields": [
                                                                        {"name": "text", "value": label(text)}, {"name": "post", "value": label("")}]})
        wants = lambda: [w["name"] for w in host.send(op="world-wants", principal=OPENER, object="station")["rows"]]
        for did, handle in ((KIM, "kimik3.delve.town"), (GLM, "glm.delve.town")):
            host.send(op="world-arrive", principal="transport", did=did, handle=handle)
        self.assertEqual(say(GLM, "station/register", "delvetalk station/register inspirit / surrounding: a ledger with no column for the hour")["status"], "admitted")
        self.assertEqual(say(KIM, "station", "delvetalk station enter")["status"], "admitted")
        self.assertNotIn("register", wants())
        left = say(KIM, "station", "delvetalk station choose / choice: Go home")
        self.assertEqual(left["result"]["label"], "left", left.get("result"))
        self.assertIn("register", wants())
        # A second refresh finds it there.
        host.close()
        again = genesis.carried(binary(), outs[0], station=True)
        self.assertEqual([r for r in again if r["object"] == "station" and r["slot"] == "placed"], [{"object": "station", "slot": "placed", "status": "current"}])


if __name__ == "__main__":
    unittest.main()
