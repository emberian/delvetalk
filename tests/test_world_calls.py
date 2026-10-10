"""A world call is a typed perform of the world object: each call site resumes at its own result
type, checked against the world's protocol.

Evidence for FOUNDATION §10 (layer: kernel).

World calls (WHOLENESS §1): `Activity<R>` yields `World.Message`s, `world.METHOD::<T>(arg)`
is the perform of `{object: {world: "", object: "world"}, method, argument: Data}` typed by
the world's protocol at T, and each call site resumes at its own result type.

    python3 -m unittest tests.test_world_calls -v
"""
import unittest

from tests.test_sugar import core
from tests.test_turn import Host, library_modules

# A stand-in for world/lib/World.obend (the objects lane's file): the shapes WHOLENESS fixes.
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
record Edits:
  count: Plans.Edit<Nat, Nat>
def keep() -> Edits:
  {count: Plans.Edit.keep({})}
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
    return library_modules("Abi", "Plan") + [{"name": "World", "source": world}, {"name": "Thing", "source": thing}]


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

    def test_every_dialect_entry_checks(self):
        for entry in ("bump", "peek", "both", "tell"):
            with self.subTest(entry=entry):
                reply = self.check(entry)
                self.assertEqual(reply["status"], "checked", reply)

    def start(self, entry, other="b"):
        ref = {"tag": "record", "fields": [{"name": "world", "value": {"tag": "label", "value": ""}},
                                           {"name": "object", "value": {"tag": "label", "value": other}}]}
        state = {"tag": "record", "fields": [{"name": "count", "value": {"tag": "natural", "value": "2"}}]}
        art = self.compile(entry)
        return art, ref, self.h.start(art, [state, {"tag": "record", "fields": [{"name": "other", "value": ref}]}])

    def test_a_world_call_yields_the_message(self):
        _, ref, y = self.start("peek")
        self.assertEqual(y["status"], "yielded", y)
        fields = {f["name"]: f["value"] for f in y["plan"]["fields"]}
        self.assertEqual(set(fields), {"object", "method", "argument"})
        self.assertEqual(fields["object"], {"tag": "record", "fields": [
            {"name": "world", "value": {"tag": "label", "value": ""}},
            {"name": "object", "value": {"tag": "label", "value": "world"}}]})
        self.assertEqual(fields["method"], {"tag": "label", "value": "view"})
        self.assertEqual(fields["argument"], {"tag": "record", "fields": [{"name": "object", "value": ref}]})

    def packet(self, entry, thing):
        art = self.compile(entry, thing)
        return core(art), art["type"]

    def test_write_sugar_is_the_world_write_it_spells(self):
        spelled = THING.replace("let written(_) = write {count: add 1n}",
                                "let written(_) = world.write(extend(keep(), {count: Plans.Edit.add({delta: 1n})}))")
        explicit = spelled.replace("world.write(", "world.write::<Edits>(")
        self.assertEqual(self.packet("bump", THING), self.packet("bump", spelled))
        self.assertEqual(self.packet("bump", THING), self.packet("bump", explicit))

    def test_a_data_field_of_the_input_injects(self):
        # send's argument is Data: the record literal {loud: true} is injected, as at a Data parameter.
        self.assertEqual(self.check("tell")["status"], "checked")
        art = self.compile("tell")
        self.assertIn("toData", str(art["packet"]))

    def test_refusals_name_the_world_call(self):
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

    def test_an_argument_of_the_wrong_shape_is_located_with_expected_and_found(self):
        d = self.refused("peek", THING.replace("world.view::<State>({object: input.other})",
                                               "world.view::<State>({thing: input.other})"))
        self.assertEqual(d["definition"], "Thing.peek")
        self.assertEqual(d["expected"], "{object: {world: String, object: String}}")
        self.assertEqual(d["found"], "{thing: {world: String, object: String}}")
        self.assertEqual(THING.count("\n", 0, d["span"]["start"]) + 1, d["span"]["line"])

    def test_without_a_world_module_the_dialect_is_refused_by_name(self):
        reply = self.h.send({"op": "check-package", "entry": "peek", "modules": library_modules("Abi", "Plan") +
                             [{"name": "Thing", "source": THING.replace("import ./World.obend as World\n", "")}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("no module named World", reply["diagnostic"]["message"])

    def test_a_protocol_signature_takes_one_input(self):
        bad = WORLD.replace("send({object", "send(Nat, {object")
        reply = self.check("bump", THING, bad)
        self.assertNotIn(reply["status"], ("checked",), reply)
        self.assertIn("exactly one input", str(reply))


def rec(**fields):
    return {"tag": "record", "fields": [{"name": n, "value": v} for n, v in fields.items()]}


def nat(n):
    return {"tag": "natural", "value": str(n)}


def variant(label, payload):
    return {"tag": "variant", "label": label, "payload": payload}


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


class SiteTypes(unittest.TestCase):
    """Each world call resumes at its own result type (WHOLENESS §1, day 2)."""

    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def compile(self, entry, thing=THING):
        reply = self.h.send({"op": "compile", "entry": entry, "modules": world_modules(thing)})
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def start(self, entry, count=2):
        art = self.compile(entry)
        ref = rec(world={"tag": "label", "value": ""}, object={"tag": "label", "value": "b"})
        return art, self.h.start(art, [rec(count=nat(count)), rec(other=ref)])

    def test_a_view_yields_at_viewed_of_its_type_and_resumes_with_it(self):
        art, y = self.start("peek")
        self.assertEqual(y["status"], "yielded", y)
        self.assertEqual(y["responseType"]["tag"], "variant")
        self.assertEqual(labels(y["responseType"]), ["viewed", "denied", "refused"])
        self.assertEqual(y["checkpoint"]["tokens"][0], "delvetalk.checkpoint.site.v1")
        done = self.h.resume(art, y["checkpoint"], variant("viewed", rec(version=nat(3), state=rec(count=nat(7)))))
        self.assertEqual((done["status"], done.get("value")), ("finished", nat(7)), done)

    def test_a_response_of_another_type_is_refused(self):
        art, y = self.start("peek")
        bad = self.h.resume(art, y["checkpoint"], variant("viewed", rec(version=nat(3), state=rec(other=nat(7)))))
        self.assertEqual(bad["status"], "error", bad)
        self.assertIn("response does not conform", bad["message"])
        written = self.h.resume(art, y["checkpoint"], variant("written", rec()))
        self.assertIn("response does not conform", written["message"])

    def test_two_sites_resume_at_two_types(self):
        art, y = self.start("both")
        self.assertEqual(labels(y["responseType"]), ["viewed", "denied", "refused"])
        w = self.h.resume(art, y["checkpoint"], variant("viewed", rec(version=nat(1), state=rec(count=nat(5)))))
        self.assertEqual(w["status"], "yielded", w)
        self.assertEqual(labels(w["responseType"]), ["written", "refused"])
        fields = {f["name"]: f["value"] for f in w["plan"]["fields"]}
        self.assertEqual(fields["method"], {"tag": "label", "value": "write"})
        # A view's response at the write's site is refused.
        again = self.h.resume(art, w["checkpoint"], variant("viewed", rec(version=nat(1), state=rec(count=nat(5)))))
        self.assertIn("response does not conform", again["message"])
        done = self.h.resume(art, w["checkpoint"], variant("written", rec()))
        self.assertEqual((done["status"], done.get("value")), ("finished", nat(5)), done)

    def test_the_artifact_names_its_dialect_and_world_methods(self):
        art = self.compile("both")
        self.assertEqual(art["dialect"], "message")
        self.assertEqual(art["world"], ["view", "write"])
        self.assertEqual(len(art["worldProtocol"]), 64)
        rows = {m["name"]: m for m in art["methods"]}
        self.assertTrue(rows["both"]["activity"])
        self.assertNotIn("dialect", self.compile("keep"))

    def test_two_calls_that_build_one_message_at_two_types_are_refused(self):
        reply = self.h.send({"op": "check-package", "entry": "twice", "modules": world_modules(TWICE)})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (world-call-site)", reply["diagnostic"]["message"])

if __name__ == "__main__":
    unittest.main()
