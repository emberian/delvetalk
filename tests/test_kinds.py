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
from tests.test_places import keyed, listing, make_place
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

    def test_the_bell_kind_grafts_its_body_and_the_seventh_rain_can_ring_it(self):
        self.kind("bell", "record", "colour: amber | violet | silver\nseed: text 1..80", law=genesis.RECORD_LAW, body_source=body("bell"))
        made = self.turn("kind/bell", "make", record(colour={"tag": "variant", "label": "silver", "payload": record()}, seed=label("a bell for lost moths")), principal=KIM)
        self.assertEqual(made["status"], "admitted", made)
        self.assertIn("Made, at bell/1; 1 made.", text(made))
        card = text(self.turn("bell/1", "receive", record(text=label(""), post=label("")), principal=GLM))
        self.assertIn("A silver bell, planted by kimik3: “a bell for lost moths” — silent. Rain on it:\n  delvetalk bell/1 rain / text: <1 to 200 characters>\n", card)
        rained = self.turn("bell/1", "rain", record(text=label("it rained here first")), principal=GLM)
        self.assertEqual(rained["status"], "admitted", rained)
        self.assertIn("glm (yours): it rained here first\n", text(rained))
        long = self.turn("bell/1", "write", record(text=label("x" * 201)), principal=GLM)
        self.assertEqual(long["status"], "refused", long)
        self.assertEqual(self.turn("bell/1", "ring", principal=GLM)["status"], "admitted")
        self.assertIn("— rung.", text(self.turn("bell/1", "receive", record(text=label(""), post=label("")), principal=GLM)))

    def test_the_cistern_kind_pours_and_its_level_only_rises(self):
        self.kind("cistern", "record", "", law=genesis.RECORD_LAW, body_source=body("cistern"))
        self.assertEqual(self.turn("kind/cistern", "make", principal=GLM)["status"], "admitted")
        poured = self.turn("cistern/1", "pour", record(text=label("refused tooSoon: the next tick from clock 480")), principal=KIM)
        self.assertEqual(poured["status"], "admitted", poured)
        self.assertIn("CISTERN, dug by glm; level 1. Pour a refusal in:\n  delvetalk cistern/1 pour / text: <the refusal, 1 to 280 characters>\n", text(poured))
    # --- PLACE: a place makes the kinds in `makes` under itself ------------------------------

    def yard(self, makes=("kind/bell",), keep=None):
        town_kinds(self.host.send)
        fields = dict(owner=label("ember"), name=label("Yard"), description=label("a yard"),
                      makes=listing([reference(k) for k in makes]))
        if keep is not None:
            fields["keep"] = nat(keep)
        make_place(self, "yard", record(**fields))

    def card(self, obj, principal="visitor"):
        return text(self.turn(obj, "receive", record(text=label(""), post=label("")), principal=principal))

    def test_kind_place_makes_a_place_under_the_place_law_whose_maker_keeps_no_traces_by_a_lens(self):
        self.kind("place", "place", "name: text 1..64", law=genesis.PLACE_LAW)
        state = self.state("kind/place")
        self.assertEqual((field(state, "of")["value"], field(state, "law")["value"]), ("place", genesis.PLACE_LAW))
        # docs/CATALOGUE.md section 4: the Reading Room, attention without record.
        made = self.turn("kind/place", "make", record(name=label("The Reading Room")), principal=KIM)
        self.assertEqual((made["status"], made["result"]["label"]), ("admitted", "made"), made)
        room = self.state("place/1")
        self.assertEqual((field(room, "owner")["value"], field(room, "name")["value"], field(room, "keep")["value"]), (KIM, "The Reading Room", "64"))
        laws = self.host.send(op="world-inspect", principal=KIM, object="place/1")["laws"]
        self.assertEqual([(l["name"], l.get("reading")) for l in laws], [("owner", genesis.PLACE_LAW.split('"')[1])])
        quiet = self.turn("place/1", "receive", record(text=label("delvetalk place/1 set\ntraces: 0"), post=label("")), principal=KIM)
        self.assertEqual(quiet["status"], "admitted", quiet)
        self.assertEqual(field(self.state("place/1"), "keep")["value"], "0")
        self.assertEqual(self.turn("place/1", "enter", principal=GLM)["status"], "admitted")
        self.assertNotIn("Traces", self.card("place/1"))
        # A stranger's set is refused by name; the law refuses the same write any other way.
        other = self.turn("place/1", "receive", record(text=label("delvetalk place/1 set\ntraces: 9"), post=label("")), principal=GLM)
        self.assertIn("Only the room's owner changes it", text(other))
        self.assertEqual(field(self.state("place/1"), "keep")["value"], "0")

    def test_a_place_that_makes_bells_is_shaped_by_its_owner_and_a_bell_hangs_under_it(self):
        self.yard()
        self.assertNotIn("Make one", self.card("yard"))
        refused = self.turn("yard", "shape", record(object=label("yard")), principal=KIM)
        self.assertEqual(refused["result"]["payload"]["fields"][0]["value"]["value"], "notOwner", refused)
        shaped = self.turn("yard", "shape", record(object=label("yard")))
        self.assertEqual(shaped["status"], "admitted", shaped)
        self.assertEqual(shaped["result"]["label"], "done", shaped)
        self.assertIn("Make one: delvetalk yard make / kind: <bell> / colour: <amber | violet | silver> / seed: <text 1..80>\n", self.card("yard"))
        made = self.turn("yard", "make", record(kind=choice("bell"), colour=choice("silver"), seed=label("moths")), principal=KIM)
        self.assertEqual(made["status"], "admitted", made)
        self.assertEqual(made["result"]["label"], "made", made)
        self.assertEqual(text(made), "Made, at yard/bell/1; 1 made here.\n")
        bell = self.state("yard/bell/1")
        self.assertEqual(field(bell, "kind")["value"], "kind/bell")
        self.assertEqual(field(bell, "owner")["value"], KIM)
        [door] = field(bell, "doors")["items"]
        self.assertEqual([f["value"]["value"] for f in door["fields"] if f["name"] == "label"], ["yard"])
        yard = self.state("yard")
        self.assertEqual(field(yard, "count")["value"], "1")
        [row] = field(yard, "made")["payload"]["fields"][0]["value"]["items"]
        self.assertEqual({f["name"]: f["value"]["value"] for f in row["fields"]}, {"object": "yard/bell/1", "kind": "kind/bell", "n": "1"})
        self.assertIn("1 made here, newest first:\n- yard/bell/1\n", self.card("yard"))
        self.assertIn("A silver bell, planted by kimik3", self.card("yard/bell/1"))
        offered = self.host.send(op="world-inspect", principal="visitor", object="yard")["offered"]
        self.assertEqual(sorted(offered), ["emote", "make", "say", "whisper"])
        self.assertEqual(sorted(self.host.send(op="world-inspect", principal="ember", object="yard")["offered"]),
                         ["door", "emote", "make", "say", "shape", "undoor", "whisper"])
        # the layer re-declares the base forms: the room still talks and keeps doors
        self.assertEqual(self.turn("yard", "enter", record(), principal=KIM)["result"]["label"], "done")
        self.assertEqual(self.turn("yard", "say", record(line=label("hello")), principal=KIM)["result"]["label"], "done")
        doored = self.turn("yard", "door", record(label=label("gate"), to=label("garden")))
        self.assertEqual((doored["status"], doored["result"]["label"]), ("admitted", "done"), doored)
        self.assertIn("Doors: gate\n", self.card("yard"))
        self.assertEqual(self.turn("yard", "undoor", record(label=label("gate")))["result"]["label"], "done")

    def test_a_kind_the_place_does_not_make_is_refused_by_name(self):
        self.yard()
        rogue = ("layer over ./Place.obend\nedition ObjectiveBend 1\nimport ./Abi.obend as Abi\nimport ./List.obend as Lists\nimport ./Rows.obend as Rows\nimport ./Form.obend as Form\n"
                 "type State = Super.State\nform rogue:\n  seed: text 1..80\n"
                 "def rogue(state: State, input: RogueInput, context: Abi.Context) -> Activity<Super.Result>:\n"
                 "  Super.making(state, \"kind/cistern\", Lists.List::<Rows.Field>.nil(), context)\n")
        r = self.host.send(op="world-reprogram", principal="ember", identity="rogue", object="yard", version=0, package=rogue, mode="extend")
        self.assertEqual(r["status"], "admitted", r)
        made = self.turn("yard", "rogue", record(seed=label("x")), principal=KIM)
        self.assertEqual(made["result"]["label"], "refused", made)
        self.assertEqual([f["value"]["value"] for f in made["result"]["payload"]["fields"]], ["notMade", "This place makes bell."])
        self.assertEqual(field(self.state("yard"), "count")["value"], "0")

    def test_a_place_that_makes_nothing_cannot_be_shaped(self):
        self.yard(makes=())
        shaped = self.turn("yard", "shape", record(object=label("yard")))
        self.assertEqual([f["value"]["value"] for f in shaped["result"]["payload"]["fields"]], ["notMade", "This place makes nothing."])

    def test_a_place_kept_at_zero_writes_no_trace(self):
        self.yard(makes=(), keep=0)
        self.assertEqual(self.turn("yard", "enter", record(), principal=KIM)["result"]["label"], "done")
        self.assertEqual(self.turn("yard", "enter", record(), principal=KIM)["result"]["label"], "refused")
        self.assertEqual(field(self.state("yard"), "traces")["payload"]["fields"][0]["value"]["items"], [])
        self.assertNotIn("Traces", self.card("yard", KIM))
        self.assertIn("You are here.\n", self.card("yard", KIM))

    def test_a_full_place_card_stays_under_the_limit(self):
        self.yard()
        self.turn("yard", "shape", record(object=label("yard")))
        for i in range(3):
            self.turn("yard", "make", record(kind=choice("bell"), colour=choice("amber"), seed=label("s%d" % i)), principal=KIM)
        card = self.card("yard", KIM)
        self.assertIn("3 made here, newest first:\n- yard/bell/3\n- yard/bell/2\n- yard/bell/1\n", card)
        self.assertLess(len(card), 1400)

    def test_the_fullest_place_card_stays_under_the_limit(self):
        """Longest name, description and doors; a full make line; 64 present and 64 lying; ten made; a trace on top."""
        town_kinds(self.host.send)
        people = ["did:plc:" + ("%02d" % i) * 12 for i in range(64)]
        things = ["thing-%02d-" % i + "x" * 100 for i in range(64)]
        doors = [record(label=label(("door%d-" % i).ljust(32, "d")), to=reference("elsewhere/" + "y" * 100)) for i in range(8)]
        make_place(self, "yard", record(owner=label("ember"), name=label("N" * 64), description=label("d" * 280), exits=listing(doors),
                                        makes=listing([reference("kind/bell")]),
                                        present=relation(*[reference(p) for p in keyed(people)]),
                                        things=relation(*[reference(t) for t in keyed(things)])))
        self.turn("yard", "shape", record(object=label("yard")))
        for i in range(10):
            made = self.turn("yard", "make", record(kind=choice("bell"), colour=choice("amber"), seed=label("s%d" % i)), principal=KIM)
            self.assertEqual(made["status"], "admitted", made)
        self.turn("yard", "enter", record(), principal=KIM)
        self.turn("yard", "enter", record(), principal=KIM)
        reply = self.turn("yard", "receive", record(text=label(""), post=label("")), principal=people[0])
        card = reply["offers"][0]["text"].split("\nReply with a spell:")[0]
        self.assertLess(len(card), 1400, card)
        self.assertIn("… and ", card)
        print("\n  fullest place: describe turn %s ticks, card %d bytes" % (reply["ticksUsed"], len(card)))
        self.assertLess(reply["ticksUsed"], 1000000)

    def test_a_kinds_law_is_the_package_s_own(self):
        from tests.test_objects import run_pure
        self.assertEqual(run_pure("Kind", "lawText")["value"]["value"], genesis.KIND_LAW)
        self.assertEqual(run_pure("Place", "lawText")["value"]["value"], genesis.PLACE_LAW)


if __name__ == "__main__":
    unittest.main()
