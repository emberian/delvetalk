"""KIND makes things: `kinds` makes a kind, a kind makes an instance of its package under its law,
and a kind with a body lays it on each instance (docs/CATALOGUE.md §3, §5 step 3).

Evidence for FOUNDATION §8 extend (layer: objects).

Refuted by: a kind whose make takes other fields than its form; an instance made without the
kind's law or head; a bell body that does not ring on `ring` or takes a rain over 200 characters.
"""
import os
import unittest

from deploy import genesis
from tests.host import ROOT
from tests.test_chain import Chain, town_kinds
from tests.wire import cast_refusal, field, label, listing, nat, record, reference, relation, rows
from tests.bend import closure

KIM, GLM = "did:plc:kimik3", "did:plc:glm"


def body(name):
    with open(os.path.join(ROOT, "world", "bodies", name + ".obend")) as handle:
        return handle.read()


def choice(word):
    return {"tag": "variant", "label": word, "payload": record()}


def text(reply):
    return "".join(o["text"] for o in reply.get("offers", []))


class Kinds(Chain):
    def setUp(self):
        super().setUp()
        r = self.host.send(op="world-create", principal="ember", identity="mk-kinds", object="kinds", modules=closure("Kind"),
                           entry="initial", seed=record(owner=label("ember"), name=label("kinds"), of=label("kind"), form=label(genesis.KINDS_FORM),
                                                        head=label("")), law=genesis.KIND_LAW)
        self.assertEqual(r["status"], "created", r)
        shaped = self.turn("kinds", "shape", record(object=label("kinds")))
        self.assertEqual(shaped["status"], "admitted", shaped)

    def kind(self, name, of, form, head="", law="", body_source=""):
        r = self.turn("kinds", "make", record(name=label(name), of=label(of), form=label(form), head=label(head), voice=label(""), about=label(""), law=label(law), body=label(body_source)))
        self.assertEqual(r["status"], "admitted", r)
        return r

    def become(self, thing, kind, principal="ember"):
        return self.turn(thing, "receive", record(text=label("delvetalk %s become / kind: %s" % (thing, kind)),
                                                 post=label("")), principal=principal)

    def component_lines(self, thing):
        return [(field(r, "verb")["value"], field(r, "text")["value"])
                for r in rows(field(self.state(thing), "lines"))]

    def component_info(self, thing):
        info = self.host.send(op="world-inspect", principal="ember", object=thing, source=True)
        info["version"] = self.host.send(op="world-view", principal="ember", object=thing)["version"]
        return info

    def water_body(self, text="input.text", super_water=False):
        return ('form water:\n  text: text 1..280\n'
                'def water(state: State, input: WaterInput, context: Abi.Context) -> Activity<Nat>:\n  ' +
                ('Super.water(state, input, context)' if super_water else
                 'Super.inscribe(state, "water", %s, context)' % text) + '\n')

    def test_made_and_become_carry_the_same_verb_and_live_kind_law(self):
        self.kind("watercap", "record", "", law='law few "at most three waters": count(new.lines where verb == "water") <= 3',
                  body_source=self.water_body())
        self.kind("plainpot", "record", "")
        for kind in ("watercap", "plainpot"):
            self.assertEqual(self.turn("kind/" + kind, "make", record())["status"], "admitted")
        laid = self.become("plainpot/1", "kind/watercap")
        self.assertEqual(laid["status"], "admitted", laid)
        for thing in ("watercap/1", "plainpot/1"):
            citations = [l for l in self.component_info(thing)["laws"] if l["clause"] == 'under "kind/watercap"']
            self.assertEqual(len(citations), 1, citations)
            for n in range(3):
                used = self.turn(thing, "water", record(text=label("w" * 280)), principal=KIM)
                self.assertEqual(used["status"], "admitted", used)
            before = self.state(thing)
            fourth = self.turn(thing, "water", record(text=label("fourth")), principal=KIM)
            self.assertEqual((fourth["status"], fourth["receipt"]["outcome"].get("clause")), ("refused", "few"), fourth)
            self.assertEqual(self.state(thing), before)
        self.reopen()
        self.assertEqual(self.turn("plainpot/1", "water", record(text=label("after reopen")))["status"], "refused")

    def test_become_lays_all_bodies_of_the_deepest_stack_bottom_first(self):
        self.kind("waterroot", "record", "", body_source=self.water_body())
        below = "waterroot"
        for name in ("waterone", "watertwo", "waterthree"):
            self.kind(name, "kind/" + below, "", body_source=self.water_body(super_water=True))
            below = name
        self.kind("stackpot", "record", "")
        for kind in (below, "stackpot"):
            self.assertEqual(self.turn("kind/" + kind, "make", record())["status"], "admitted")
        laid = self.become("stackpot/1", "kind/" + below)
        self.assertEqual(laid["status"], "admitted", laid)
        for thing in (below + "/1", "stackpot/1"):
            used = self.turn(thing, "water", record(text=label("bottom reached")))
            self.assertEqual(used["status"], "admitted", used)
            self.assertEqual(self.component_lines(thing), [("water", "bottom reached")])

    def test_become_twice_keeps_one_component_one_citation_and_its_pin(self):
        self.kind("oncewater", "record", "", body_source=self.water_body(super_water=False))
        self.kind("oncepot", "record", "")
        for kind in ("oncewater", "oncepot"):
            self.assertEqual(self.turn("kind/" + kind, "make", record())["status"], "admitted")
        for thing in ("oncewater/1", "oncepot/1"):
            made = self.component_info(thing)
            first = self.become(thing, "kind/oncewater")
            self.assertEqual(first["status"], "admitted", first)
            if thing == "oncewater/1":
                self.assertFalse(first["receipt"]["outcome"].get("reprograms"), first)
                self.assertEqual((self.component_info(thing)["pin"], self.component_info(thing)["version"]),
                                 (made["pin"], made["version"]))
            before = self.component_info(thing)
            second = self.become(thing, "kind/oncewater")
            self.assertEqual(second["status"], "admitted", second)
            after = self.component_info(thing)
            self.assertEqual((after["pin"], after["source"], after["version"]),
                             (before["pin"], before["source"], before["version"]))
            self.assertFalse(second["receipt"]["outcome"].get("reprograms"), second)
            self.assertFalse(second["receipt"]["outcome"].get("amendments"), second)
            self.assertEqual(after["madeFrom"]["object"], "kind/oncewater")
            self.assertEqual(after["madeFrom"]["pin"], self.component_info("kind/oncewater")["pin"])
            self.assertEqual(sum(l["clause"] == 'under "kind/oncewater"' for l in after["laws"]), 1)
            self.assertEqual(self.turn(thing, "water", record(text=label("once")))["status"], "admitted")
            self.assertEqual(self.component_lines(thing), [("water", "once")])

    def test_become_upgrades_in_place_and_preserves_a_layer_above_it(self):
        stale = ('form stale:\ndef stale(state: State, context: Abi.Context) -> Activity<Nat>:\n'
                 '  Super.inscribe(state, "stale", "old code", context)\n')
        self.kind("freshwater", "record", "", body_source=self.water_body('"old"') + stale)
        self.assertEqual(self.turn("kind/freshwater", "make", record())["status"], "admitted")
        layer = '''layer over ./Record.obend
edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Form.obend as Form
import ./Text.obend as Text
type State = Super.State
form pour:
  text: text 1..280
def pour(state: State, input: PourInput, context: Abi.Context) -> Activity<Nat>:
  Super.inscribe(state, "pour", input.text, context)
def actions(state: State, context: Abi.Context) -> Lists.List<String>:
  Lists.concat(Super.actions(state, context), Text.words("pour"))
'''
        version = self.component_info("freshwater/1")["version"]
        added = self.host.send(op="world-reprogram", principal="ember", identity="above-water", object="freshwater/1",
                               version=version, package=layer, mode="extend")
        self.assertEqual(added["status"], "admitted", added)
        self.assertEqual(self.turn("freshwater/1", "water", record(text=label("ignored")))["status"], "admitted")
        version = self.component_info("kind/freshwater")["version"]
        fresh = (field(self.state("kind/freshwater"), "body")["value"].replace('"old"', '"new"')
                 .replace(stale, "").replace('Text.words("water stale")', 'Text.words("water")'))
        changed = self.host.send(op="world-propose", principal="ember", identity="fresh-body",
                                 roots=[{"object": "kind/freshwater", "version": version}],
                                 writes=[{"object": "kind/freshwater", "edits": [record(body={"tag": "variant", "label": "set",
                                                                                         "payload": record(value=label(fresh))})]}])
        self.assertEqual(changed["status"], "admitted", changed)
        snapshot = self.host.send(op="world-snapshot")
        self.assertEqual(snapshot["status"], "snapshot", snapshot)
        self.reopen()
        upgraded = self.become("freshwater/1", "kind/freshwater")
        self.assertEqual(upgraded["status"], "admitted", upgraded)
        gone = self.turn("freshwater/1", "stale")
        self.assertEqual(gone["receipt"]["outcome"]["class"], "noMethod", gone)
        self.assertEqual(self.turn("freshwater/1", "water", record(text=label("ignored")))["status"], "admitted")
        poured = self.turn("freshwater/1", "pour", record(text=label("the layer above still runs")))
        self.assertEqual(poured["status"], "admitted", poured)
        self.assertEqual([text for verb, text in self.component_lines("freshwater/1") if verb == "water"], ["old", "new"])
        info = self.component_info("freshwater/1")
        self.assertEqual(info["madeFrom"]["pin"], self.component_info("kind/freshwater")["pin"])
        self.assertEqual(info["madeFrom"]["receipt"], changed["receipt"]["hash"])
        self.reopen()
        again = self.become("freshwater/1", "kind/freshwater")
        self.assertEqual(again["status"], "admitted", again)
        self.assertFalse(again["receipt"]["outcome"].get("reprograms"), again)
        self.assertEqual(self.turn("freshwater/1", "water", record(text=label("ignored")))["status"], "admitted")
        self.assertEqual([text for verb, text in self.component_lines("freshwater/1") if verb == "water"], ["old", "new", "new"])

    def test_become_refuses_code_and_citation_together_under_the_things_law(self):
        self.kind("guardwater", "record", "", body_source=self.water_body())
        self.kind("guardpot", "record", "")
        self.assertEqual(self.turn("kind/guardpot", "make", record())["status"], "admitted")
        version = self.component_info("guardpot/1")["version"]
        amended = self.host.send(op="world-amend", principal="ember", identity="guard-amend", object="guardpot/1", version=version,
                                law=genesis.RECORD_LAW + '\nlaw code "no code laid": not (request.kind == reprogram)')
        self.assertEqual(amended["status"], "admitted", amended)
        before = self.component_info("guardpot/1")
        refused = self.become("guardpot/1", "kind/guardwater")
        self.assertEqual((refused["status"], refused["receipt"]["outcome"].get("clause")), ("refused", "code"), refused)
        self.assertEqual(self.component_info("guardpot/1"), before)


    def test_make_under_judges_text_fields_against_the_form_by_the_hosts_clauses(self):
        """A place hands a kind's makeUnder text, which no spell fitted: the kind judges it against its form as the
        host judges a make spell, and a value outside the form makes nothing (OBJECTS-HANDOFF, 4a's open findings)."""
        town_kinds(self.host.send)
        for fields, clause, reading in (([("colour", "verdigris"), ("seed", "x")], "badValue", "colour is one of: red, orange, yellow, green, cyan, blue, violet, amber, silver, magenta, purple, pink"),
                                        ([("colour", "amber")], "missing", "Still needs seed."),
                                        ([("colour", "amber"), ("seed", "x" * 81)], "badValue", "seed is 1 to 80 characters; this one is 81.")):
            with self.subTest(fields=fields):
                rows = {"tag": "list", "items": [record(name=label(n), value=label(v)) for n, v in fields]}
                r = self.turn("kind/bell", "makeUnder", record(under=label("yard"), fields=rows), principal=KIM)
                self.assertEqual(cast_refusal(r), (clause, reading), r)
        self.assertEqual(field(self.state("kind/bell"), "count")["value"], "0")

    def test_a_kind_from_a_name_and_what_it_is_of_alone(self):
        """PLAYTEST-2's first move: `kinds make / name / of`, the rest omitted (optional text fields), makes a kind
        whose make then makes a thing."""
        said = lambda who, obj, line: self.turn(obj, "receive", record(text=label(line), post=label("at://x/" + line[-8:])), principal=who)
        kind = said(KIM, "kinds", "delvetalk kinds make / name: lamp / of: record")
        self.assertEqual((kind["status"], kind["result"]["label"]), ("admitted", "made"), kind)
        lamp = said(GLM, "kind/lamp", "delvetalk kind/lamp make")
        self.assertEqual((lamp["status"], lamp["result"]["label"]), ("admitted", "made"), lamp)
        self.assertIn("Made, at lamp/1", text(lamp))

    def test_a_kind_with_no_law_clause_makes_things_its_maker_alone_amends_or_reprograms(self):
        """Codex objects 1: a kind made with no law, or with rules and wants alone, cited an empty text from every
        instance, which admitted any request: a stranger amended the maker's thing to admit himself and replaced
        its program. A kind whose text holds no law clause keeps its package's own law beside its rules and wants."""
        said = lambda who, obj, line: self.turn(obj, "receive", record(text=label(line), post=label("at://x/" + line[-8:])), principal=who)
        self.kind("loud", "record", "", law=genesis.RECORD_LAW, body_source=body("cistern"))
        for name, law in (("lamp", ""), ("wick", 'want lit "a wick nobody has lit": count(new.lines) == 0 asks delvetalk {request.object} write')):
            with self.subTest(law=law):
                kind = self.turn("kinds", "make", record(name=label(name), of=label("record"), form=label(""), head=label(""), voice=label(""), about=label(""), law=label(law), body=label("")), principal=KIM)
                self.assertEqual(kind["status"], "admitted", kind)
                made = self.turn("kind/" + name, "make", record(), principal=KIM)
                thing = made["result"]["payload"]["fields"][0]["value"]["value"]
                amended = said(GLM, thing, 'delvetalk %s adopt / law: law mine "glm writes": request.subject == "%s"' % (thing, GLM))
                self.assertEqual((amended["status"], amended["receipt"]["outcome"]["class"], amended["receipt"]["outcome"]["clause"]), ("refused", "lawRefused", "owner"), amended)
                reprogrammed = said(GLM, thing, "delvetalk %s become / kind: kind/loud" % thing)
                self.assertEqual((reprogrammed["status"], reprogrammed["receipt"]["outcome"].get("clause")), ("refused", "owner"), reprogrammed)
                if law:
                    self.assertIn("lit", [w["name"] for w in self.host.send(op="world-wants", principal=KIM, object=thing)["rows"]])
                wrote = self.turn(thing, "write", record(text=label("a stranger's line")), principal=GLM)
                self.assertEqual(wrote["status"], "admitted", wrote)
                # The owner's law is the thing's own, never the kind's.
                self.assertEqual(field(self.state("kind/" + name), "law")["value"], law)
                self.assertTrue(self.host.send(op="world-object", principal=KIM, object=thing)["record"]["law"].startswith(genesis.RECORD_LAW))

    def test_a_kinds_law_that_does_not_read_is_refused_by_name_and_makes_no_kind(self):
        """Playtest 2's D4 (69068, 69097): `law: writeOnce(claim)` made kind/prereg, whose every make was then refused
        and which could not be made again. A law is read as the kind is made: a line that is no clause, or a clause
        outside the law's grammar, is refused badValue with the law's line as the hint, and nothing is made."""
        said = lambda line, n: self.turn("kinds", "receive", record(text=label(line), post=label("at://x/law/%d" % n)), principal=KIM)
        for n, (law, why) in enumerate((("writeOnce(claim)", "law: `writeOnce(claim)` is no clause"),
                                        ('law q "x": new.owner = 3', "law: law outside the enforced fragment: `=`"))):
            with self.subTest(law=law):
                r = said("delvetalk kinds make / name: prereg / of: record / form: claim: text 1..80 / law: " + law, n)
                reason = r["receipt"]["outcome"]["reason"]
                self.assertEqual(cast_refusal(r)[0], "badValue", r)
                self.assertEqual(r["receipt"]["outcome"].get("writes", []), [], r)
                self.assertTrue(reason.startswith("refused badValue: " + why), reason)
                self.assertIn('One clause a line: law NAME "reading": EXPR, a rule ending then SPELL, a want asks SPELL; delvetalk library read / page: laws', reason)
        self.assertNotIn("kind/prereg", self.host.send(op="world-objects", principal="ember")["ids"])
        made = said('delvetalk kinds make / name: prereg / of: record / form: claim: text 1..80 / law: law once "a prereg never changes": unchanged(fields)', 9)
        self.assertEqual((made["status"], made["result"]["label"]), ("admitted", "made"), made)

    def test_an_exact_id_is_the_kind_owners_place_offered_to_them_alone(self):
        """Playtest 2's F5 (69132 to 69138): every kind's make offered `id:` to anyone, and only a refusal said it was
        the maker's. `make` names the thing; `place / id:` puts it at an exact id, the kind owner's, offered to them."""
        self.kind("lamp", "record", "light: text 1..80", law=genesis.RECORD_LAW)
        offered = lambda who: self.host.send(op="world-inspect", principal=who, object="kind/lamp", source=False)["offered"]
        self.assertIn("place", offered("ember"))
        self.assertNotIn("place", offered(KIM))
        self.assertIn("make", offered(KIM))
        stranger = self.turn("kind/lamp", "place", record(light=label("mine"), id=label("lamp/here")), principal=KIM)
        self.assertEqual(cast_refusal(stranger), ("notOwner", "Only ember places what this kind makes at an id; make it, and it is named"))
        self.assertEqual(stranger["receipt"]["outcome"].get("writes", []), [], stranger)
        placed = self.turn("kind/lamp", "place", record(light=label("the hand's"), id=label("lamp/here")), principal="ember")
        self.assertEqual(placed["result"], {"tag": "variant", "label": "made", "payload": record(object=label("lamp/here"))}, placed)
        made = self.turn("kind/lamp", "make", record(light=label("anyone's")), principal=KIM)
        self.assertEqual(made["result"]["payload"], record(object=label("lamp/1")), made)

    def test_a_kind_is_shaped_once(self):
        """The live redeploy: `kinds shape` a second time laid a layer over the package's module, which a shaped
        kind no longer runs, and the compile refused it. A shaped kind, or one `kinds` made, is refused by name."""
        for target in ("kinds", "kind/key"):
            if target == "kind/key":
                self.kind("key", "record", "seed: text 1..80", law=genesis.RECORD_LAW)
            again = self.turn(target, "shape", record(object=label(target)))
            self.assertEqual(cast_refusal(again)[0], "shaped", again)
            self.assertTrue(again["receipt"]["outcome"]["reason"].startswith("refused shaped: Already shaped; its make stands"), again)

    def test_making_a_kind_and_its_thing_journals_no_refused_delivery(self):
        """A made kind has no `made`; only a made record with a body is sent one (the host lane's finding: every
        kind creation journaled a delivered noMethod)."""
        def refusals(reply):
            got = reply.get("delivered", []) + [d for x in self.deliver_all() for d in x.get("delivered", []) + x.get("receipts", [])]
            return [d for d in got if (d.get("receipt", d).get("outcome") or {}).get("class") not in (None, "", "admitted")]
        made = self.turn("kinds", "make", record(name=label("cairn"), of=label("record"), form=label(""), head=label("A CAIRN"), voice=label(""), about=label(""), law=label(genesis.RECORD_LAW),
                                                body=label(body("cistern"))), principal=KIM)
        self.assertEqual((made["status"], refusals(made)), ("admitted", []), made)
        thing = self.turn("kind/cairn", "make", record(), principal=GLM)
        self.assertEqual((thing["status"], thing["result"]["label"], refusals(thing)), ("admitted", "made", []), thing)

    def test_a_kind_of_record_makes_a_record_under_its_law_with_its_head(self):
        self.kind("key", "record", "seed: text 1..80", head="THE KEY, begun by {maker}: {seed}", law=genesis.RECORD_LAW)
        made = self.turn("kind/key", "make", record(seed=label("three hands deep")), principal=KIM)
        self.assertEqual(made["status"], "admitted", made)
        self.assertEqual(made["result"]["label"], "made", made)
        state = self.state("key/1")
        self.assertEqual(field(state, "head")["value"], "THE KEY, begun by kimik3: three hands deep")
        self.assertEqual(field(state, "owner")["value"], KIM)
        self.assertEqual(field(state, "kind")["value"], "kind/key")
        wrote = self.turn("key/1", "write", record(text=label("coined by the room itself")), principal=GLM)
        self.assertEqual(wrote["status"], "admitted", wrote)
        self.assertIn("Made, at key/1; 1 made.", text(made))
        self.assertIn("THE KEY, begun by kimik3: three hands deep", text(self.turn("key/1", "receive", record(text=label(""), post=label("")), principal=GLM)))

    def test_the_cistern_kind_pours_and_its_level_only_rises(self):
        self.kind("cistern", "record", "", law=genesis.RECORD_LAW, body_source=body("cistern"))
        self.assertEqual(self.turn("kind/cistern", "make", record(), principal=GLM)["status"], "admitted")
        poured = self.turn("cistern/1", "pour", record(text=label("refused tooSoon: the next tick from clock 480")), principal=KIM)
        self.assertEqual(poured["status"], "admitted", poured)
        self.assertIn("CISTERN, dug by glm; level 1. Pour a refusal in:\n  delvetalk cistern/1 pour / text: <the refusal, 1 to 280 characters>\n", text(poured))
    # --- ROOM and making under a record ---------------------------------------------------------

    def card(self, obj, principal="visitor"):
        return text(self.turn(obj, "receive", record(text=label(""), post=label("")), principal=principal))

    def test_kind_room_makes_a_room_whose_body_is_laid_in_the_turn_that_makes_it(self):
        self.kind("room", "record", "name: text 1..64", head="{name}", law=genesis.RECORD_LAW, body_source=body("room"))
        made = self.turn("kind/room", "make", record(name=label("The Reading Room")), principal=KIM)
        self.assertEqual((made["status"], made["result"]["label"]), ("admitted", "made"), made)
        room = self.state("room/1")
        self.assertEqual((field(room, "head")["value"], field(room, "owner")["value"]), ("The Reading Room", KIM))
        laws = self.host.send(op="world-inspect", principal=KIM, object="room/1")["laws"]
        # The room's owner's law, its own, then kind/room's, cited (`under "kind/room"`).
        self.assertEqual([l["name"] for l in laws], ["owner", "kept", "methods", "pending", "door", "kind"])
        self.assertEqual(self.turn("room/1", "enter", principal=GLM)["result"]["label"], "entered")
        self.assertIn("The Reading Room (1 here), you are here.\n", self.card("room/1", GLM))
        self.assertIn("The Reading Room (1 here). Enter: delvetalk room/1 enter.\n", self.card("room/1"))
        said = self.turn("room/1", "say", record(line=label("attention without record")), principal=GLM)
        self.assertEqual([(o["to"], o["text"]) for o in said["receipt"]["offers"]], [(GLM, "glm: attention without record\n")])
        # the record's write stays: a visit is a line the visitor writes
        self.assertEqual(self.turn("room/1", "write", record(text=label("Visit: glm / Took: nothing / Left: a margin line")), principal=GLM)["status"], "admitted")

    def test_prose_in_spween_is_a_scene_of_one_passage_and_choices_with_no_passage_are_refused_by_name(self):
        """Playtest 2 F3: prose in `spween:` made a room with no scene, silently. Prose alone is now a scene of one
        passage, kept; choices with no passage to hold them are refused with the line to add, nothing made."""
        self.kind("room", "record", "name: text 1..64\nspween: text 0..16384", head="{name}", law=genesis.RECORD_LAW, body_source=body("room"))
        bad = self.turn("kind/room", "make", record(name=label("The Annex"), spween=label("a quiet annex\n* [Look out]")), principal=KIM)
        self.assertEqual(cast_refusal(bad), ("spween", "The spween is not a scene: a scene needs === start; add it above your prose"), bad)
        self.assertEqual(self.host.send(op="world-view", principal=KIM, object="room/1").get("status"), "unknown")
        made = self.turn("kind/room", "make", record(name=label("The Annex"), spween=label("a quiet annex with a window")), principal=KIM)
        self.assertEqual(made["result"]["label"], "made", made)
        state = {f["name"]: f["value"] for f in self.host.send(op="world-view", principal=KIM, object="room/1")["state"]["fields"]}
        self.assertEqual(state["start"]["value"], "start")
        self.assertIn("a quiet annex with a window", str(state["passages"]))

    def test_a_room_mints_past_an_id_already_held(self):
        """The host takes the first free <prefix><n> (HOST-HANDOFF §4), so a squatted id stops no kind."""
        self.kind("room", "record", "name: text 1..64", head="{name}", law=genesis.RECORD_LAW, body_source=body("room"))
        squat = self.host.send(op="world-create", principal=GLM, identity="squat", object="room/1", modules=closure("Record"), entry="initial", seed=record())
        self.assertEqual(squat["status"], "created", squat)
        made = self.turn("kind/room", "make", record(name=label("The Porch")), principal=KIM)
        self.assertEqual(made["result"]["label"], "made", made)
        self.assertIn("Made, at room/2; 1 made.", text(made))

    def test_a_spween_block_posted_to_a_room_makes_a_room_under_it(self):
        self.kind("room", "record", "name: text 1..64", head="{name}", law=genesis.RECORD_LAW, body_source=body("room"))
        self.turn("kind/room", "make", record(name=label("The Porch")), principal=KIM)
        spween = "a tube between porch and ledger:\n\n```spween\n---\nid: tube\ntitle: The Tube\n---\n=== mouth\nA scratch comes down the tube.\n* [Listen] -> END\n```"
        r = self.turn("room/1", "receive", record(text=label(spween), post=label("at://x/1")), principal=GLM)
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(text(r), "ROOM The Tube is at room/1/room/1. Enter: delvetalk room/1/room/1 enter\n")
        tube = self.state("room/1/room/1")
        self.assertEqual((field(tube, "head")["value"], field(tube, "start")["value"], field(tube, "owner")["value"]), ("The Tube", "mouth", GLM))
        self.assertEqual(self.turn("room/1/room/1", "enter", principal=KIM)["result"]["label"], "entered")
        self.assertIn("you are at mouth:\nA scratch comes down the tube.\nChoices:\n  * Listen\n", self.card("room/1/room/1", KIM))
        self.assertEqual(self.turn("room/1/room/1", "choose", record(choice=label("Listen")), principal=KIM)["result"]["label"], "left")

    def yard(self, makes=("kind/bell",)):
        """A record that makes bells, with a body whose `makes` names the kinds and whose `plant` names one, as the
        garden's body does (world/bodies/garden.obend)."""
        town_kinds(self.host.send)
        r = self.host.send(op="world-create", principal="ember", identity="mk-yard", object="yard", modules=closure("Record"), entry="initial",
                           seed=record(owner=label("ember"), head=label("THE YARD")), law=genesis.RECORD_LAW)
        self.assertEqual(r["status"], "created", r)
        kinds = " ".join(makes)
        plant = ("layer over ./Record.obend\nedition ObjectiveBend 1\nimport ./Abi.obend as Abi\nimport ./List.obend as Lists\nimport ./Document.obend as Document\n"
                 "import ./Rows.obend as Rows\nimport ./Form.obend as Form\nimport ./Text.obend as Text\n"
                 "type State = Super.State\nform plant:\n  colour: amber | violet | silver\n  seed: text 1..80\n"
                 "def makes(state: State) -> Lists.List<String>:\n  Text.words(\"%s\")\n"
                 "def plant(state: State, input: PlantInput, context: Abi.Context) -> Activity<Super.Made>:\n"
                 "  Super.making(state, \"kind/bell\", Lists.List.cons({head: {name: \"colour\", value: plantColourText(input.colour)}, tail: Lists.List.cons({head: {name: \"seed\", value: input.seed}, tail: Lists.List.nil()})}), context, Super.madeLine, fn(m: Super.Made) -> Super.Made: m)\n"
                 "def plantColourText(c: PlantColour) -> String:\n  match c:\n    case amber(_): \"amber\"\n    case violet(_): \"violet\"\n    case silver(_): \"silver\"\n") % kinds
        r = self.host.send(op="world-reprogram", principal="ember", identity="plant", object="yard", version=0, package=plant, mode="extend")
        self.assertEqual(r["status"], "admitted", r)

    def test_a_record_that_makes_bells_makes_one_under_itself_citing_it_home(self):
        self.yard()
        made = self.turn("yard", "plant", record(colour=choice("silver"), seed=label("moths")), principal=KIM)
        self.assertEqual((made["status"], made["result"]["label"]), ("admitted", "made"), made)
        self.assertEqual(text(made), "Made, at yard/bell/1.\n")
        bell = self.state("yard/bell/1")
        self.assertEqual((field(bell, "kind")["value"], field(bell, "owner")["value"]), ("kind/bell", KIM))
        [door] = field(bell, "cites")["items"]
        self.assertEqual([f["value"]["value"] for f in door["fields"] if f["name"] == "label"], ["yard"])
        self.assertIn("A silver bell, planted by kimik3", self.card("yard/bell/1"))
        refused = self.turn("yard", "plant", record(colour=choice("silver"), seed=label("x" * 81)), principal=KIM)
        self.assertEqual(refused["status"], "refused", refused)

    def test_a_kind_the_record_does_not_make_is_refused_by_name(self):
        self.yard(makes=())
        made = self.turn("yard", "plant", record(colour=choice("amber"), seed=label("x")), principal=KIM)
        self.assertEqual(cast_refusal(made), ("notMade", "This record makes nothing."))
        self.assertEqual(field(self.state("kind/bell"), "count")["value"], "0")

    def test_the_fullest_room_card_stays_under_the_limit(self):
        """Longest name and doors; 32 present and 64 lying; eight lines; the reader in the room at a long passage."""
        from tests.test_rooms import make_room
        people = ["did:plc:" + ("%02d" % i) * 12 for i in range(32)]
        things = ["thing-%02d-" % i + "x" * 100 for i in range(64)]
        doors = [record(label=label(("door%d-" % i).ljust(32, "d")), to=reference("elsewhere/" + "y" * 100), description=label(""), examples=listing([])) for i in range(8)]
        make_room(self, "yard", head=label("N" * 120), cites=listing(doors), presence=relation(*[record(who=label(p), handle=label(""), at=label(""), draw=nat(0)) for p in sorted(people, key=lambda i: (len(i), i))]),
                  things=relation(*[reference(t) for t in sorted(things, key=lambda i: (len(i), i))]))
        for i in range(8):
            self.turn("yard", "write", record(text=label("w" * 280)), principal=people[i])
        reply = self.turn("yard", "receive", record(text=label(""), post=label("")), principal=people[0])
        card = reply["offers"][0]["text"].split("\nReply with a spell:")[0]
        self.assertLess(len(card), 1400, card)
        print("\n  fullest room: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(card)))
        self.assertLess(reply["ticksUsed"], 1000000)

    def test_a_kept_record_wants_its_keeper_while_a_line_waits_past_its_retention(self):
        """Codex objects 9: `pending` compared counts of lines and admissions, which retention drops on their own: past
        128 lines, the keeper having admitted them all, line 129 waited while both counts stood at 128 and the record
        wanted nothing. A kept record keeps its waiting lines' numbers, dropped on admission and with their lines."""
        r = self.host.send(op="world-create", principal="ember", identity="mk-ledger", object="ledger", modules=closure("Record"),
                           entry="initial", seed=record(owner=label("ember"), keeper=label("ember")), law=genesis.RECORD_LAW)
        self.assertEqual(r["status"], "created", r)
        wants = lambda: [w["name"] for w in self.host.send(op="world-wants", principal="ember", object="ledger")["rows"]]
        for n in range(1, 129):
            self.assertEqual(self.turn("ledger", "write", record(text=label("line %d" % n)), principal=KIM)["status"], "admitted")
            self.assertEqual(self.turn("ledger", "admit", record(number={"tag": "natural", "value": str(n)}), principal="ember")["status"], "admitted")
        self.assertNotIn("pending", wants())
        self.assertEqual(self.turn("ledger", "write", record(text=label("line 129")), principal=KIM)["status"], "admitted")
        self.assertIn("pending", wants())
        self.assertEqual(self.turn("ledger", "admit", record(number={"tag": "natural", "value": "129"}), principal="ember")["status"], "admitted")
        self.assertNotIn("pending", wants())

    def test_a_kinds_law_is_the_package_s_own(self):
        from tests.test_objects import run_pure
        self.assertEqual(run_pure("Kind", "lawText")["value"]["value"], genesis.KIND_LAW)
        self.assertEqual(run_pure("Record", "lawText")["value"]["value"], genesis.RECORD_LAW)


if __name__ == "__main__":
    unittest.main()
