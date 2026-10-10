"""Data, the universal first-order type: one world call carries any payload shape, Data.of checks its
declared type, nothing takes Data apart, and a malformed value is refused on every admission path.

Evidence for FOUNDATION §3 (layer: kernel).

The universal first-order type `Data` (`Data.of::<T>(value)`, no elimination).

Each test names what would refute it.
"""
import json
import unittest

from tests.test_chain import Chain
from tests.test_turn import MESSAGE, Host, TurnCase, nat, label, library_modules, variant
from tests.test_turn_world import closure
from tests.test_turn_world import declared

CALLER_WORLD = "edition ObjectiveBend 1\n" + MESSAGE + """record Call:
  object: String
  method: String
  argument: Data
sum Reply:
  returned: {result: Data}
  refused: {}
protocol world:
  call(Call) -> Reply
"""

CALLER = """edition ObjectiveBend 1
import ./World.obend as World
record Pair:
  a: Nat
  b: String
sum Shade:
  dark: {}
  light: {level: Nat}
def fan(count: Nat) -> Activity<Data>:
  match world.call({object: "counter", method: "add", argument: Data.of::<Nat>(count)}):
    case returned(first):
      match world.call({object: "pairs", method: "put", argument: Data.of::<Pair>({a: count, b: "hi"})}):
        case returned(second): second.result
        case refused(_): first.result
    case refused(_): Data.of::<Shade>(Shade.dark({}))
def keep(value: Data, n: Nat) -> Activity<Data>:
  match world.call({object: "box", method: "put", argument: value}):
    case returned(r): r.result
    case refused(_): value
def pair(p: Pair) -> Activity<Nat>:
  match world.call({object: "pairs", method: "put", argument: Data.of::<Pair>(p)}):
    case returned(_): p.a
    case refused(_): 0n
"""


def called(plan):
    """The Call record a yielded Message carries as its argument."""
    return field(field(plan, "argument"), "argument")


def field(record, name):
    for f in record["fields"]:
        if f["name"] == name:
            return f["value"]
    raise KeyError(name)


def record(**fields):
    return {"tag": "record", "fields": [{"name": k, "value": v} for k, v in fields.items()]}


class DataTypeTests(TurnCase):

    def test_one_activity_calls_two_objects_with_different_argument_shapes(self):
        # Refuted if a single world call cannot carry a Nat and a record payload in one activity.
        h = self.host()
        art = h.compile(CALLER, "fan", world=CALLER_WORLD)
        first = h.start(art, [nat(5)])
        self.assertEqual(first["status"], "yielded", first)
        self.assertEqual(called(first["plan"]), nat(5))
        self.assertEqual(field(first["plan"], "method"), label("call"))
        second = h.resume(art, first["checkpoint"], variant("returned", record(result=nat(6))))
        self.assertEqual(second["status"], "yielded", second)
        self.assertEqual(called(second["plan"]), record(a=nat(5), b=label("hi")))

    def test_data_field_round_trips_through_a_checkpoint(self):
        # Refuted if a Data value (here a variant inside a record) changes across yield/resume.
        h = self.host()
        art = h.compile(CALLER, "keep", world=CALLER_WORLD)
        value = record(shade=variant("light", record(level=nat(3))), tags=label("x"))
        started = h.start(art, [value, nat(0)])
        self.assertEqual(started["status"], "yielded", started)
        self.assertEqual(called(started["plan"]), value)
        echoed = variant("on", record(deep=variant("light", record(level=nat(4)))))
        done = h.resume(art, started["checkpoint"], variant("returned", record(result=echoed)))
        self.assertEqual(done["status"], "finished", done)
        self.assertEqual(done["value"], echoed)
        self.assertEqual(done["type"], {"tag": "data"})

    def test_data_argument_with_a_repeated_field_is_refused(self):
        # Refuted if Data admits a record that is not well-formed data.
        h = self.host()
        art = h.compile(CALLER, "keep", world=CALLER_WORLD)
        bad = {"tag": "record", "fields": [{"name": "a", "value": nat(1)}, {"name": "a", "value": nat(2)}]}
        reply = h.start(art, [bad, nat(0)])
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("does not conform", reply["message"])

    def test_argument_shape_not_conforming_to_the_declared_type_is_refused(self):
        # Refuted if a Data payload of the wrong shape reaches a callee typed Pair.
        h = self.host()
        art = h.compile(CALLER, "pair", world=CALLER_WORLD)
        reply = h.start(art, [record(a=nat(1))])
        self.assertEqual(reply["status"], "error", reply)
        self.assertEqual(reply["message"], "turn refused: argument does not conform to its type")
        ok = h.start(art, [record(a=nat(1), b=label("x"))])
        self.assertEqual(ok["status"], "yielded", ok)

    def test_data_of_checks_its_declared_type_and_has_no_elimination(self):
        # Refuted if Data.of accepts a value of another type, or Bend can take Data apart.
        h = self.host()
        wrong = h.send({"op": "compile", "entry": "f", "modules": [{"name": "Package", "source":
            "edition ObjectiveBend 1\ndef f(n: Nat) -> Data:\n  Data.of::<String>(n)\n"}]})
        self.assertEqual(wrong["status"], "error", wrong)
        self.assertIn("Data.of::<String>", wrong["message"])
        eliminate = h.send({"op": "compile", "entry": "g", "modules": [{"name": "Package", "source":
            "edition ObjectiveBend 1\ndef g(d: Data) -> Nat:\n  d + 1n\n"}]})
        self.assertEqual(eliminate["status"], "error", eliminate)
        good = h.send({"op": "compile", "entry": "f", "modules": [{"name": "Package", "source":
            "edition ObjectiveBend 1\ndef f(n: Nat) -> Data:\n  Data.of::<Nat>(n)\n"}]})
        self.assertEqual(good["status"], "compiled", good)

    def test_a_long_list_argument_starts_an_activity_at_data_and_at_its_declared_type(self):
        # Refuted if the activity path refuses a deep value the runtime admits: the checker's
        # walk fuel for `Data` (and its fuel for an argument literal) was fixed, so a list
        # of a couple of thousand items was refused at `Data` and of four thousand at
        # `List<String>`, while the pure path has no such bound. Also refuted if starting
        # costs more than linear-ish time (annotations were looked up by scanning a list).
        h = self.host()
        items = {"tag": "list", "items": [label("x%d" % i) for i in range(2500)]}
        art = h.compile(CALLER, "keep", world=CALLER_WORLD)
        started = h.start(art, [items, nat(0)])
        self.assertEqual(started["status"], "yielded", started.get("message"))
        self.assertEqual(called(started["plan"]), items)
        typed = h.send({"op": "compile", "entry": "count", "modules": library_modules("List") + [
            {"name": "World", "source": LONG_WORLD}, {"name": "Package", "source": LONG_TYPED}]})
        self.assertEqual(typed["status"], "compiled", typed)
        longer = {"tag": "list", "items": [label("y%d" % i) for i in range(4500)]}  # past the old four-thousand refusal
        reply = h.start(typed["artifact"], [longer, nat(3)])
        self.assertEqual(reply["status"], "yielded", reply.get("message"))
        self.assertEqual(field(reply["plan"], "method"), label("say"))
        self.assertEqual(field(reply["plan"], "argument"), record(n=nat(3)))


LONG_WORLD = "edition ObjectiveBend 1\n" + MESSAGE + """sum Reply:
  ok: {}
protocol world:
  say({n: Nat}) -> Reply
"""

LONG_TYPED = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./World.obend as World
def count(xs: Lists.List<String>, n: Nat) -> Activity<Nat>:
  match world.say({n: n}):
    case ok(_): n
"""


# A Counter whose state holds a universal `Data` payload (a Wake trigger's stored argument
# is the motivating case). `put*` write the payload in an activity; `copyAfter` awaits a
# slot and then copies the payload it read before suspending, so the Data value crosses a
# checkpoint; `touch` is a pure method, so the state crosses the native admission path.
DATA_COUNTER = declared("""edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
import ./List.obend as Lists
record State:
  count: Nat
  payload: Data
  copy: Data
record Edits:
  count: Plans.Edit<Nat, Nat>
  payload: Plans.Edit<Data, Data>
  copy: Plans.Edit<Data, Data>
record Tagged:
  name: String
  n: Nat
def initial() -> State:
  {count: 0n, payload: Data.of::<Nat>(0n), copy: Data.of::<Nat>(0n)}
def keepData() -> Plans.Edit<Data, Data>:
  Plans.Edit::<Data, Data>.keep({})
def setData(value: Data) -> Plans.Edit<Data, Data>:
  Plans.Edit::<Data, Data>.set({value: value})
def put(context: Abi.Context, value: Data) -> Activity<Nat>:
  match world.write({count: Plans.Edit::<Nat, Nat>.keep({}), payload: setData(value), copy: keepData()}):
    case written(_): 1n
    case _: 0n
def putRecord(state: State, input: Tagged, context: Abi.Context) -> Activity<Nat>:
  put(context, Data.of::<Tagged>(input))
def putList(state: State, input: {items: Lists.List<Nat>}, context: Abi.Context) -> Activity<Nat>:
  put(context, Data.of::<Lists.List<Nat>>(input.items))
def copyAfter(state: State, input: {principal: String, intent: String}, context: Abi.Context) -> Activity<Nat>:
  match world.await({slot: {principal: input.principal, intent: input.intent}, patience: 8n}):
    case reply(_):
      match world.write({count: Plans.Edit::<Nat, Nat>.add({delta: 1n}), payload: keepData(), copy: setData(state.payload)}):
        case written(_): 1n
        case _: 0n
    case _: 0n
def touch(state: State, context: Abi.Context) -> State:
  {count: state.count + 1n, payload: state.payload, copy: state.copy}
""")


def data_counter_modules():
    return closure("DataCounter", override={"DataCounter": DATA_COUNTER})


def items(*values):
    return {"tag": "list", "items": list(values)}


def set_payload(value):
    return record(payload=variant("set", record(value=value)))


REPEATED = {"tag": "record", "fields": [{"name": "a", "value": nat(1)}, {"name": "a", "value": nat(2)}]}


class DataInState(Chain):
    """A state record with `payload: Data`: created, written, viewed, checkpointed, replayed."""

    def raw(self, **request):
        """One reply exactly as the host printed it (no list rewriting by the helper)."""
        self.host.proc.stdin.write(json.dumps(request) + "\n")
        self.host.proc.stdin.flush()
        return json.loads(self.host.proc.stdout.readline())

    def payload(self, name="payload"):
        view = self.raw(op="world-view", principal="ember", object="box")
        self.assertEqual(view["status"], "viewed", view)
        return [f["value"] for f in view["state"]["fields"] if f["name"] == name][0]

    def cid(self, value):
        return self.raw(op="canonical-encode", data=value)["cid"]

    def create(self, payload=None):
        r = self.host.send(op="world-create", principal="ember", identity="mk-box", object="box",
                           modules=data_counter_modules(), entry="initial",
                           seed=record(count=nat(0), payload=payload or nat(0), copy=nat(0)))
        return r

    def test_created_written_with_a_record_and_a_list_and_viewed_back_identical(self):
        # Refuted if the State schema refuses a Data field, or a written value comes back changed.
        self.assertEqual(self.create(record(seeded=label("yes")))["status"], "created")
        self.assertEqual(self.payload(), record(seeded=label("yes")))
        tagged = record(name=label("moth"), n=nat(7))
        r = self.turn("box", "putRecord", tagged)
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.payload(), tagged)
        self.assertEqual(self.cid(self.payload()), self.cid(tagged))
        listed = items(nat(1), nat(2), nat(3))
        r = self.turn("box", "putList", record(items=listed))
        self.assertEqual((r["status"], r["result"]), ("admitted", nat(1)), r)
        self.assertEqual(self.payload(), listed)
        self.assertEqual(self.cid(self.payload()), self.cid(listed))
        # A pure method receives the state (with its Data field) and commits every field.
        r = self.turn("box", "touch")
        self.assertEqual(r["status"], "admitted", r)
        self.assertEqual(self.payload(), listed)
        self.assertEqual(self.payload("count"), nat(1))

    def test_a_data_payload_crosses_an_await_checkpoint_a_restart_and_a_replay(self):
        # Refuted if the Data value read before suspending is not the one written after resuming.
        self.assertEqual(self.create()["status"], "created")
        nested = record(shade=variant("light", record(level=nat(3))), tags=items(label("a"), label("b")))
        self.assertEqual(self.raw(op="world-propose", principal="ember", identity="w1",
                                  roots=[{"object": "box", "version": 0}],
                                  writes=[{"object": "box", "edits": set_payload(nested)}]
                                  )["status"], "admitted")
        s = self.turn("box", "copyAfter", record(principal=label("glm"), intent=label("post-1")), identity="wait")
        self.assertEqual(s["status"], "suspended", s)
        self.reopen()                                    # the checkpoint is rebuilt from the journal
        settled = self.host.send(op="world-propose", principal="glm", identity="post-1", roots=[], writes=[])
        self.assertEqual([x["status"] for x in settled["resumed"]], ["admitted"], settled)
        self.assertEqual(self.payload("copy"), nested)
        self.assertEqual(self.cid(self.payload("copy")), self.cid(nested))
        before = self.raw(op="world-view", principal="ember", object="box")
        self.reopen()                                    # replay of the whole journal
        self.assertEqual(self.raw(op="world-view", principal="ember", object="box"), before)

    def test_a_malformed_data_value_is_refused_by_name(self):
        # Refuted if Data admits a record that repeats a field, on any admission path.
        refused = self.create(REPEATED)
        self.assertEqual((refused["status"], refused["message"]),
                         ("error", "seed does not conform to the package state type"), refused)
        self.assertEqual(self.create()["status"], "created")
        bad = self.raw(op="world-propose", principal="ember", identity="w2", roots=[{"object": "box", "version": 0}],
                       writes=[{"object": "box", "edits": set_payload(REPEATED)}])
        self.assertEqual((bad["status"], bad["receipt"]["outcome"]["class"]), ("refused", "typeMismatch"), bad)


STATE_PACKAGE = """edition ObjectiveBend 1
record State:
  count: Nat
  payload: Data
def initial() -> State:
  {count: 0n, payload: Data.of::<{a: Nat}>({a: 1n})}
def touch(state: State) -> State:
  {count: state.count + 1n, payload: state.payload}
"""


class DataInPackageData(unittest.TestCase):
    """The typed-data schema (run-data-v1, the compact codec) with a Data field."""

    @classmethod
    def setUpClass(cls):
        cls.h = Host()
        cls.addClassCleanup(cls.h.close)

    def test_run_data_admits_any_well_formed_value_and_refuses_a_repeated_field_by_name(self):
        art = self.h.compile(STATE_PACKAGE, "touch")
        value = variant("deep", record(x=nat(1), y=variant("z", record())))
        ok = self.h.send({"op": "run-data-v1", "artifact": art, "arguments": [record(count=nat(4), payload=value)]})
        self.assertEqual(ok["status"], "finished", ok)
        self.assertEqual(ok["value"], record(count=nat(5), payload=value))
        bad = self.h.send({"op": "run-data-v1", "artifact": art, "arguments": [record(count=nat(4), payload=REPEATED)]})
        # The strict typed-data wire refuses the repeat before admission; the compact codec
        # (below) reaches the Data admission itself.
        self.assertEqual((bad["status"], bad["message"]), ("error", "duplicate typed data field"), bad)

    def test_initial_state_with_a_data_field_evaluates(self):
        art = self.h.compile(STATE_PACKAGE, "initial")
        r = self.h.send({"op": "run-data-v1", "artifact": art, "arguments": []})
        self.assertEqual((r["status"], r["value"]), ("finished", record(count=nat(0), payload=record(a=nat(1)))), r)

    def test_the_compact_codec_carries_a_data_field_as_its_own_wire_value(self):
        art = self.h.compile(STATE_PACKAGE, "initial")
        value = record(count=nat(2), payload=record(b=label("x"), a=nat(3)))
        enc = self.h.send({"op": "encode-compact", "selection": {"artifact": art, "path": []}, "value": value})
        self.assertEqual(enc["status"], "encoded", enc)
        dec = self.h.send({"op": "decode-compact", "selection": {"artifact": art, "path": []}, "value": enc["value"]})
        self.assertEqual((dec["status"], dec["value"]), ("decoded", value), dec)
        bad = self.h.send({"op": "decode-compact", "selection": {"artifact": art, "path": []},
                           "value": ["1", REPEATED]})
        self.assertEqual((bad["status"], bad["message"]), ("error", "typed data value at Data repeats a record field"), bad)


if __name__ == "__main__":
    unittest.main()
