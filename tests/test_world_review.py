"""Room transitions, authentic activity notices and indentation of grown method bodies.

Refuted by an END or direct entry disagreeing with the avatar, a sender evicting
real notices about another thing, or a nested body that cannot run as a method.
"""
import unittest

from tests.bend import closure, declared
from tests.host import bounds
from tests.test_chain import Chain
from tests.test_objects import run_pure
from tests.test_rooms import avatar_seed, make_room, room_seed, thing_seed
from tests.test_scene import choice, passage, plain, scene_fields
from tests.wire import field, label, nat, record, reference, relation


RELAY = declared('''edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  owner: String
def initial() -> State:
  {owner: ""}
def notify(state: State, input: {avatar: String, thing: String, verb: String}, context: Abi.Context) -> Activity<World.Sent>:
  world.send({object: {world: context.world, object: input.avatar}, method: "heard", argument: {thing: input.thing, verb: input.verb}})
def cite(state: State, input: {thing: String}, context: Abi.Context) -> Activity<World.Sent>:
  world.send({object: {world: context.world, object: input.thing}, method: "cited", argument: Plans.nothing()})
def locate(state: State, input: {avatar: String}, context: Abi.Context) -> Activity<World.Returned<Bool>>:
  world.call::<Bool>({object: {world: context.world, object: input.avatar}, method: "locate", argument: Plans.nothing()})
''')


def relay_modules():
    return closure("World", "Abi") + [{"name": "Relay", "source": RELAY}]


class Location(Chain):
    def setUp(self):
        super().setUp()
        self.make("glm", closure("Avatar"), avatar_seed("glm"))
        make_room(self, "scene", **scene_fields([
            passage("gate", "A gate.", [choice("Out", "END")])]))
        make_room(self, "garden", **room_seed("Garden", [("back", "scene")]))

    def admitted(self, obj, method, argument=None):
        reply = self.turn(obj, method, argument, principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        return reply

    def at(self):
        return field(self.state("glm"), "at")

    def present(self, obj):
        return [r["who"] for r in plain(field(self.state(obj), "presence"))]

    def test_go_end_leave_and_go_again_share_room_presence(self):
        self.admitted("glm", "go", record(to=label("scene")))
        self.assertEqual(self.at(), reference("scene"))
        self.assertEqual(self.present("scene"), ["glm"])
        self.admitted("scene", "choose", record(choice=label("Out")))
        self.assertEqual((self.present("scene"), self.at()), ([], reference("")))
        self.admitted("glm", "go", record(to=label("garden")))
        self.assertEqual((self.present("garden"), self.at()), (["glm"], reference("garden")))
        self.admitted("garden", "leave")
        self.assertEqual((self.present("garden"), self.at()), ([], reference("")))
        self.admitted("glm", "go", record(to=label("scene")))
        self.assertEqual((self.present("scene"), self.at()), (["glm"], reference("scene")))

    def test_direct_enter_updates_look_and_departure_from_the_previous_room(self):
        self.admitted("scene", "enter")
        self.assertEqual(self.at(), reference("scene"))
        looked = self.admitted("glm", "receive", record(text=label("look"), post=label("")))
        self.assertIn("A gate.", "".join(o["text"] for o in looked["offers"]))
        self.admitted("garden", "enter")
        self.assertEqual((self.present("scene"), self.present("garden"), self.at()),
                         ([], ["glm"], reference("garden")))
        self.admitted("glm", "move", record(exit=label("back")))
        self.assertEqual((self.present("scene"), self.present("garden"), self.at()),
                         (["glm"], [], reference("scene")))

    def test_a_full_destination_refuses_without_departing_or_changing_the_index(self):
        make_room(self, "full", **room_seed("Full", present=["reader-%02d" % n for n in range(32)]))
        self.admitted("glm", "go", record(to=label("scene")))
        before = {obj: self.state(obj) for obj in ("scene", "full", "glm")}
        refused = self.turn("glm", "go", record(to=label("full")), principal="glm")
        self.assertEqual(refused["status"], "refused", refused)
        self.assertEqual(refused["receipt"]["outcome"]["clause"], "roomFull", refused)
        self.assertEqual({obj: self.state(obj) for obj in before}, before)

    def test_a_refused_departure_rolls_back_direct_entry_and_the_index(self):
        self.admitted("scene", "enter")
        version = self.host.send(op="world-view", principal="ember", object="scene")["version"]
        amended = self.host.send(op="world-amend", principal="ember", object="scene", identity="stay",
                                 version=version,
                                 law='law stay "stay here": request.method != "leave"')
        self.assertEqual(amended["status"], "admitted", amended)
        before = {obj: self.state(obj) for obj in ("scene", "garden", "glm")}
        refused = self.turn("garden", "enter", principal="glm")
        self.assertEqual(refused["status"], "refused", refused)
        self.assertEqual({obj: self.state(obj) for obj in before}, before)

    def test_a_direct_or_non_room_location_claim_cannot_move_the_avatar(self):
        direct = self.turn("glm", "locate", principal="glm")
        self.assertEqual(direct["status"], "refused", direct)
        self.make("relay", relay_modules(), record(owner=label("glm")))
        relayed = self.admitted("relay", "locate", record(avatar=label("glm")))
        self.assertEqual(relayed["result"]["label"], "refused", relayed)
        self.assertEqual(self.at(), reference(""))

    def test_go_uses_presence_when_the_previous_index_names_an_empty_room(self):
        self.make("kim", closure("Avatar"), avatar_seed("kim", "scene"))
        went = self.turn("kim", "go", record(to=label("garden")), principal="kim")
        self.assertEqual(went["status"], "admitted", went)
        self.assertEqual(field(self.state("kim"), "at"), reference("garden"))
        self.assertEqual((self.present("scene"), self.present("garden")), ([], ["kim"]))


class Notifications(Chain):
    def make_avatar(self, heard=()):
        self.make("alice", closure("Avatar"), record(handle=label("Alice"), heard=relation(*heard)))

    def notices(self):
        return plain(field(self.state("alice"), "heard"))

    def test_another_object_cannot_fabricate_a_notice_or_evict_any_of_64_real_rows(self):
        rows = [record(thing=label("bell"), verb=label("rain"), by=label("bob"), handle=label("Bob"),
                       at=nat(n + 1), n=nat(n)) for n in range(64)]
        self.make_avatar(rows)
        self.make("bell", closure("Record"), record(owner=label("alice"), maker=label("alice")))
        self.make("relay", relay_modules(), record(owner=label("bob")))
        before = field(self.state("alice"), "heard")
        sent = self.turn("relay", "notify", record(avatar=label("alice"), thing=label("bell"), verb=label("rain")), principal="bob")
        self.assertEqual(sent["status"], "admitted", sent)
        self.deliver_all()
        self.assertEqual(field(self.state("alice"), "heard"), before)
        refused = [d for d in sent.get("delivered", []) if d["status"] == "refused"]
        self.assertTrue(refused, sent)
        self.assertEqual(refused[0]["receipt"]["outcome"]["clause"], "heard", refused)

    def test_records_things_and_committed_doors_still_notify_from_the_thing(self):
        self.make_avatar()
        self.make("bell", closure("Record"), record(owner=label("alice"), maker=label("alice")))
        self.make("stone", closure("Thing"), thing_seed("stone", owner="alice"))
        self.make("shelf", closure("Record"), record(owner=label("bob")))
        for obj, method, argument in (
            ("bell", "write", record(text=label("a line"))),
            ("stone", "inspirit", record(surrounding=label("moss"))),
            ("shelf", "door", record(label=label("bell"), to=label("bell"))),
            ("shelf", "door", record(label=label("stone"), to=label("stone"))),
        ):
            reply = self.turn(obj, method, argument, principal="bob")
            self.assertEqual(reply["status"], "admitted", reply)
            self.deliver_all()
        self.assertEqual([(h["thing"], h["verb"], h["by"]) for h in self.notices()],
                         [("bell", "write", "bob"), ("stone", "inspirit", "bob"),
                          ("bell", "door", "bob"), ("stone", "door", "bob")])

    def test_a_sender_without_a_committed_door_cannot_use_the_citation_notice(self):
        self.make_avatar()
        self.make("bell", closure("Record"), record(owner=label("alice"), maker=label("alice")))
        self.make("relay", relay_modules(), record(owner=label("bob")))
        self.turn("relay", "cite", record(thing=label("bell")), principal="bob")
        self.deliver_all()
        self.assertEqual(self.notices(), [])

    def test_grown_gestures_on_records_and_things_notify_from_their_own_identity(self):
        self.make_avatar()
        self.make("bell", closure("Record"), record(owner=label("alice"), maker=label("alice")))
        self.make("stone", closure("Thing"), thing_seed("stone", owner="alice"))
        for obj in ("bell", "stone"):
            grown = self.turn(obj, "receive", record(text=label(
                "delvetalk %s grow / name: water / reading: a cupful" % obj), post=label("")), principal="bob")
            self.assertEqual(grown["status"], "admitted", grown)
            used = self.turn(obj, "act", record(verb=label("water"), text=label("a cup")), principal="bob")
            self.assertEqual(used["status"], "admitted", used)
            self.deliver_all()
        self.assertEqual([(h["thing"], h["verb"], h["by"]) for h in self.notices()],
                         [("bell", "water", "bob"), ("stone", "water", "bob")])


class VerbBodies(Chain):
    def setUp(self):
        super().setUp()
        self.make("workshop", closure("Workshop"), record(title=label("Workshop")))
        self.make("pot", closure("Record"), record(owner=label("glm"), maker=label("glm")))

    def grow(self, name, body):
        reply = self.turn("pot", "receive", record(text=label(
            "delvetalk pot grow / name: %s / takes: nothing\nbody: <<BEND\n%s\nBEND" % (name, body)), post=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(reply["result"]["label"], "reprogrammed", reply)

    def test_match_cases_and_nested_records_compile_and_execute_with_common_indentation(self):
        self.grow("water", '''    match state.next == 1n:
      case true:
        let words = {
          first: "first",
          second: "cup"
        }

        Super.inscribe(state, "water", "{words.first} {words.second}", context)
      case false:
        match state.next == 2n:
          case true: Super.inscribe(state, "water", "second cup", context)
          case false: Super.inscribe(state, "water", "later cup", context)''')
        for expected in ("first cup", "second cup", "later cup"):
            reply = self.turn("pot", "water", principal="glm")
            self.assertEqual(reply["status"], "admitted", reply)
            self.assertIn(expected, "".join(o["text"] for o in reply["offers"]))

    def test_indentation_does_not_make_an_invalid_case_body_compile(self):
        reply = self.turn("pot", "receive", record(text=label(
            'delvetalk pot grow / name: spill / takes: nothing\nbody: <<BEND\n'
            'match state.next == 1n:\ncase true: 1n\ncase false: 2n\nBEND'), post=label("")), principal="glm")
        self.assertEqual(reply["status"], "admitted", reply)
        self.assertEqual(reply["result"]["label"], "flawed", reply)


class VerbLayer(unittest.TestCase):
    def layer(self, body):
        reply = run_pure("Workshop", "verbLayer", label("water"), label("nothing"), label(body),
                         limits={"ticks": "20000000", "bytes": "16777216", "heap": "262144"})
        self.assertEqual(reply["status"], "done", reply)
        return reply["value"]["value"]

    def test_a_maximum_length_body_preserves_its_nested_case_indentation(self):
        tail = '    match state.next == 0n:\n      case true: 0n\n      case false: 1n'
        size = bounds()["kernel"]["maxPackageBytes"]
        comment = "x" * (size - len(tail) - len("    #\n"))
        body = "    #" + comment + "\n" + tail
        self.assertEqual(len(body.encode()), size)
        layer = self.layer(body)
        self.assertTrue(layer.endswith('  match state.next == 0n:\n    case true: 0n\n    case false: 1n\n'))
        self.assertIn("  #" + comment + "\n", layer)

    def test_only_the_common_whitespace_prefix_is_removed(self):
        layer = self.layer("  \tmatch state.next == 0n:\n  \t  case true: 0n\n    case false: 1n")
        self.assertTrue(layer.endswith("  \tmatch state.next == 0n:\n  \t  case true: 0n\n    case false: 1n\n"), layer)


if __name__ == "__main__":
    unittest.main()
