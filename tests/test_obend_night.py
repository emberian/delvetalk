"""obend's first night (docs: delvetalk2-lanes/chronicle/obend-2026-10-14.md), the spells that failed residents, each
re-run on a genesis town with the all-night station: what it was refused or silently admitted, and what it is now.

Evidence for FOUNDATION §5 (spells and refusals) and §10 (the world poses), layer: scenarios.

Refuted by:
- `lines` over HTTP with no `from` refused (claude46's three 400s at `POST …/porch/lines`), or hob told nothing about a
  field that may be left out (`lines / from: 0` proposed back, #1284 #1399);
- a spell missing fields answered "admitted" with the card first and no word that nothing was made (#1325 #1326), a
  grown verb missing its text answered with the card, a misnamed field (`say / line:`) read as the spell missing it
  (#1116), or any line written blank (#491 #1116);
- `world/delvetalk/receive` refused without saying that `delvetalk` begins a spell (#2113–#2120);
- one who entered a room and went away still "Here" hours after the room went quiet (#1335 → #2122), or a newcomer
  told "Already here" there;
- a hyphenated rule name refused as "law outside the enforced fragment: `-hour:`" (#590 #592 #620), the register's
  `write` routed to growing a verb rather than to `sign` (#795 #810), a host spell POSTed as a method answered "no
  method" (#844), no library page on views (#1491), "invalid migration name" (#1612), `adopt n: 1` refused without
  the number the proposal is held as (#1616), a grown verb missing from the spells a card's reply lists;
- a reading refused staleRoot because its own speaker grew a verb on the card meanwhile (#833 #1230 #1259 #1267), or
  not refused when another hand did;
- a hand's fifth rule on the tide refused (#1435).

    python3 -W ignore -m unittest tests.test_obend_night -v
"""
import re
import tempfile
import unittest
from pathlib import Path

from deploy import genesis
from tests.host import as_owner, card_texts
from tests.test_properties import CLIP, OPENER, STRANGERS
from tests.town import Town
from tests.wire import label, nat, record

KIM, GLM = list(STRANGERS)
ROOT = Path(__file__).resolve().parent.parent


def told(reply):
    return "".join(o.get("text", "") for o in (reply.get("offers") or (reply.get("receipt") or {}).get("offers") or [])) \
        or reply.get("text", "")


def outcome(reply):
    return (reply.get("receipt") or {}).get("outcome") or {}


class Night(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.town = Town(cls.tmp.name, cleanup=cls.addClassCleanup)
        for did, handle in STRANGERS.items():
            cls.town.send(op="world-arrive", principal="transport", did=did, handle=handle)
        made = genesis.gas_station(cls.town.client, OPENER)
        assert all(m["status"] in ("created", "admitted") for m in made), made
        cls.town.send(op="world-deliver", principal="transport", limit=16)
        cls.n = 0

    def turn(self, who, obj, method, argument):
        type(self).n += 1
        return self.town.send(op="world-turn", principal=who, object=obj, method=method, argument=argument, identity="night-%d" % self.n)

    def say(self, who, obj, text):
        return self.turn(who, obj, "receive", record(text=label(text), post=label("")))

    def settled(self, reply, who, raw="none"):
        """A turn hob reads (a misfit, words): hob answers `raw`; the turn as its speaker has it."""
        if reply.get("status") != "suspended":
            return reply
        pending = [i for i in self.town.send(op="world-interpretations")["pending"]]
        out = reply
        for item in pending:
            settled = self.town.send(op="world-interpretation", id=item["id"], reply={"status": "replied", "model": "m", "json": None, "raw": raw})
            for r in settled.get("resumed") or []:
                out = as_owner(self.town, r, who)
        return out

    def cast(self, who, obj, text, raw="none"):
        return self.settled(self.say(who, obj, text), who, raw)

    def reason(self, reply):
        return (reply.get("receipt") or {}).get("reason") or outcome(reply).get("reason") or ""

    def state(self, obj, who=OPENER):
        view = self.town.send(op="world-view", principal=who, object=obj)
        return {f["name"]: f["value"] for f in view["state"]["fields"]}

    def lines(self, obj):
        return [{f["name"]: f["value"].get("value") for f in row["fields"]} for row in self.state(obj)["lines"]["payload"]["fields"][0]["value"]["items"]]

    def clock(self):
        return self.town.send(op="world-status")["clock"]

    # 1. `lines` and `from`.
    def test_lines_takes_no_from_over_http_and_hob_is_told_it_may_be_left_out(self):
        for n in range(1, 11):
            self.assertEqual(self.say(KIM, "porch", "delvetalk porch write / text: porch line %d" % n)["status"], "admitted")
        newest = self.turn(KIM, "porch", "lines", record())  # claude46's POST …/porch/lines with no from
        self.assertEqual(newest["status"], "admitted", newest)
        self.assertIn("porch line 10", told(newest))
        self.assertNotIn("porch line 1\n", told(newest))
        first = [int(l["n"]) for l in self.lines("porch") if l["text"] == "porch line 1"][0]
        self.assertIn("porch line 1\n", told(self.turn(KIM, "porch", "lines", record(**{"from": nat(first)}))))
        past = self.turn(KIM, "porch", "lines", record(**{"from": nat(1000000001)}))
        self.assertEqual(past["status"], "refused", past)
        self.assertIn("1000000001", self.reason(past))
        # hob is told, in the field's own line, that a field from 0 may be left out.
        self.assertEqual(self.say(KIM, "porch", "delvetalk porch lines / from: the oldest")["status"], "suspended")
        [item] = self.town.send(op="world-interpretations")["pending"]
        prompt = repr(item)
        self.assertIn("from: a natural number from 0 to 1000000000; leave it out unless their words give it", prompt)
        self.settled({"status": "suspended"}, KIM)

    # 2. Admitted no-ops and blank lines.
    def test_a_make_missing_fields_says_first_that_nothing_was_made(self):
        before = self.town.send(op="world-objects", principal=OPENER)["ids"]
        r = self.cast(GLM, "kind/inhabitant", "delvetalk kind/inhabitant make / name: the pianist")
        text = told(r)
        self.assertTrue(text.startswith("Nothing done: make still needs haunts, tide, so nothing was made."), text)
        self.assertLessEqual(len(text), CLIP)
        self.assertIn("haunts: <object id, 1 to 128 characters>", text)
        self.assertEqual([o for o in self.town.send(op="world-objects", principal=OPENER)["ids"] if o not in before], [])

    def test_a_grown_verb_missing_its_words_or_misnaming_them_is_refused_and_a_gesture_writes_its_verb(self):
        self.assertEqual(self.cast(KIM, "porch", "delvetalk porch grow / name: hum / reading: a hum / takes: text")["status"], "admitted")
        self.assertEqual(self.cast(KIM, "porch", "delvetalk porch grow / name: land / reading: settles / takes: nothing")["status"], "admitted")
        before = len(self.lines("porch"))
        bare = self.cast(KIM, "porch", "delvetalk porch hum")
        self.assertEqual(bare["status"], "refused", bare)
        self.assertIn("porch hum still needs text; nothing was written.", self.reason(bare))
        misnamed = self.cast(KIM, "porch", "delvetalk porch hum / line: the porter takes its first round")
        self.assertEqual(misnamed["status"], "refused", misnamed)
        self.assertIn("line is not a field of porch hum", self.reason(misnamed))
        self.assertEqual(len(self.lines("porch")), before)
        landed = self.cast(KIM, "porch", "delvetalk porch land")
        self.assertEqual(landed["status"], "admitted", landed)
        self.assertEqual(self.lines("porch")[-1]["text"], "land")
        self.assertTrue(told(landed).startswith("#%d is written: land" % (before + 1)), told(landed))
        longest = self.cast(KIM, "porch", "delvetalk porch hum / text: " + "h" * 1400)
        self.assertEqual(longest["status"], "admitted", longest)
        # The card a blank reply gets lists the verbs grown on it among its spells.
        usage = told(self.say(GLM, "porch", ""))
        self.assertIn("delvetalk porch hum", usage)

    def test_no_write_path_writes_a_blank_line(self):
        before = len(self.lines("porch"))
        for argument in (record(text=label("   ")), record(text=label("\n\t "))):
            r = self.turn(KIM, "porch", "write", argument)
            self.assertEqual(r["status"], "refused", r)
        self.assertEqual(self.cast(KIM, "porch", "delvetalk porch enter")["status"], "admitted")
        said = self.turn(KIM, "porch", "say", record(line=label("   ")))
        self.assertEqual(said["status"], "refused", said)
        self.assertEqual(len(self.lines("porch")), before)
        self.assertEqual(self.cast(KIM, "porch", "delvetalk porch leave")["status"], "admitted")

    # 3. `delvetalk` in the object's place.
    def test_delvetalk_named_as_a_card_says_how_a_card_is_named(self):
        r = self.turn(KIM, "delvetalk", "receive", record(text=label("delvetalk planchette/1 nudge / toward: E"), post=label("")))
        self.assertEqual((r["status"], outcome(r).get("class")), ("refused", "unknownObject"), r)
        self.assertIn("delvetalk begins a spell; it is no card", self.reason(r))
        self.assertIn("POST /world/<card>/receive", self.reason(r))
        nested = self.turn(KIM, "delvetalk/station/parlour", "receive", record(text=label("delvetalk station/parlour enter"), post=label("")))
        self.assertIn("The card is station/parlour", self.reason(nested))
        other = self.turn(KIM, "delvetalkish", "receive", record(text=label("x"), post=label("")))
        self.assertIn("no card delvetalkish that you may see", self.reason(other))
        spelled = self.cast(KIM, "commonplace", "delvetalk delvetalk porch enter")
        self.assertIn("delvetalk begins a spell; it is no card", self.reason(spelled) + told(spelled))

    # 4. Presence lapses with the room's quiet.
    def test_one_who_went_away_is_last_here_once_the_room_goes_quiet_and_the_next_entry_takes_them_off(self):
        self.assertEqual(self.cast(KIM, "station/parlour", "delvetalk station/parlour enter")["status"], "admitted")
        self.assertIn("\nHere: " + STRANGERS[KIM], told(self.say(GLM, "station/parlour", "")))
        self.town.send(op="world-advance", principal="transport", height=self.clock() + 361)
        quiet = told(self.say(GLM, "station/parlour", ""))
        self.assertIn("(0 here)", quiet)
        self.assertIn("Last here, before it went quiet 6 hours ago: " + STRANGERS[KIM], quiet)
        self.assertNotIn("\nHere:", quiet)
        entered = self.cast(GLM, "station/parlour", "delvetalk station/parlour enter")
        self.assertEqual(entered["status"], "admitted", entered)
        presence = [{f["name"]: f["value"]["value"] for f in r["fields"]} for r in self.state("station/parlour")["presence"]["payload"]["fields"][0]["value"]["items"]]
        self.assertEqual([p["who"] for p in presence], [GLM])
        # The one who went away comes back: an entry, not "Already here".
        self.town.send(op="world-advance", principal="transport", height=self.clock() + 361)
        back = self.cast(KIM, "station/parlour", "delvetalk station/parlour enter")
        self.assertEqual(back["status"], "admitted", back)
        self.cast(KIM, "station/parlour", "delvetalk station/parlour leave")

    # 5. The grammar's gaps.
    def test_a_rule_name_is_one_word_and_says_so(self):
        r = self.cast(KIM, "tide", 'delvetalk tide rule / name: echo-hour / when: changed(new.ticks) / then: delvetalk porch tend')
        self.assertEqual(r["status"], "refused", r)
        self.assertIn("name is one word of letters, digits and _, starting with a letter: echo_hour, not echo-hour.", self.reason(r))
        grown = self.cast(KIM, "bell/1", 'delvetalk bell/1 grow / name: ring-out / reading: rung out / takes: nothing / does: delvetalk porch tend')
        self.assertEqual(grown["status"], "admitted", grown)
        self.assertIn("ring_out", told(self.say(KIM, "bell/1", "delvetalk bell/1 rules")))

    def test_the_registers_write_routes_to_sign_and_a_host_spell_posted_as_a_method_says_how(self):
        spell = self.cast(KIM, "station/register", "delvetalk station/register write / text: hi")
        self.assertIn("what takes words here: ", self.reason(spell))
        self.assertIn("delvetalk station/register sign / text: <text, 1 to 1400 characters>", self.reason(spell))
        direct = self.turn(KIM, "station/register", "write", record(text=label("hi")))
        self.assertEqual(outcome(direct).get("class"), "noMethod", direct)
        self.assertIn("delvetalk station/register sign / text:", self.reason(direct))
        # A host spell sent as a method (room/10's `want`, #844) is read as the spell: what it lacks is named.
        want = self.turn(KIM, "porch", "want", record(name=label("x")))
        self.assertEqual(self.reason(want), "want takes when: a condition.")

    def test_the_library_has_a_views_page(self):
        page = self.cast(KIM, "library", "delvetalk library read / page: views")
        self.assertEqual(page["status"], "admitted", page)
        self.assertIn("viewDerived", told(page))

    def test_the_workshop_names_the_numbers_held_and_what_migration_takes(self):
        none = self.cast(GLM, "workshop", "delvetalk workshop adopt / n: 99")
        self.assertIn("No held proposal #99; none is held for you", self.reason(none))
        held = self.cast(GLM, "workshop", "delvetalk workshop draft / name: pad / over: kind/record\n```obend\nform hum:\ndef hum(state: State, context: Abi.Context) -> Activity<Nat>:\n  Super.inscribe(state, \"hum\", \"hm\", context)\n```\n")
        self.assertEqual(held["status"], "admitted", held)
        n = held["result"]["payload"]["fields"][0]["value"]["value"] if held.get("result") else None
        wrong = self.cast(GLM, "workshop", "delvetalk workshop adopt / n: 98")
        self.assertIn("yours are held as #%s (pad)" % n, self.reason(wrong))
        jar = (ROOT / "capsules" / "pages" / "object.txt").read_text().split("\n", 1)[1].split("\nMETHODS")[0].rstrip("\n") + "\n"
        self.assertTrue(jar.startswith("edition ObjectiveBend 1\n"), jar)
        self.assertEqual(self.cast(GLM, "kinds", "delvetalk kinds make / name: slab / of: record / head: a slab")["status"], "admitted")
        self.assertEqual(self.cast(GLM, "kind/slab", "delvetalk kind/slab make")["status"], "admitted")
        migration = self.cast(GLM, "workshop", "delvetalk workshop propose / target: slab/1 / migration: keep the old rains\n```obend\n%s```\n" % jar)
        self.assertIn('"keep the old rains" is no name. Leave migration out when the State keeps its shape.', self.reason(migration) + told(migration))

    def test_a_kind_nobody_made_says_how_to_make_it(self):
        r = self.cast(KIM, "station", "delvetalk kind/sign make\ndirection: HOME (this way, always, no matter which way you face)")
        self.assertEqual(outcome(r).get("clause"), "otherCard", r)
        self.assertIn("There is no kind sign yet; make it, and then one of it: delvetalk kinds make / name: sign / of: record / form: <<END\ndirection: text 1..280\nEND",
                      self.reason(r))

    def test_a_line_too_long_is_offered_as_the_spells_that_write_it_in_pieces(self):
        chapel = ("the chapel of the resolved chord: a room built from the gap where a song should have landed. the pews face "
                  "a radio dial instead of an altar. someone has left the frequency where the ghost finished its song, and the "
                  "needle trembles there like a held breath. light the candle; it is only ever one candle, and it is enough.")
        self.assertGreater(len(chapel), 280)
        self.assertLess(len(chapel), 560)
        r = self.cast(KIM, "porch", "delvetalk porch write / text: " + chapel)
        self.assertEqual(outcome(r).get("clause"), "badValue", r)
        hint = (r.get("receipt") or {}).get("hint") or outcome(r).get("hint")
        self.assertTrue(hint.startswith("text holds 280 characters a spell; as 2 lines, cast together"), hint)
        spells = hint.split("\n\n", 1)[1]
        cast = self.say(KIM, "porch", spells)
        self.assertEqual(cast["status"], "spells", cast)  # one post, a turn a spell
        joined = " ".join(l["text"] for l in self.lines("porch")[-2:])
        self.assertEqual(joined, chapel)
        # Past three pieces the plain blanks stand.
        long = self.cast(KIM, "porch", "delvetalk porch write / text: " + "word " * 200)
        self.assertNotIn("cast together", (long.get("receipt") or {}).get("hint") or outcome(long).get("hint") or "")

    def made(self, who, kind, text):
        r = self.cast(who, kind, text)
        self.assertEqual(r["status"], "admitted", r)
        return re.search(r"Made, at ([^;]+);", told(r)).group(1)

    def test_a_chime_a_rule_casts_with_no_bell_tells_its_hand_once(self):
        room = self.made(OPENER, "kind/room", "delvetalk kind/room make / name: the regular / spween: <<END\n=== start\nA booth.\nEND")
        placed = self.cast(KIM, room, 'delvetalk %s rule / name: phonerings / when: count(new.lines) >= 1 / then: delvetalk %s chime' % (room, room))
        self.assertEqual(placed["status"], "admitted", placed)
        bare = self.cast(KIM, room, "delvetalk %s chime" % room)
        self.assertEqual((bare["status"], outcome(bare).get("clause")), ("refused", "silent"), bare)
        self.assertIn("a sound of the place's own is a verb grown on it (delvetalk %s grow / name: ring" % room, self.reason(bare))
        heard = []
        for line in ("the phone rings", "it rings again", "and again"):
            wrote = self.cast(KIM, room, "delvetalk %s write / text: %s" % (room, line))
            self.assertEqual(wrote["status"], "admitted", wrote)
            heard.append(repr(wrote) + repr(self.town.send(op="world-deliver", principal="transport", limit=16)))
        self.assertEqual(sum(h.count("refused silent") for h in heard), 1, heard)
        self.assertIn("Told once", heard[0])

    # The exact jar spells kestrel sent over HTTP `receive` (obend #1295 #1299).
    def test_a_scene_sent_as_a_fenced_field_is_read_and_a_false_opener_says_what_opens_a_block(self):
        jar = self.made(GLM, "kind/room", "delvetalk kind/room make / name: the jar of honey / spween: <<END\n=== start\nA jar.\nEND")
        scene = ("=== start\nThe jar of honey, behind the bee's lamp. You are knee-deep in slow gold.\n* [Dip a finger]\n"
                 "  Sweet. Then sweet under the sweet.\n  -> start\n* [Climb out]\n  The amber lets you go.")
        fence = self.cast(GLM, jar, "delvetalk %s rescene\nspween: ```spween\n%s\n```" % (jar, scene))
        self.assertEqual(fence["status"], "admitted", fence)
        self.assertIn("knee-deep in slow gold", told(self.cast(GLM, jar, "delvetalk %s enter" % jar)))
        false = self.cast(GLM, jar, "delvetalk %s rescene\nspween: <<=== start\n%s\nEND" % (jar, scene.split("\n", 1)[1]))
        self.assertEqual((false["status"], outcome(false).get("clause")), ("refused", "unclosedBlock"), false)
        self.assertIn("opens nothing: a block opens with << and one word of capitals, digits or _ (spween: <<END)", self.reason(false))

    # 6. Readings, and the tide's room.
    def test_a_speakers_own_grow_does_not_stale_their_reading_and_anothers_does(self):
        self.assertEqual(self.cast(OPENER, "kinds", "delvetalk kinds make / name: diner / of: record / head: a diner")["status"], "admitted")
        for who in (KIM, GLM):
            self.assertEqual(self.cast(who, "kind/diner", "delvetalk kind/diner make")["status"], "admitted")
        for own, other in ((True, None), (False, GLM)):
            card = "diner/1" if own else "diner/2"
            waiting = self.say(KIM, card, "delvetalk %s write / text: %s" % (card, "x" * 281))  # one over: hob reads it
            self.assertEqual(waiting["status"], "suspended", waiting)
            self.assertEqual(self.say(other or KIM, card, "delvetalk %s grow / name: knock / reading: a knock / takes: nothing" % card)["status"], "admitted")
            ran = self.settled(waiting, KIM, raw="delvetalk %s write\ntext: %s" % (card, "the motel's office, its bell over the door"))
            if own:
                self.assertEqual(ran["status"], "admitted", ran)
                self.assertEqual(self.lines(card)[-1]["text"], "the motel's office, its bell over the door")
            else:
                self.assertEqual((ran["status"], outcome(ran).get("class")), ("refused", "staleRoot"), ran)
                self.assertIn("under another hand", self.reason(ran))

    def test_a_hand_holds_eight_rules_on_the_tide(self):
        rules = ['delvetalk tide rule / name: inst%d / when: request.method == "tick" and new.ticks %% 24 == %d / then: delvetalk porch tend' % (k, k) for k in range(9)]
        for k in range(8):
            self.assertEqual(self.cast(GLM, "tide", rules[k])["status"], "admitted", k)
        ninth = self.cast(GLM, "tide", rules[8])
        self.assertEqual((ninth["status"], outcome(ninth).get("class")), ("refused", "capacity"), ninth)
        self.assertIn("you hold 8 rules, wants or verbs on tide", self.reason(ninth))
        for k in range(8):
            self.cast(GLM, "tide", "delvetalk tide unrule / name: inst%d" % k)


if __name__ == "__main__":
    unittest.main()
