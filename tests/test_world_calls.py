"""A world call is a typed perform of the world object: each call site resumes at its own result
type, checked against the world's protocol.

Evidence for FOUNDATION §10 (layer: kernel).

World calls (FOUNDATION §3): `Activity<R>` yields `World.Message`s, `world.METHOD::<T>(arg)`
is the perform of `{object: {world: "", object: "world"}, method, argument: Data}` typed by
the world's protocol at T, and each call site resumes at its own result type.

    python3 -m unittest tests.test_world_calls -v
"""
import unittest

from tests.bend import closure
from tests.test_turn import Host
from tests.wire import nat, record, variant

# A stand-in for world/lib/World.obend (the objects lane's file): the shapes FOUNDATION §3 fixes.
WORLD = """edition ObjectiveBend 1
import ./Plan.obend as Plans
record Message:
  object: Plans.Reference
  method: String
  argument: Data
sum Viewed<S>:
  viewed: {version: Nat, state: S}
  denied: {}
  refused: {clause: String}
sum Written:
  written: {}
  refused: {clause: String}
sum Returned<R>:
  returned: {result: R}
  refused: {clause: String}
sum Sent:
  delivery: {id: String}
  refused: {clause: String}
protocol world:
  view<S>({object: Plans.Reference}) -> Viewed<S>
  write<E>(E) -> Written
  call<R>({object: Plans.Reference, method: String, argument: Data}) -> Returned<R>
  send({object: Plans.Reference, method: String, argument: Data}) -> Sent
"""

THING = """edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
def bump(state: State, input: {}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {count: add 1n}
  state.count + 1n
def peek(state: State, input: {other: Plans.Reference}, context: Abi.Context) -> Activity<Nat>:
  match world.view::<State>({object: input.other}):
    case viewed(v): v.state.count
    case _: 0n
def both(state: State, input: {other: Plans.Reference}, context: Abi.Context) -> Activity<Nat>:
  let viewed(v) = world.view::<State>({object: input.other})
  let written(_) = world.write(extend(keep(), {count: Plans.Edit.set({value: v.state.count})}))
  v.state.count
def tell(state: State, input: {other: Plans.Reference}, context: Abi.Context) -> Activity<String>:
  match world.send({object: input.other, method: "ring", argument: {loud: true}}):
    case delivery(d): d.id
    case refused(r): r.clause
"""


def world_modules(thing=THING, world=WORLD):
    return closure("Abi", "Plan") + [{"name": "World", "source": world}, {"name": "Thing", "source": thing}]


def labels(t):
    """The labels of a variant type's row (typeJson)."""
    out, row = [], t.get("row")
    while row and row.get("tag") == "field":
        out.append(row["name"])
        row = row["tail"]
    return out


TWICE = THING + """def twice(state: State, input: {other: Plans.Reference}, context: Abi.Context) -> Activity<Nat>:
  match state.count == 0n:
    case true:
      match world.view::<State>({object: input.other}):
        case viewed(v): 1n
        case _: 0n
    case false:
      match world.view::<Data>({object: input.other}):
        case viewed(v): 2n
        case _: 0n
"""


class WorldCalls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def check(self, entry, thing=THING, world=WORLD):
        return self.h.send({"op": "check-package", "entry": entry, "modules": world_modules(thing, world)})

    def compile(self, entry, thing=THING):
        reply = self.h.send({"op": "compile", "entry": entry, "modules": world_modules(thing)})
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def refused(self, entry, thing, world=WORLD):
        reply = self.check(entry, thing, world)
        self.assertEqual(reply["status"], "refused", reply)
        return reply["diagnostic"]


    def test_refusals_name_the_world_call_the_missing_world_and_the_one_input(self):
        cases = {
            "refused (perform): surface perform is withdrawn": ("bump", THING.replace(
                "let written(_) = write {count: add 1n}",
                'let written(_) = perform({object: {world: "", object: "world"}, method: "x", argument: Data.of::<Nat>(1n)})')),
            "the world has no method mail": ("tell", THING.replace("world.send(", "world.mail(")),
            "cannot infer the type argument S of world.view": ("peek", THING.replace(
                "world.view::<State>({object: input.other}):", "world.view({object: input.other}):")),
            "takes 1 type argument, not 2": ("peek", THING.replace(
                "world.view::<State>({object: input.other}):", "world.view::<State, Nat>({object: input.other}):")),
            "refused (old-dialect): Activity<Plan, Response, Result> is withdrawn": ("peek", THING.replace(
                "-> Activity<Nat>:\n  match world.view", "-> Activity<World.Message, Data, Nat>:\n  match world.view")),
        }
        for needle, (entry, source) in cases.items():
            with self.subTest(needle=needle):
                d = self.refused(entry, source)
                self.assertIn(needle, d["message"])
        reply = self.h.send({"op": "check-package", "entry": "peek", "modules": closure("Abi", "Plan") +
                             [{"name": "Thing", "source": THING.replace("import ./World.obend as World\n", "")}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("no module named World", reply["diagnostic"]["message"])
        bad = WORLD.replace("send({object", "send(Nat, {object")
        reply = self.check("bump", THING, bad)
        self.assertNotIn(reply["status"], ("checked",), reply)
        self.assertIn("exactly one input", str(reply))

    def test_an_argument_of_the_wrong_shape_is_located_with_expected_and_found(self):
        d = self.refused("peek", THING.replace("world.view::<State>({object: input.other})",
                                               "world.view::<State>({thing: input.other})"))
        self.assertEqual(d["definition"], "Thing.peek")
        self.assertEqual(d["expected"], "{object: {world: String, object: String}}")
        self.assertEqual(d["found"], "{thing: {world: String, object: String}}")
        self.assertEqual(THING.count("\n", 0, d["span"]["start"]) + 1, d["span"]["line"])


    def start(self, entry, count=2):
        art = self.compile(entry)
        ref = record(world={"tag": "label", "value": ""}, object={"tag": "label", "value": "b"})
        return art, self.h.start(art, [record(count=nat(count)), record(other=ref)])

    def test_a_view_yields_at_viewed_of_its_type_resumes_with_it_and_refuses_another(self):
        art, y = self.start("peek")
        self.assertEqual(y["status"], "yielded", y)
        self.assertEqual(y["responseType"]["tag"], "variant")
        self.assertEqual(labels(y["responseType"]), ["viewed", "denied", "refused"])
        self.assertEqual(y["checkpoint"]["tokens"][0], "delvetalk.checkpoint.site.v1")
        done = self.h.resume(art, y["checkpoint"], variant("viewed", record(version=nat(3), state=record(count=nat(7)))))
        self.assertEqual((done["status"], done.get("value")), ("finished", nat(7)), done)
        art, y = self.start("peek")
        bad = self.h.resume(art, y["checkpoint"], variant("viewed", record(version=nat(3), state=record(other=nat(7)))))
        self.assertEqual(bad["status"], "error", bad)
        self.assertIn("response does not conform", bad["message"])
        written = self.h.resume(art, y["checkpoint"], variant("written", record()))
        self.assertIn("response does not conform", written["message"])

    def test_two_sites_resume_at_two_types_and_one_message_at_two_types_is_refused(self):
        art, y = self.start("both")
        self.assertEqual(labels(y["responseType"]), ["viewed", "denied", "refused"])
        w = self.h.resume(art, y["checkpoint"], variant("viewed", record(version=nat(1), state=record(count=nat(5)))))
        self.assertEqual(w["status"], "yielded", w)
        self.assertEqual(labels(w["responseType"]), ["written", "refused"])
        fields = {f["name"]: f["value"] for f in w["plan"]["fields"]}
        self.assertEqual(fields["method"], {"tag": "label", "value": "write"})
        # A view's response at the write's site is refused.
        again = self.h.resume(art, w["checkpoint"], variant("viewed", record(version=nat(1), state=record(count=nat(5)))))
        self.assertIn("response does not conform", again["message"])
        done = self.h.resume(art, w["checkpoint"], variant("written", record()))
        self.assertEqual((done["status"], done.get("value")), ("finished", nat(5)), done)
        reply = self.h.send({"op": "check-package", "entry": "twice", "modules": world_modules(TWICE)})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (world-call-site)", reply["diagnostic"]["message"])


if __name__ == "__main__":
    unittest.main()
