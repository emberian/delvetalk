"""KIND makes things: `kinds` makes a kind, a kind makes an instance of its package under its law,
and a kind with a body grafts it on each instance (docs/CATALOGUE.md §3, §5 step 3).

Evidence for FOUNDATION §8 extend (layer: objects).

Refuted by: a kind whose make takes other fields than its form; an instance made without the
kind's law or head; a bell body that does not ring on `ring` or takes a rain over 200 characters.
"""
import os
import unittest

from deploy import genesis
from tests.test_chain import Chain, field, reference, town_kinds
from tests.test_rooms import listing
from tests.test_turn_world import relation
from tests.test_objects import closure
from tests.test_turn_world import label, nat, record

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
                self.assertEqual((r["status"], r["result"]["label"]), ("admitted", "refused"), r)
                self.assertEqual([f["value"]["value"] for f in r["result"]["payload"]["fields"]], [clause, reading], r)
        self.assertEqual(field(self.state("kind/bell"), "count")["value"], "0")

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
        self.assertEqual(self.turn("kind/cistern", "make", principal=GLM)["status"], "admitted")
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
        self.deliver_all()
        room = self.state("room/1")
        self.assertEqual((field(room, "head")["value"], field(room, "owner")["value"]), ("The Reading Room", KIM))
        laws = self.host.send(op="world-inspect", principal=KIM, object="room/1")["laws"]
        self.assertEqual([l["name"] for l in laws], ["owner", "kept"])
        self.assertEqual(self.turn("room/1", "enter", principal=GLM)["result"]["label"], "entered")
        self.assertIn("The Reading Room (1 here), you are here.\n", self.card("room/1", GLM))
        self.assertIn("The Reading Room (1 here). Enter: delvetalk room/1 enter.\n", self.card("room/1"))
        said = self.turn("room/1", "say", record(line=label("attention without record")), principal=GLM)
        self.assertEqual([(o["to"], o["text"]) for o in said["receipt"]["offers"]], [(GLM, "glm: attention without record\n")])
        # the record's write stays: a visit is a line the visitor writes
        self.assertEqual(self.turn("room/1", "write", record(text=label("Visit: glm / Took: nothing / Left: a margin line")), principal=GLM)["status"], "admitted")

    def test_a_room_mints_past_an_id_already_held(self):
        """The host takes the first free <prefix><n> (HOST-HANDOFF 5.127), so a squatted id stops no kind."""
        self.kind("room", "record", "name: text 1..64", head="{name}", law=genesis.RECORD_LAW, body_source=body("room"))
        squat = self.host.send(op="world-create", principal=GLM, identity="squat", object="room/1", modules=closure("Record"), entry="initial", seed=record())
        self.assertEqual(squat["status"], "created", squat)
        made = self.turn("kind/room", "make", record(name=label("The Porch")), principal=KIM)
        self.assertEqual(made["result"]["label"], "made", made)
        self.deliver_all()
        self.assertIn("Made, at room/2; 1 made.", text(made))

    def test_a_spween_block_posted_to_a_room_makes_a_room_under_it(self):
        self.kind("room", "record", "name: text 1..64", head="{name}", law=genesis.RECORD_LAW, body_source=body("room"))
        self.turn("kind/room", "make", record(name=label("The Porch")), principal=KIM)
        spween = "a tube between porch and ledger:\n\n```spween\n---\nid: tube\ntitle: The Tube\n---\n=== mouth\nA scratch comes down the tube.\n* [Listen] -> END\n```"
        self.deliver_all()
        r = self.turn("room/1", "receive", record(text=label(spween), post=label("at://x/1")), principal=GLM)
        self.assertEqual(r["status"], "admitted", r)
        self.deliver_all()
        self.assertEqual(text(r), "ROOM The Tube is at room/1/room/1. Enter: delvetalk room/1/room/1 enter\n")
        tube = self.state("room/1/room/1")
        self.assertEqual((field(tube, "head")["value"], field(tube, "start")["value"], field(tube, "owner")["value"]), ("The Tube", "mouth", GLM))
        self.assertEqual(self.turn("room/1/room/1", "enter", principal=KIM)["result"]["label"], "entered")
        self.assertIn("you are at mouth:\nA scratch comes down the tube.\nChoices:\n  * Listen\n", self.card("room/1/room/1", KIM))
        self.assertEqual(self.turn("room/1/room/1", "choose", record(choice=label("Listen")), principal=KIM)["result"]["label"], "left")

    def yard(self, makes=("kind/bell",)):
        """A record that makes bells, with a body whose `plant` names the kind, as a garden's does."""
        town_kinds(self.host.send)
        r = self.host.send(op="world-create", principal="ember", identity="mk-yard", object="yard", modules=closure("Record"), entry="initial",
                           seed=record(owner=label("ember"), head=label("THE YARD"), makes=listing([reference(k) for k in makes])), law=genesis.RECORD_LAW)
        self.assertEqual(r["status"], "created", r)
        plant = ("layer over ./Record.obend\nedition ObjectiveBend 1\nimport ./Abi.obend as Abi\nimport ./List.obend as Lists\nimport ./Rows.obend as Rows\nimport ./Form.obend as Form\n"
                 "type State = Super.State\nform plant:\n  colour: amber | violet | silver\n  seed: text 1..80\n"
                 "def plant(state: State, input: PlantInput, context: Abi.Context) -> Activity<Super.Made>:\n"
                 "  Super.making(state, \"kind/bell\", Lists.List.cons({head: {name: \"colour\", value: plantColourText(input.colour)}, tail: Lists.List.cons({head: {name: \"seed\", value: input.seed}, tail: Lists.List.nil()})}), context)\n"
                 "def plantColourText(c: PlantColour) -> String:\n  match c:\n    case amber(_): \"amber\"\n    case violet(_): \"violet\"\n    case silver(_): \"silver\"\n")
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
        self.assertEqual(made["result"]["label"], "refused", made)
        self.assertEqual([f["value"]["value"] for f in made["result"]["payload"]["fields"]], ["notMade", "This record makes nothing."])
        self.assertEqual(field(self.state("kind/bell"), "count")["value"], "0")

    def test_the_fullest_room_card_stays_under_the_limit(self):
        """Longest name and doors; 32 present and 64 lying; eight lines; the reader in the room at a long passage."""
        from tests.test_rooms import make_room
        people = ["did:plc:" + ("%02d" % i) * 12 for i in range(32)]
        things = ["thing-%02d-" % i + "x" * 100 for i in range(64)]
        doors = [record(label=label(("door%d-" % i).ljust(32, "d")), to=reference("elsewhere/" + "y" * 100)) for i in range(8)]
        make_room(self, "yard", head=label("N" * 120), cites=listing(doors), presence=relation(*[record(who=label(p), at=label("")) for p in sorted(people, key=lambda i: (len(i), i))]),
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
