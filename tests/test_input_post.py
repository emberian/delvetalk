"""`inputOrigin.post`: the post a turn came from. A `receive {text, post}` frame's post is the reply's own
`post`, and the host keeps it when it reads the reply as a spell, so the spell's method (which no longer
sees `{text, post}`) sees it in its Context. A called frame inherits its caller's post unless it is itself a
`receive {text, post}`; a delivered `receive` brings its own. A suspended activity journals it, so a call
after the resumption and a stale re-run see it too.

Evidence for HOST-HANDOFF 5.71 (layer: host). Refuted by a spell's method, a called method or a delivered
spell whose Context names another post, or none.

    python3 -W error -m unittest tests.test_input_post -v
"""
import json
import unittest

from tests.test_reflection import Reflection
from tests.test_turn_world import label, nat, record, declared

GARDEN = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  planted: String
  noted: String
  heard: String
record Binding:
  name: String
  value: String
def initial() -> State:
  {planted: "", noted: "", heard: ""}
def plant(state: State, input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {planted: Plans.Edit.set({value: textConcat(input.seed, textConcat("@", context.inputOrigin.post))})}))
  1n
def note(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {noted: Plans.Edit.set({value: context.inputOrigin.post})}))
  2n
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(extend(keep(), {heard: Plans.Edit.set({value: context.inputOrigin.post})}))
  3n
"""

# The relay's own receive (prose: the bare fields) calls the garden's `note` (the post is inherited),
# calls the garden's receive with a spell from another post, and sends one from a third.
RELAY = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  n: Nat
record Binding:
  name: String
  value: String
def initial() -> State:
  {n: 0n}
def garden() -> Plans.Reference:
  {world: "", object: "garden"}
def receive(state: State, input: {text: String, post: String, fields: Lists.List<Binding>}, context: Abi.Context) -> Activity<Nat>:
  match world.call::<Data>({object: garden(), method: "note", argument: {}}):
    case returned(_):
      match world.call::<Data>({object: garden(), method: "receive", argument: {text: "delvetalk garden plant\\nseed: called", post: "at://called"}}):
        case returned(_):
          match world.send({object: garden(), method: "receive", argument: {text: "delvetalk garden plant\\nseed: sent", post: "at://sent"}}):
            case delivery(_): 1n
            case _: 90n
        case _: 91n
    case _: 92n
"""

# A garden whose `plant` awaits a slot and then calls its own `note`: the call runs after the
# resumption, from the journaled post.
WAITING = GARDEN.replace("""def plant(state: State, input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write(""", """def plant(state: State, input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  match world.await({slot: {principal: "glm", intent: "later"}, patience: 4n}):
    case _: sown(input, context)
def sown(input: {seed: String}, context: Abi.Context) -> Activity<Nat>:
  let returned(_) = world.call::<Data>({object: {world: "", object: context.object}, method: "note", argument: {}})
  let written(_) = world.write(""")


class InputPost(Reflection):
    def setUp(self):
        super().setUp()
        self.open_library()

    def create(self, name, source):
        r = self.host.send(op="world-create", principal="ember", identity="mk-" + name, object=name,
                           modules=[{"name": name.capitalize(), "source": declared(source)}], entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)

    def entries(self):
        return [json.loads(line) for line in self.lines()]

    def field(self, name, card="garden"):
        return {f["name"]: f["value"] for f in self.state(card)["fields"]}[name]

    def say(self, card, text, post, identity):
        return self.turn(card, "receive", record(text=label(text), post=label(post)), principal="glm", identity=identity)

    def test_a_spells_method_sees_the_replys_post(self):
        self.create("garden", GARDEN)
        r = self.say("garden", "delvetalk garden plant\nseed: fern", "at://glm/1", "plant-1")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.field("planted"), label("fern@at://glm/1"))
        # Prose reaches receive, whose Context names the same post; a direct `plant` names none.
        self.assertEqual(self.say("garden", "lovely", "at://glm/2", "prose")["result"], nat(3))
        self.assertEqual(self.field("heard"), label("at://glm/2"))
        self.assertEqual(self.turn("garden", "plant", record(seed=label("moss")), principal="glm")["status"], "admitted")
        self.assertEqual(self.field("planted"), label("moss@"))

    def test_called_and_delivered_turns_see_their_post(self):
        self.create("garden", GARDEN)
        self.create("relay", RELAY)
        r = self.say("relay", "pass it on", "at://glm/relay", "relay-1")
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.field("noted"), label("at://glm/relay"))   # a call inherits the caller's post
        # The called spell wrote first and the delivered one after: each names its own post.
        self.assertEqual(self.field("planted"), label("sent@at://sent"))
        planted = [str(w["edits"]) for e in self.entries() for w in e.get("outcome", {}).get("writes", [])
                   if w["object"] == "garden" and "planted" in str(w["edits"]) and "@" in str(w["edits"])]
        self.assertEqual(len(planted), 2, planted)
        self.assertIn("called@at://called", planted[0])

    def test_a_resumed_activitys_call_sees_the_journaled_post(self):
        self.create("garden", WAITING)
        r = self.say("garden", "delvetalk garden plant\nseed: fern", "at://glm/wait", "plant-w")
        self.assertEqual(r["status"], "suspended", r)
        suspended = [e for e in self.entries() if e.get("outcome", {}).get("tag") == "suspended"][-1]
        self.assertEqual(suspended["outcome"]["activity"].get("post"), "at://glm/wait")
        self.assertEqual(suspended["outcome"]["activity"].get("origin"), "spell")
        self.reopen()
        self.assertEqual(self.turn("garden", "note", record(), principal="glm", identity="later")["status"], "admitted")
        self.assertEqual(self.field("planted"), label("fern@at://glm/wait"))
        self.assertEqual(self.field("noted"), label("at://glm/wait"))


if __name__ == "__main__":
    unittest.main()
