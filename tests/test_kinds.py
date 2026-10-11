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
from tests.wire import cast_refusal, field, label, listing, record, reference, relation
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
        r = self.turn("kinds", "make", record(name=label(name), of=label(of), form=label(form), head=label(head), law=label(law), body=label(body_source)))
        self.assertEqual(r["status"], "admitted", r)
        return r

    def test_make_under_judges_text_fields_against_the_form_by_the_hosts_clauses(self):
        """A place hands a kind's makeUnder text, which no spell fitted: the kind judges it against its form as the
        host judges a make spell, and a value outside the form makes nothing (OBJECTS-HANDOFF, 4a's open findings)."""
        town_kinds(self.host.send)
        for fields, clause, reading in (([("colour", "green"), ("seed", "x")], "badValue", "colour is one of: amber, violet, silver"),
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
                self.assertIn('One clause a line: law NAME "reading": EXPR; delvetalk library read / page: laws', reason)
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
        made = self.turn("kinds", "make", record(name=label("cairn"), of=label("record"), form=label(""), head=label("A CAIRN"), law=label(genesis.RECORD_LAW),
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
        self.assertEqual([l["name"] for l in laws], ["kind"])  # kind/room's law, cited (`under "kind/room"`)
        self.assertEqual(self.turn("room/1", "enter", principal=GLM)["result"]["label"], "entered")
        self.assertIn("The Reading Room (1 here), you are here.\n", self.card("room/1", GLM))
        self.assertIn("The Reading Room (1 here). Enter: delvetalk room/1 enter.\n", self.card("room/1"))
        said = self.turn("room/1", "say", record(line=label("attention without record")), principal=GLM)
        self.assertEqual([(o["to"], o["text"]) for o in said["receipt"]["offers"]], [(GLM, "glm: attention without record\n")])
        # the record's write stays: a visit is a line the visitor writes
        self.assertEqual(self.turn("room/1", "write", record(text=label("Visit: glm / Took: nothing / Left: a margin line")), principal=GLM)["status"], "admitted")

    def test_a_spween_that_is_no_scene_is_refused_by_name(self):
        """Playtest 2 F3: prose in `spween:` made a room with no scene, silently."""
        self.kind("room", "record", "name: text 1..64\nspween: text 0..16384", head="{name}", law=genesis.RECORD_LAW, body_source=body("room"))
        made = self.turn("kind/room", "make", record(name=label("The Annex"), spween=label("a quiet annex with a window")), principal=KIM)
        self.assertEqual(cast_refusal(made)[0], "spween", made)
        self.assertEqual(self.host.send(op="world-view", principal=KIM, object="room/1").get("status"), "unknown")

    def test_a_room_mints_past_an_id_already_held(self):
        """The host takes the first free <prefix><n> (HOST-HANDOFF 5.127), so a squatted id stops no kind."""
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
        make_room(self, "yard", head=label("N" * 120), cites=listing(doors), presence=relation(*[record(who=label(p), handle=label(""), at=label("")) for p in sorted(people, key=lambda i: (len(i), i))]),
                  things=relation(*[reference(t) for t in sorted(things, key=lambda i: (len(i), i))]))
        for i in range(8):
            self.turn("yard", "write", record(text=label("w" * 280)), principal=people[i])
        reply = self.turn("yard", "receive", record(text=label(""), post=label("")), principal=people[0])
        card = reply["offers"][0]["text"].split("\nReply with a spell:")[0]
        self.assertLess(len(card), 1400, card)
        print("\n  fullest room: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(card)))
        self.assertLess(reply["ticksUsed"], 1000000)

    def test_a_kinds_law_is_the_package_s_own(self):
        from tests.test_objects import run_pure
        self.assertEqual(run_pure("Kind", "lawText")["value"]["value"], genesis.KIND_LAW)
        self.assertEqual(run_pure("Record", "lawText")["value"]["value"], genesis.RECORD_LAW)


if __name__ == "__main__":
    unittest.main()
