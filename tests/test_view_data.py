"""A card reads another object's state, or one field, as Data, the root recorded and a private object
denied.

Evidence for FOUNDATION §3 (layer: host).

view::<Data> / viewField::<Data>: a card reads another object's state, or one field of it, as `Data` it may pass
along but not take apart (a Bell's `view` of the directory could not carry the directory's state type).
Read authority and the root are `view`'s. Refuted by a value other than the field's, a field read without
recording the root, or a private object answered.

    python3 -W error -m unittest tests.test_view_data -v
"""
import unittest

from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record, declared

READER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  note: String
def initial() -> State:
  {note: ""}
def field(state: State, input: {target: String, field: String}, context: Abi.Context) -> Activity<Data>:
  match world.viewField::<Data>({object: {world: "", object: input.target}, field: input.field}):
    case viewed(v): v.state
    case refused(r): Data.of::<String>(r.clause)
    case _: Data.of::<String>("other")
def whole(state: State, input: {target: String}, context: Abi.Context) -> Activity<Data>:
  match world.view::<Data>({object: {world: "", object: input.target}}):
    case viewed(v): v.state
    case denied(_): Data.of::<String>("denied")
    case _: Data.of::<String>("other")
""")
TARGET = declared("""edition ObjectiveBend 1
import ./List.obend as Lists
record State:
  owner: String
  words: String
  greeted: Lists.List<String>
def initial() -> State:
  {owner: "", words: "GARDEN · ROOMS", greeted: Lists.List::<String>.cons({head: "glm", tail: Lists.List::<String>.nil({})})}
""")


class ViewData(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()
        self.make("reader", READER, record(note=label("")))

    def target(self, name, **extra):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name, source=TARGET,
                           entry="initial", seed=record(), **extra)
        self.assertEqual(r["status"], "created", r)

    def test_a_card_reads_one_field_of_another_object_as_data_and_the_root_is_recorded(self):
        self.target("directory")
        r = self.turn("reader", "field", record(target=label("directory"), field=label("words")))
        self.assertEqual((r["status"], r["result"]), ("admitted", label("GARDEN · ROOMS")), r)
        self.assertIn({"object": "directory", "version": 0, "field": "words", "key": "*"}, r["receipt"]["roots"])
        listed = self.turn("reader", "field", record(target=label("directory"), field=label("greeted")))
        self.assertEqual(listed["result"], {"tag": "list", "items": [label("glm")]}, listed)
        missing = self.turn("reader", "field", record(target=label("directory"), field=label("nope")))
        self.assertEqual(missing["result"], label("field"))

    def test_the_whole_state_as_data_and_a_private_object_is_denied(self):
        self.target("directory")
        whole = self.turn("reader", "whole", record(target=label("directory")))
        self.assertEqual([f["name"] for f in whole["result"]["fields"]], ["owner", "words", "greeted"], whole)
        self.target("vault", read={"principals": ["ember"]})
        denied = self.turn("reader", "whole", record(target=label("vault")), principal="ann")
        self.assertEqual(denied["result"], label("denied"), denied)


if __name__ == "__main__":
    unittest.main()
