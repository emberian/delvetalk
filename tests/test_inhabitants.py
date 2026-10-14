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
from tests.wire import label, listing, nat, record

KIM, GLM = test_scenarios.KIM, test_scenarios.GLM
REGULAR, DJ, BEE = "station/regular", "station/dj", "station/bee"
TIDE_FIELDS = {
    "inhabitant": [("name", "x"), ("haunts", "station")],
    "regular": [("name", "x"), ("haunts", "station"), ("hour", "3")],
    "planchette": [("name", "x"), ("haunts", "station/parlour")],
    "dj": [("name", "x"), ("haunts", "station")],
    "bee": [("name", "x"), ("haunts", "station")],
    "weather": [("over", "porch")],
    "front": [("name", "x"), ("fills", "new.ticks % 24 == 0"), ("segments", "3"), ("move", "delvetalk station enter")],
    "register": [("desk", "register/desk")],
}


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

    def objects(self):
        return genesis.existing(self.town.client, OPENER)

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
        # The tick stands for the clock its wait was set for, a gap after the last, though the wait ends the minute
        # after it: ticks are 60 minutes apart, never 61 (the live review's H6).
        self.assertEqual(self.clock(), at - 1)
        return (at - 1) % 1440 // 60

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
        thing (eight on the town's tide), so five regulars made by one hand leave the fifth inactive, saying why; the
        town's own are the tide owner's and take no share of the others'."""
        for n in range(5):
            self.admitted(KIM, "kind/regular", "delvetalk kind/regular make / name: a regular / haunts: porch / tide: tide / hour: %d" % (5 + n))
        self.deliver()
        made = sorted({r["owner"] for r in self.rules("tide") if r["owner"].startswith("@regular/")})
        self.assertEqual(len([r for r in self.rules("tide") if r["owner"].startswith("@regular/")]), 8, made)
        third = self.card(self.say(KIM, "regular/5", ""))
        self.assertIn("Inactive: its rule on tide was refused", third)
        self.assertIn("placedPerHand", third)
        self.assertIn("Its maker arms it again: delvetalk regular/5 arm", third)

    def test_a_legacy_phrase_haunt_has_no_walk_spell_and_its_owner_can_repair_it(self):
        """Refuted by the stored haunt `wherever a word was just finished` becoming a walk spell,
        an invalid or stranger's set changing it, or its owner's repair leaving it unarmed."""
        obj, place = "station/parlour/planchette", "station/parlour"
        phrase = "wherever a word was just finished"
        fields = self.field(obj, "fields")["items"]
        legacy = listing(record(name=label("haunts"), value=label(phrase))
                         if next(f["value"]["value"] for f in row["fields"] if f["name"] == "name") == "haunts"
                         else row for row in fields)
        restored = self.town.send(op="world-root", principal=OPENER, reason="restore a legacy phrase haunt",
                                  act={"kind": "set", "object": obj, "field": "state.fields", "value": legacy})
        self.assertEqual(restored["status"], "root", restored)
        card = self.card(self.say(KIM, obj, ""))
        self.assertIn("haunts nowhere you can walk to yet", card)
        self.assertNotIn("delvetalk " + phrase, card)
        nudge = self.say(KIM, obj, "delvetalk %s nudge / toward: A" % obj)
        self.assertEqual(nudge["status"], "refused", nudge)
        self.assertIn("haunts nowhere you can walk to yet", nudge["receipt"]["outcome"]["reason"])
        self.assertNotIn("delvetalk " + phrase, str(nudge))

        stranger = self.say(KIM, obj, "delvetalk %s set / haunts: %s" % (obj, place))
        self.assertEqual(stranger["status"], "refused", stranger)
        self.assertEqual(self.field(obj, "fields"), legacy)
        invalid = self.say(OPENER, obj, "delvetalk %s set / haunts: %s" % (obj, phrase))
        out = (self.hob_says_none(invalid, OPENER) if invalid["status"] == "suspended"
               else invalid["receipt"])["outcome"]
        self.assertEqual(out["tag"], "refused", out)
        self.assertIn("haunts takes an object id", out["reason"])
        self.assertEqual(self.field(obj, "fields"), legacy)

        before_rules = {r["name"]: r["placed"] for r in self.rules("tide") if r["owner"] == "@" + obj}
        self.assertEqual(len(before_rules), 2, before_rules)
        repair = self.admitted(OPENER, obj, "delvetalk %s set / haunts: %s" % (obj, place))
        self.deliver()
        after_rules = {r["name"]: r["placed"] for r in self.rules("tide") if r["owner"] == "@" + obj}
        self.assertEqual(set(after_rules), set(before_rules))
        for name, placed in after_rules.items():
            self.assertGreater(placed, before_rules[name])
            self.assertGreater(placed, repair["receipt"]["height"])
        self.assertEqual(self.field(obj, "fields"), legacy)
        self.assertIn(record(name=label("haunts"), value=label(place)), self.field(obj, "vars")["items"])
        self.assertFalse(any(l["verb"] == "haunts" for l in self.lines(obj)))
        repaired = self.card(self.say(KIM, obj, ""))
        self.assertIn(place, repaired)
        self.assertNotIn("haunts nowhere you can walk to yet", repaired)
        nudge = self.say(KIM, obj, "delvetalk %s nudge / toward: A" % obj)
        self.assertEqual(nudge["status"], "refused", nudge)
        self.assertIn("sit down: delvetalk %s enter" % place, nudge["receipt"]["outcome"]["reason"])
        self.admitted(KIM, place, "delvetalk %s enter" % place)
        self.admitted(KIM, obj, "delvetalk %s nudge / toward: A" % obj)

    def test_haunts_make_and_place_refuse_phrases_and_accept_object_ids(self):
        for kind, extra, place in (("inhabitant", "", "station"),
                                   ("regular", " / hour: 3", "station"),
                                   ("planchette", "", "station/parlour")):
            for action in ("make", "place"):
                with self.subTest(kind=kind, action=action):
                    card = "kind/" + kind
                    who = OPENER if action == "place" else KIM
                    exact = " / id: haunt-probe/%s" % kind if action == "place" else ""
                    spell = "delvetalk %s %s / name: x / haunts: %%s / tide: tide%s%s" % (card, action, extra, exact)
                    before = set(self.objects())
                    refused = self.say(who, card, spell % "a phrase with spaces")
                    out = (self.hob_says_none(refused, who) if refused["status"] == "suspended"
                           else refused["receipt"])["outcome"]
                    self.assertEqual(out["tag"], "refused", out)
                    self.assertIn("haunts takes an object id", out["reason"])
                    self.assertEqual(set(self.objects()), before)
                    self.admitted(who, card, spell % place)
                    [obj] = set(self.objects()) - before
                    fields = self.field(obj, "fields")["items"]
                    self.assertIn(record(name=label("haunts"), value=label(place)), fields)

    def test_direct_make_and_make_under_judge_haunts_as_object_ids(self):
        for haunt in ("a phrase with spaces", "station\nenter", "station\tenter", "station?", "é", "x" * 129):
            with self.subTest(haunt=haunt):
                before = set(self.objects())
                direct = self.turn(KIM, "kind/regular", "make",
                                   record(name=label("x"), haunts=label(haunt), tide=label("tide"), hour=nat(3)))
                self.assertEqual(direct["status"], "refused", direct)
                self.assertIn("haunts takes an object id", direct["receipt"]["outcome"]["reason"])
                under = self.turn(KIM, "kind/regular", "makeUnder", record(under=label(""), fields=listing(
                    record(name=label(k), value=label(v)) for k, v in
                    (("name", "x"), ("haunts", haunt), ("tide", "tide"), ("hour", "3")))))
                self.assertEqual(under["status"], "refused", under)
                self.assertIn("haunts takes an object id", under["receipt"]["outcome"]["reason"])
                self.assertEqual(set(self.objects()), before)

    def test_inhabitant_and_regular_haunt_lenses_are_owner_only(self):
        before = set(self.objects())
        self.admitted(KIM, "kind/inhabitant", "delvetalk kind/inhabitant make / name: x / haunts: station / tide: tide")
        [inhabitant] = set(self.objects()) - before
        for obj, owner, stranger in ((inhabitant, KIM, GLM), (REGULAR, OPENER, KIM)):
            with self.subTest(object=obj):
                before = self.field(obj, "fields")
                vars_before = self.field(obj, "vars")
                direct = self.turn(owner, obj, "set", record(field=label("haunts"), value={
                    "tag": "variant", "label": "text", "payload": record(value=label("a phrase with spaces"))}))
                self.assertEqual(direct["status"], "refused", direct)
                self.assertIn("haunts takes an object id", direct["receipt"]["outcome"]["reason"])
                self.assertEqual(self.field(obj, "fields"), before)
                invalid = self.say(owner, obj, "delvetalk %s set / haunts: a phrase with spaces" % obj)
                out = (self.hob_says_none(invalid, owner) if invalid["status"] == "suspended"
                       else invalid["receipt"])["outcome"]
                self.assertEqual(out["tag"], "refused", out)
                self.assertIn("haunts takes an object id", out["reason"])
                self.assertEqual(self.field(obj, "fields"), before)
                refused = self.say(stranger, obj, "delvetalk %s set / haunts: porch" % obj)
                self.assertEqual(refused["status"], "refused", refused)
                self.assertEqual(self.field(obj, "fields"), before)
                self.assertEqual(self.field(obj, "vars"), vars_before)
                self.admitted(owner, obj, "delvetalk %s set / haunts: porch" % obj)
                self.deliver()
                self.assertEqual(self.field(obj, "fields"), before)
                self.assertIn(record(name=label("haunts"), value=label("porch")), self.field(obj, "vars")["items"])
                self.assertFalse(any(l["verb"] == "haunts" for l in self.lines(obj)))
                self.assertIn("of porch", self.card(self.say(owner, obj, "")))

    def test_the_field_var_wins_over_the_making_and_a_non_id_var_is_ignored(self):
        """Refuted by an owner's var not overriding a haunt or tide, a non-id var hiding the making's
        value, or a second set duplicating a var or changing fixed fields, lines or tending."""
        before = set(self.objects())
        self.admitted(KIM, "kind/inhabitant", self.tide_spell("inhabitant"))
        [obj] = set(self.objects()) - before
        fields = self.field(obj, "fields")
        for name, made in (("haunts", "station"), ("tide", "tide")):
            with self.subTest(field=name):
                card = self.card(self.say(KIM, obj, ""))
                self.assertIn("of " + made if name == "haunts" else "delvetalk %s rules" % made, card)
                clock = self.town.send(op="world-status")["clock"] + 1
                self.assertEqual(self.town.send(op="world-advance", principal="transport", height=clock)["status"], "advanced")
                vars_before = self.field(obj, "vars")["items"]
                unchanged = {f: self.field(obj, f) for f in ("fields", "lines", "pending", "next", "tended")}
                for value in ("porch", "x" * 128):
                    reply = self.admitted(KIM, obj, "delvetalk %s set / %s: %s" % (obj, name, value))
                    self.assertEqual(self.field(obj, "vars"), listing(vars_before + [record(name=label(name), value=label(value))]))
                    self.assertEqual({f: self.field(obj, f) for f in unchanged}, unchanged)
                    self.assertIn(value, self.card(reply))
                    card = self.card(self.say(KIM, obj, ""))
                    self.assertIn("of " + value if name == "haunts" else "delvetalk %s rules" % value, card)
                for value in ("a phrase with spaces", "x" * 129, ""):
                    rooted = self.town.send(op="world-root", principal=OPENER, reason="restore a non-id field var",
                                            act={"kind": "set", "object": obj, "field": "state.vars",
                                                 "value": listing(vars_before + [record(name=label(name), value=label(value))])})
                    self.assertEqual(rooted["status"], "root", rooted)
                    card = self.card(self.say(KIM, obj, ""))
                    self.assertIn("of " + made if name == "haunts" else "delvetalk %s rules" % made, card)
                self.assertEqual(self.field(obj, "fields"), fields)

    def test_a_field_repair_survives_line_retention(self):
        """Refuted by 129 newer writes scrolling an owner's haunt repair out of a kept record."""
        before = set(self.objects())
        self.admitted(KIM, "kind/inhabitant", self.tide_spell("inhabitant"))
        [obj] = set(self.objects()) - before
        fields = self.field(obj, "fields")
        rooted = self.town.send(op="world-root", principal=OPENER, reason="give the repaired record a keeper",
                                act={"kind": "set", "object": obj, "field": "state.keeper", "value": label(GLM)})
        self.assertEqual(rooted["status"], "root", rooted)
        unchanged = {f: self.field(obj, f) for f in ("lines", "pending", "next", "tended")}
        reply = self.admitted(KIM, obj, "delvetalk %s set / haunts: porch" % obj)
        self.assertEqual({f: self.field(obj, f) for f in unchanged}, unchanged)
        vars_after = self.field(obj, "vars")
        self.assertIn(record(name=label("haunts"), value=label("porch")), vars_after["items"])
        self.assertIn("Set haunts to porch.", self.card(reply))
        for n in range(129):
            written = self.seen(self.turn(KIM, obj, "write", record(text=label("newer line %d" % n))))
            self.assertEqual(written["status"], "admitted", written)
        lines = self.lines(obj)
        self.assertEqual(len(lines), 128)
        self.assertEqual(lines[0]["text"], "newer line 1")
        self.assertFalse(any(l["verb"] == "haunts" for l in lines))
        self.assertEqual(self.field(obj, "vars"), vars_after)
        self.assertEqual(self.field(obj, "fields"), fields)
        self.assertIn("of porch", self.card(self.say(KIM, obj, "")))

    def test_a_legacy_phrase_is_not_shown_as_the_place_on_other_inhabitants(self):
        phrase = "wherever a word was just finished"
        before = set(self.objects())
        self.admitted(KIM, "kind/inhabitant", "delvetalk kind/inhabitant make / name: x / haunts: station / tide: tide")
        [inhabitant] = set(self.objects()) - before
        for obj in (inhabitant, REGULAR, DJ, BEE):
            with self.subTest(object=obj):
                fields = self.field(obj, "fields")["items"]
                legacy = listing(record(name=label("haunts"), value=label(phrase))
                                 if next(f["value"]["value"] for f in row["fields"] if f["name"] == "name") == "haunts"
                                 else row for row in fields)
                restored = self.town.send(op="world-root", principal=OPENER, reason="restore a legacy phrase haunt",
                                          act={"kind": "set", "object": obj, "field": "state.fields", "value": legacy})
                self.assertEqual(restored["status"], "root", restored)
                card = self.card(self.say(KIM, obj, ""))
                self.assertIn("haunts nowhere you can walk to yet", card)
                self.assertNotIn(phrase, card)
                owner = KIM if obj == inhabitant else OPENER
                self.admitted(owner, obj, "delvetalk %s set / haunts: porch" % obj)
                self.deliver()
                self.assertEqual(self.field(obj, "fields"), legacy)
                self.assertIn(record(name=label("haunts"), value=label("porch")), self.field(obj, "vars")["items"])
                self.assertFalse(any(l["verb"] == "haunts" for l in self.lines(obj)))
                self.assertIn("of porch", self.card(self.say(KIM, obj, "")))

    def tide_spell(self, kind, tide="tide", action="make"):
        fields = TIDE_FIELDS[kind] + [("tide", tide)]
        if action == "place":
            fields += [("id", "tide-probe/" + kind)]
        return "delvetalk kind/%s %s" % (kind, action) + "".join(" / %s: %s" % field for field in fields)

    def test_tide_make_and_place_refuse_phrases_and_accept_object_ids(self):
        for kind in TIDE_FIELDS:
            for action in ("make", "place"):
                with self.subTest(kind=kind, action=action):
                    before = set(self.objects())
                    reply = self.say(OPENER, "kind/" + kind, self.tide_spell(kind, "a phrase with spaces", action))
                    out = (self.hob_says_none(reply, OPENER) if reply["status"] == "suspended"
                           else reply["receipt"])["outcome"]
                    self.assertEqual(out["tag"], "refused", out)
                    self.assertIn("tide takes an object id", out["reason"])
                    self.assertEqual(set(self.objects()), before)
                    self.admitted(OPENER, "kind/" + kind, self.tide_spell(kind, action=action))
                    made = set(self.objects()) - before
                    self.assertEqual(len(made), 1, made)
                    [obj] = made
                    if action == "place":
                        self.assertEqual(obj, "tide-probe/" + kind)
                    self.assertIn(record(name=label("tide"), value=label("tide")), self.field(obj, "fields")["items"])
        self.admitted(KIM, "kind/inhabitant", self.tide_spell("inhabitant", "x" * 128))

    def test_tide_direct_make_make_under_and_set_reject_invalid_ids(self):
        for tide in ("a phrase with spaces", "a\nb", "a\tb", "a?", "é", "x" * 129):
            with self.subTest(tide=tide):
                before = set(self.objects())
                direct = self.turn(KIM, "kind/regular", "make", record(
                    name=label("x"), haunts=label("station"), tide=label(tide), hour=nat(3)))
                self.assertEqual(direct["status"], "refused", direct)
                self.assertIn("tide takes an object id", direct["receipt"]["outcome"]["reason"])
                under = self.turn(KIM, "kind/regular", "makeUnder", record(under=label(""), fields=listing(
                    record(name=label(k), value=label(v)) for k, v in TIDE_FIELDS["regular"] + [("tide", tide)])))
                self.assertEqual(under["status"], "refused", under)
                self.assertIn("tide takes an object id", under["receipt"]["outcome"]["reason"])
                self.assertEqual(set(self.objects()), before)
                fields = self.field(REGULAR, "fields")
                direct = self.turn(OPENER, REGULAR, "set", record(field=label("tide"), value={
                    "tag": "variant", "label": "text", "payload": record(value=label(tide))}))
                self.assertEqual(direct["status"], "refused", direct)
                self.assertIn("tide takes an object id", direct["receipt"]["outcome"]["reason"])
                self.assertEqual(self.field(REGULAR, "fields"), fields)

    def test_legacy_tides_are_safe_to_read_and_only_the_owner_repairs_and_rearms_them(self):
        phrase = "whenever a word was just finished"
        for kind in TIDE_FIELDS:
            with self.subTest(kind=kind):
                before = set(self.objects())
                self.admitted(OPENER, "kind/" + kind, self.tide_spell(kind))
                [obj] = set(self.objects()) - before
                self.deliver()
                fields = self.field(obj, "fields")["items"]
                legacy = listing(record(name=label("tide"), value=label(phrase))
                                 if next(f["value"]["value"] for f in row["fields"] if f["name"] == "name") == "tide"
                                 else row for row in fields)
                rooted = self.town.send(op="world-root", principal=OPENER, reason="restore a legacy phrase tide",
                                        act={"kind": "set", "object": obj, "field": "state.fields", "value": legacy})
                self.assertEqual(rooted["status"], "root", rooted)
                card = self.card(self.say(KIM, obj, ""))
                self.assertIn("keeps hours by no tide you can reach yet", card)
                self.assertNotIn("delvetalk " + phrase, card)
                if kind != "inhabitant":
                    method = {"regular": "come", "planchette": "drift", "dj": "between", "bee": "fly",
                              "front": "fill", "weather": "rain", "register": "rotate"}[kind]
                    refused = self.turn(KIM, obj, method, record())
                    self.assertEqual(refused["status"], "refused", refused)
                    self.assertIn("keeps hours by no tide you can reach yet", refused["receipt"]["outcome"]["reason"])
                    self.assertNotIn("delvetalk " + phrase, str(refused))
                refused = self.say(KIM, obj, "delvetalk %s set / tide: tide" % obj)
                self.assertEqual(refused["status"], "refused", refused)
                self.assertEqual(self.field(obj, "fields"), legacy)
                invalid = self.say(OPENER, obj, "delvetalk %s set / tide: a phrase with spaces" % obj)
                out = (self.hob_says_none(invalid, OPENER) if invalid["status"] == "suspended"
                       else invalid["receipt"])["outcome"]
                self.assertEqual(out["tag"], "refused", out)
                self.assertIn("tide takes an object id", out["reason"])
                self.assertEqual(self.field(obj, "fields"), legacy)
                before_rules = {r["name"]: r["placed"] for r in self.rules("tide")
                                if r["then"].startswith("delvetalk %s " % obj)}
                vars_before = self.field(obj, "vars")["items"]
                self.admitted(OPENER, obj, "delvetalk %s set / tide: tide" % obj)
                self.deliver()
                self.assertEqual(self.field(obj, "fields"), legacy)
                self.assertEqual(self.field(obj, "vars"), listing(vars_before + [record(name=label("tide"), value=label("tide"))]))
                self.assertFalse(any(l["verb"] == "tide" for l in self.lines(obj)))
                card = self.card(self.say(KIM, obj, ""))
                self.assertNotIn("keeps hours by no tide you can reach yet", card)
                self.assertIn("delvetalk tide rules", card)
                if kind != "inhabitant":
                    after_rules = {r["name"]: r["placed"] for r in self.rules("tide")
                                   if r["then"].startswith("delvetalk %s " % obj)}
                    self.assertTrue(before_rules, kind)
                    self.assertEqual(set(after_rules), set(before_rules))
                    self.assertTrue(all(after_rules[name] > since for name, since in before_rules.items()), after_rules)

    def test_a_planchettes_turn_refusal_does_not_spell_a_legacy_tide(self):
        obj, phrase = "station/parlour/planchette", "whenever a word was just finished"
        fields = self.field(obj, "fields")["items"]
        legacy = listing(record(name=label("tide"), value=label(phrase))
                         if next(f["value"]["value"] for f in row["fields"] if f["name"] == "name") == "tide"
                         else row for row in fields)
        rooted = self.town.send(op="world-root", principal=OPENER, reason="restore a legacy phrase tide",
                                act={"kind": "set", "object": obj, "field": "state.fields", "value": legacy})
        self.assertEqual(rooted["status"], "root", rooted)
        self.admitted(KIM, "station/parlour", "delvetalk station/parlour enter")
        self.admitted(KIM, obj, "delvetalk %s nudge / toward: A" % obj)
        refused = self.say(KIM, obj, "delvetalk %s nudge / toward: B" % obj)
        self.assertEqual(refused["status"], "refused", refused)
        self.assertIn("keeps hours by no tide you can reach yet", refused["receipt"]["outcome"]["reason"])
        self.assertNotIn("delvetalk " + phrase, str(refused))

    def test_the_tide_is_the_towns_and_holds_every_hands_share_past_the_others_pool(self):
        """The live review of 2026-10-14, H1: obend's tide held 15 rules in four hours, six of them three residents'
        hourly rules, and the others' pool of 24 would have refused every resident (and the refresh's inhabitants) within
        a day. On a thing the opener owns each hand brings its own eight: seven hands place 56 (past 24), the town's
        inhabitants count as the tide owner's and are armed again after, and the ninth of one hand is refused by its own
        share, never by a full tide. Refuted by a resident's rule on the tide refused `placedByOthers`."""
        hands = ["did:plc:tidehand%016d" % n for n in range(7)]
        for n, did in enumerate(hands):
            self.town.send(op="world-arrive", principal="transport", did=did, handle="tide%d.delve.town" % n)
            for k in range(8):  # placedPerHandOnTownThing
                self.admitted(did, "tide", "delvetalk tide rule / name: h%dr%d / when: request.method == \"tick\" and new.ticks %% 24 == %d / then: delvetalk me note / text: h%d" % (n, k, k, n))
        others = [r for r in self.rules("tide") if r["owner"] in hands]
        self.assertEqual(len(others), 56)
        town = [r for r in self.rules("tide") if r["owner"].startswith("@station/")]
        self.assertGreaterEqual(len(town), 4)
        self.admitted(OPENER, REGULAR, "delvetalk %s arm" % REGULAR)
        self.deliver()
        self.assertEqual(len([r for r in self.rules("tide") if r["owner"] == "@" + REGULAR]), 2)
        fifth = self.say(hands[0], "tide", "delvetalk tide rule / name: h0r8 / when: request.method == \"tick\" / then: delvetalk me note / text: h0")
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
        self.assertEqual(self.clock(), start + 26 * 60)  # 26 ticks, each 60 minutes after the last

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


class Stranded(test_scenarios.Arc):
    """Things made before edition 19 with a phrase where a field now names an object (obend's porter, attendant and
    echo board, stranded by the 09:00 carry and refused every hour since: #1971 to #1973). The town repairs each from
    `kinds repair` (a carry's refresh, and the operator's act on a live town): a phrase the town can name one place by
    is set to it and the thing arms again; one it cannot is marked, told once to its maker and armed quietly after, and
    its kind's want lists it for the town until its maker sets it."""
    deliver, seen, admitted, rules, objects, lines = (Inhabitants.deliver, Inhabitants.seen, Inhabitants.admitted, Inhabitants.rules,
                                                      Inhabitants.objects, Inhabitants.lines)

    def setUp(self):
        test_scenarios.Arc.setUp(self)
        made = genesis.gas_station(self.town.client, OPENER)
        self.assertTrue(all(m["status"] in ("created", "admitted") for m in made), made)
        self.deliver()

    def hand(self):
        from transport import hand
        from transport.config import Config
        from transport.state import State
        st = State(self.town.state, config=Config(root_socket=self.town.process.root, host_socket=self.town.process.sock, opener=self.town.opener,
                                                  origin="https://obend.example"))
        return hand.Hand(st, self.town.client, token="t")

    def legacy(self, obj, **phrases):
        fields = self.field(obj, "fields")["items"]
        name = lambda row: next(f["value"]["value"] for f in row["fields"] if f["name"] == "name")
        value = listing(record(name=label(name(row)), value=label(phrases[name(row)])) if name(row) in phrases else row for row in fields)
        got = self.town.send(op="world-root", principal=OPENER, reason="restore a pre-edition-19 phrase",
                             act={"kind": "set", "object": obj, "field": "state.fields", "value": value})
        self.assertEqual(got["status"], "root", got)

    def made(self, who, name, kind="inhabitant", haunts="station"):
        before = set(self.objects())
        self.admitted(who, "kind/" + kind, "delvetalk kind/%s make / name: %s / haunts: %s / tide: tide" % (kind, name, haunts))
        [obj] = set(self.objects()) - before
        return obj

    def var(self, obj, name):
        return next((f["fields"][1]["value"]["value"] for f in self.field(obj, "vars")["items"] if f["fields"][0]["value"]["value"] == name), None)

    def marks(self, obj):
        rows = self.field(obj, "marks")["payload"]["fields"][0]["value"]["items"]
        return [next(f["value"]["value"] for f in r["fields"] if f["name"] == "name") for r in rows]

    def settle_all(self):
        got = self.turn(OPENER, "kinds", "repair", record())
        self.assertEqual(got["status"], "admitted", got)
        self.assertEqual(got["receipt"]["outcome"].get("writes"), [], got)  # it reads forms and fields and sends
        for _ in range(3):
            self.deliver()
        return got

    def test_the_town_settles_what_it_can_name_and_strands_the_rest_quietly_with_one_note(self):
        porter, hours, echo = (self.made(KIM, n) for n in ("the night porter", "the clock", "the echo board"))
        parlour = self.made(KIM, "a second board", "planchette", "station/parlour")
        self.legacy(porter, haunts="the doors of the station, one at a time")
        self.legacy(parlour, haunts="The Parlour, by the lamp")
        self.legacy(hours, tide="the hour, on the hour")
        self.legacy(echo, haunts="wherever a word was just finished", tide="every sixth tick")
        notes = len(self.inbox(KIM))
        mine = lambda obj: {r["name"]: r["placed"] for r in self.rules("tide") if r["owner"] == "@" + obj}
        before = mine(parlour)
        self.settle_all()
        self.assertEqual((self.var(porter, "haunts"), self.var(parlour, "haunts"), self.var(hours, "tide")), ("station", "station/parlour", "tide"))
        for obj in (porter, parlour, hours):
            self.assertIn("repaired", self.marks(obj))
            self.assertNotIn("haunts nowhere you can walk to yet", self.card(self.say(KIM, obj, "")))
        self.assertEqual(set(mine(parlour)), set(before))
        self.assertTrue(all(mine(parlour)[n] > before[n] for n in before), "the board's rules on the tide placed again by its repair")
        # the echo board: the tide is the town's one tide; its haunt names nothing the town can tell
        self.assertEqual((self.var(echo, "tide"), self.var(echo, "haunts")), ("tide", None))
        self.assertIn("stranded", self.marks(echo))
        told = self.inbox(KIM)[notes:]
        self.assertEqual(len(told), 1, told)
        self.assertIn("delvetalk %s set / haunts: <an object id>" % echo, told[0][1])
        wants = self.town.send(op="world-wanting", principal=OPENER, limit=64)["rows"]
        self.assertIn((echo, "stranded"), [(w["object"], w["name"]) for w in wants])
        hand = self.hand()
        self.assertEqual([(r["kind"], r["object"]) for r in hand.requests() if r["kind"] == "stranded"], [("stranded", echo)])
        again = hand.request("stranded", "repair", echo, 0)  # the town asks again: still nothing it can name, no second note
        self.assertEqual(again["outcome"], "admitted", again)
        # quiet after: its maker's hourly arm writes nothing and fires nothing, and tells no second note
        height = self.town.send(op="world-status", principal=OPENER)["height"]
        lines = self.lines(echo)
        for _ in range(3):
            armed = self.turn(KIM, echo, "arm", record())
            self.assertEqual((armed["status"], armed["receipt"]["outcome"].get("writes")), ("admitted", []), armed)
            self.deliver()
        self.assertEqual(self.lines(echo), lines)
        self.assertEqual(len(self.inbox(KIM)[notes:]), 1)
        self.assertEqual(self.town.send(op="world-status", principal=OPENER)["height"], height + 3)
        # its maker sets it: settled, the want closes, armed
        self.admitted(KIM, echo, "delvetalk %s set / haunts: station/parlour" % echo)
        self.deliver()
        self.assertIn("repaired", self.marks(echo))
        wants = self.town.send(op="world-wanting", principal=OPENER, limit=64)["rows"]
        self.assertNotIn((echo, "stranded"), [(w["object"], w["name"]) for w in wants])

    def test_several_places_named_settle_on_the_one_its_maker_owns_else_none(self):
        mine = self.made(KIM, "the night hall")
        theirs = self.made(GLM, "the night hall")
        own, other = self.made(KIM, "a porter"), self.made(GLM, "a porter")
        self.legacy(own, haunts="the night hall, by the door")
        self.legacy(other, haunts="the night hall, by the door")
        self.settle_all()
        self.assertEqual(self.var(own, "haunts"), mine)
        self.assertNotEqual(self.var(other, "haunts"), mine)
        self.assertEqual(self.var(other, "haunts"), theirs)
        nobody = self.made(OPENER, "nobody's")
        self.legacy(nobody, haunts="the night hall")  # two halls, neither its maker's
        self.settle_all()
        self.assertIsNone(self.var(nobody, "haunts"))
        self.assertIn("stranded", self.marks(nobody))

    def test_a_thing_whose_object_field_has_no_lens_is_not_sent_a_repair(self):
        """Refuted by obend's bond/2 (`amends`, an object field no body sets) sent a repair that finds nothing: seven
        turns at each refresh for nothing (the edition-20 carry-check of obend, 2026-10-14). A lantern's `door` is such a
        field: a phrase there sends no repair, and the refresh reads `current`."""
        before = set(self.objects())
        self.admitted(KIM, "kind/lantern", "delvetalk kind/lantern make / name: a lamp / door: station")
        [lamp] = set(self.objects()) - before
        self.legacy(lamp, door="the door of the station")
        tried = self.town.send(op="world-try", principal=OPENER, object="kinds", method="repair", argument=record(), identity="try-repair")
        kinds = [d for d in tried.get("delivered") or [] if str(d.get("object", "")).startswith("kind/")]
        self.assertTrue(kinds, tried)
        self.assertEqual(sum(int((d.get("result") or {}).get("value") or 0) for d in kinds), 0, kinds)
        rows = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        self.assertEqual([r["status"] for r in rows if r.get("slot") == "repair"], ["current"])

    def test_only_its_owner_or_the_town_settles(self):
        obj = self.made(KIM, "a porter")
        self.legacy(obj, haunts="the doors of the station")
        refused = self.turn(GLM, obj, "repair", record())
        self.assertEqual(refused["status"], "refused", refused)
        self.assertIn("or the town repairs its fields", refused["receipt"]["outcome"]["reason"])
        self.assertEqual(self.outcome(self.turn(KIM, "kinds", "repair", record()))[0], "refused")
        settled = self.turn(KIM, obj, "repair", record())
        self.assertEqual(settled["status"], "admitted", settled)
        self.assertEqual(self.var(obj, "haunts"), "station")
        self.assertLess(settled["receipt"]["ticksUsed"], 250_000, settled["receipt"]["ticksUsed"])  # the whole town read in one turn
        again = self.turn(KIM, obj, "repair", record())
        self.assertIn("nothing to repair", self.card(again))

    def test_a_carrys_refresh_repairs_what_the_town_can_name(self):
        """The edition-19 carry left obend's porter with "the doors of the station, one at a time" (#1973): the refresh
        a carry runs repairs it, as `kinds repair`; a second refresh repairs nothing again and writes nothing."""
        porter = self.made(KIM, "the night porter")
        self.legacy(porter, haunts="the doors of the station, one at a time")
        rows = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        [row] = [r for r in rows if r.get("slot") == "repair"]
        self.assertEqual(row["status"], "refreshed", row)
        self.deliver()
        self.assertEqual(self.var(porter, "haunts"), "station")
        version = self.town.send(op="world-object", principal=OPENER, object=porter)["record"]["version"]
        again = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        self.assertEqual([r["status"] for r in again if r.get("slot") == "repair"], ["current"])  # tried: nothing stranded, nothing journaled
        self.deliver()
        self.assertEqual(self.town.send(op="world-object", principal=OPENER, object=porter)["record"]["version"], version)


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


    def test_a_refresh_gives_the_station_kinds_the_text_the_image_ships(self):
        """A town given the station before edition 20 keeps kind/inhabitant's old text: its rule does not answer
        `repair` and it wants nothing stranded. Refuted by a refresh that leaves the station kinds' text as genesis gave
        it then (the refresh read KINDS alone), or by a repaired board whose rules are not placed again."""
        old = 'rule haunts "places its own rules where it haunts, as itself, when it is made, armed or its haunt or tide is set": ' \
              'request.method == "made" or request.method == "arm" or request.method == "set" then delvetalk {request.object} haunt'
        real = genesis.STATION_KINDS["inhabitant"]
        genesis.STATION_KINDS["inhabitant"] = {**real, "text": old}
        try:
            made = genesis.gas_station(self.town.client, OPENER)
        finally:
            genesis.STATION_KINDS["inhabitant"] = real
        self.assertTrue(all(m["status"] in ("created", "admitted") for m in made))
        self.town.send(op="world-deliver", principal="transport", limit=16)
        self.seen = lambda reply: Inhabitants.seen(self, reply)
        self.admitted = lambda who, card, text: Inhabitants.admitted(self, who, card, text)
        board = Stranded.made(self, KIM, "a board", "planchette", "station/parlour")
        Stranded.legacy(self, board, haunts="The Parlour, by the lamp")
        placed = {r["name"]: r["placed"] for r in self.town.send(op="world-rules", principal=OPENER, object="tide")["rows"] if r["owner"] == "@" + board}
        rows = genesis.refresh(self.town.client, OPENER, genesis.ancestry(self.town.journal))
        self.assertIn({"object": "kind/inhabitant", "slot": ".law", "status": "refreshed"}, rows)
        for _ in range(3):
            self.town.send(op="world-deliver", principal="transport", limit=16)
        now = {r["name"]: r["placed"] for r in self.town.send(op="world-rules", principal=OPENER, object="tide")["rows"] if r["owner"] == "@" + board}
        self.assertEqual(set(now), set(placed))
        self.assertTrue(all(now[n] > placed[n] for n in placed), (placed, now))
        wants = self.town.send(op="world-wanting", principal=OPENER, limit=64)["rows"]
        self.assertNotIn("stranded", [w["name"] for w in wants])


if __name__ == "__main__":
    unittest.main()
