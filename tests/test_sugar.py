"""Surface sugar compiles to the packet of its explicit spelling and moves no receipt; a misuse is
refused by name with the spelling it means.

Evidence for FOUNDATION §8 Surface (layer: kernel).

Surface sugar without new semantics: each sugared form compiles to the packet of
its explicit spelling. A packet names its modules' source hashes (`sourceModules`),
so two spellings are compared on the packet without that one field; everything else
(term, annotations, types, bounds, entry) must be byte-identical.

    python3 -m unittest tests.test_sugar -v
"""
import hashlib
import re
import json
import unittest

from tests.test_turn import BINDING, Host, library_modules, nat, variant
from tests.test_turn_world import TurnWorld, declared, label, record

HEAD = "edition ObjectiveBend 1\n"


def core(artifact):
    """The packet's digest without its source hashes."""
    packet = dict(artifact["packet"])
    packet.pop("sourceModules")
    return hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()


# A stand-in for world/lib/World.obend: the message and three world methods, so a sugared and
# an explicit spelling yield the same world calls without the world library's closure.
SUGAR_WORLD = HEAD + """record Reference:
  world: String
  object: String
record Message:
  object: Reference
  method: String
  argument: Data
record Edit:
  field: Nat
  after: Nat
sum Sent:
  delivery: {id: String}
  refused: {clause: String}
sum Reply:
  written: {}
  refused: {clause: String}
  later: {}
protocol world:
  send({object: Reference, method: String, argument: Data}) -> Sent
  put(Edit) -> Reply
"""


def sugar_modules(source, library=()):
    return library_modules(*library) + [{"name": "World", "source": SUGAR_WORLD}, {"name": "Package", "source": source}]


# A generic declaration in every package, so both spellings run the generics pass (an
# explicit `Data.of::<T>` is a specialization, and the pass adds its generated module
# to the package's metadata).
DATA_PLANS = HEAD + """import ./World.obend as World
sum Box<T>:
  box: {value: T}
record Note:
  text: String
  count: Nat
"""

# (name, explicit, sugared, entry): each pair must compile to the same packet.
DATA_PAIRS = [
    ("sum payload field",
     DATA_PLANS + "def tell(text: String) -> Activity<Nat>:\n"
     "  match world.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: Data.of::<{text: String}>({text: text})}):\n"
     "    case _: 1n\n",
     DATA_PLANS + "def tell(text: String) -> Activity<Nat>:\n"
     "  match world.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: {text: text}}):\n"
     "    case _: 1n\n",
     "tell"),
    ("named record value",
     DATA_PLANS + "def tell(note: Note) -> Activity<Nat>:\n"
     "  match world.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: Data.of::<Note>(note)}):\n"
     "    case _: note.count\n",
     DATA_PLANS + "def tell(note: Note) -> Activity<Nat>:\n"
     "  match world.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: note}):\n"
     "    case _: note.count\n",
     "tell"),
    ("call argument",
     DATA_PLANS + "def wrap(d: Data, n: Nat) -> Nat:\n  n\ndef f(n: Nat) -> Nat:\n  wrap(Data.of::<Nat>(n), n)\n",
     DATA_PLANS + "def wrap(d: Data, n: Nat) -> Nat:\n  n\ndef f(n: Nat) -> Nat:\n  wrap(n, n)\n",
     "f"),
    ("definition result",
     DATA_PLANS + "def nothing(n: Nat) -> Data:\n  Data.of::<{}>({})\n",
     DATA_PLANS + "def nothing(n: Nat) -> Data:\n  {}\n",
     "nothing"),
    ("both branches of an if",
     DATA_PLANS + "def pick(n: Nat) -> Data:\n  if n == 0n then Data.of::<String>(\"zero\") else Data.of::<Nat>(n)\n",
     DATA_PLANS + "def pick(n: Nat) -> Data:\n  if n == 0n then \"zero\" else n\n",
     "pick"),
]


LISTS_HEAD = HEAD + """import ./List.obend as Lists
import ./World.obend as World
record Rain:
  author: String
  text: String
record State:
  rains: Lists.List<Rain>
  count: Nat
def line(rain: Rain) -> String:
  rain.text
"""

# (name, explicit, sugared, entry)
GENERIC_PAIRS = [
    ("arguments fix both parameters",
     LISTS_HEAD + "def lines(state: State) -> Lists.List<String>:\n  Lists.map::<Rain, String>(state.rains, line)\n",
     LISTS_HEAD + "def lines(state: State) -> Lists.List<String>:\n  Lists.map(state.rains, line)\n",
     "lines"),
    ("a lambda's annotation",
     LISTS_HEAD + "def sizes(state: State) -> Lists.List<Nat>:\n  Lists.map::<Rain, Nat>(state.rains, fn(r: Rain) -> Nat: textLength(r.text))\n",
     LISTS_HEAD + "def sizes(state: State) -> Lists.List<Nat>:\n  Lists.map(state.rains, fn(r: Rain) -> Nat: textLength(r.text))\n",
     "sizes"),
    ("nested calls",
     LISTS_HEAD + "def count(state: State) -> Nat:\n  Lists.length::<String>(Lists.map::<Rain, String>(state.rains, line)) + Lists.length::<Rain>(state.rains)\n",
     LISTS_HEAD + "def count(state: State) -> Nat:\n  Lists.length(Lists.map(state.rains, line)) + Lists.length(state.rains)\n",
     "count"),
    ("constructor from its head",
     LISTS_HEAD + "def one(rain: Rain, state: State) -> Lists.List<Rain>:\n  Lists.List::<Rain>.cons({head: rain, tail: state.rains})\n",
     LISTS_HEAD + "def one(rain: Rain, state: State) -> Lists.List<Rain>:\n  Lists.List.cons({head: rain, tail: state.rains})\n",
     "one"),
    ("constructor from the expected type",
     LISTS_HEAD + "def fresh(n: Nat) -> State:\n  {rains: Lists.List::<Rain>.nil({}), count: n}\n",
     LISTS_HEAD + "def fresh(n: Nat) -> State:\n  {rains: Lists.List.nil({}), count: n}\n",
     "fresh"),
    ("a literal head with a declared tail",
     LISTS_HEAD + "def said(text: String, state: State) -> Lists.List<Rain>:\n  Lists.List::<Rain>.cons({head: {author: \"me\", text: text}, tail: state.rains})\n",
     LISTS_HEAD + "def said(text: String, state: State) -> Lists.List<Rain>:\n  Lists.List.cons({head: {author: \"me\", text: text}, tail: state.rains})\n",
     "said"),
    ("an activity's result type",
     LISTS_HEAD + "def wrote<T>(state: State, then: Nat -> T) -> Activity<T>:\n"
     "  match world.put({field: state.count + 1n, after: 0n}):\n    case _: then(state.count)\n"
     "def bump(state: State, n: Nat) -> Activity<Nat>:\n"
     "  wrote::<Nat>(state, fn(c: Nat) -> Nat: c + n)\n",
     LISTS_HEAD + "def wrote<T>(state: State, then: Nat -> T) -> Activity<T>:\n"
     "  match world.put({field: state.count + 1n, after: 0n}):\n    case _: then(state.count)\n"
     "def bump(state: State, n: Nat) -> Activity<Nat>:\n"
     "  wrote(state, fn(c: Nat) -> Nat: c + n)\n",
     "bump"),
    ("inside a generic body",
     LISTS_HEAD + "def twice<T>(items: Lists.List<T>) -> Nat:\n  Lists.length::<T>(items) + Lists.length::<T>(items)\n"
     "def f(state: State) -> Nat:\n  twice::<Rain>(state.rains)\n",
     LISTS_HEAD + "def twice<T>(items: Lists.List<T>) -> Nat:\n  Lists.length(items) + Lists.length(items)\n"
     "def f(state: State) -> Nat:\n  twice(state.rains)\n",
     "f"),
]


TURN_HEAD = HEAD + """import ./World.obend as World
"""

BUMP_SUGARED = TURN_HEAD + """def bump(count: Nat) -> Activity<Nat>:
  let written(_) = world.put({field: 0n, after: count + 1n})
  let next = count + 1n
  next
"""
# The match the statement lowers to: one refusal arm per label it does not name.
BUMP_EXPLICIT = TURN_HEAD + """def bump(count: Nat) -> Activity<Nat>:
  match world.put({field: 0n, after: count + 1n}):
    case written(_):
      let next = count + 1n
      next
    case refused(_): refuse("unexpected response refused")
    case later(_): refuse("unexpected response later")
"""

# Two statements in a row, the second binding its payload.
TWICE_SUGARED = TURN_HEAD + """def twice(count: Nat) -> Activity<String>:
  let written(_) = world.put({field: 0n, after: count})
  let refused(r) = world.put({field: 1n, after: count})
  r.clause
"""
TWICE_EXPLICIT = TURN_HEAD + """def twice(count: Nat) -> Activity<String>:
  match world.put({field: 0n, after: count}):
    case written(_):
      match world.put({field: 1n, after: count}):
        case refused(r): r.clause
        case written(_): refuse("unexpected response written")
        case later(_): refuse("unexpected response later")
    case refused(_): refuse("unexpected response refused")
    case later(_): refuse("unexpected response later")
"""


class SugarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def compile(self, source, entry, library=()):
        reply = self.h.send({"op": "compile", "entry": entry, "modules": sugar_modules(source, library)})
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def check(self, source, entry, library=()):
        return self.h.send({"op": "check-package", "entry": entry, "modules": sugar_modules(source, library)})

    def same(self, explicit, sugared, entry, library=()):
        a = self.compile(explicit, entry, library)
        b = self.compile(sugared, entry, library)
        self.assertEqual(core(a), core(b))
        self.assertEqual(a["type"], b["type"])
        return a, b

    # 1. Implicit Data injection.
    def test_data_injection_is_its_explicit_spelling(self):
        for name, explicit, sugared, entry in DATA_PAIRS:
            with self.subTest(form=name):
                self.same(explicit, sugared, entry)

    def test_data_injection_refuses_a_closure_by_name(self):
        source = DATA_PLANS + "def wrap(d: Data, n: Nat) -> Nat:\n  n\ndef f(n: Nat) -> Nat:\n  wrap(fn(x: Nat) -> Nat: x, n)\n"
        reply = self.check(source, "f")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (data-injection): this value is a function", reply["diagnostic"]["message"])

    def test_data_injection_refuses_an_activity_by_name(self):
        source = DATA_PLANS + ("def go(n: Nat) -> Activity<Nat>:\n"
                               "  match world.send({object: {world: \"\", object: \"b\"}, method: \"m\", argument: {}}):\n"
                               "    case _: n\n"
                               "def wrap(d: Data, n: Nat) -> Nat:\n  n\n"
                               "def f(n: Nat) -> Nat:\n  wrap(go(n), n)\n")
        reply = self.check(source, "f")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (data-injection): this value is an Activity", reply["diagnostic"]["message"])

    # 2. Type-argument inference.
    def test_inferred_type_arguments_are_their_explicit_spelling(self):
        for name, explicit, sugared, entry in GENERIC_PAIRS:
            with self.subTest(form=name):
                a, b = self.same(explicit, sugared, entry, ("List",))
                # Instance records name source hashes and spans; their names and order agree.
                self.assertEqual([i["name"] for i in a["genericInstances"]],
                                 [i["name"] for i in b["genericInstances"]])

    def test_an_uninferable_parameter_is_named_with_its_spelling(self):
        # Neither the argument (a nil of no known type) nor the position fixes T.
        source = LISTS_HEAD + "def zero(n: Nat) -> Nat:\n  Lists.length(Lists.List.nil({}))\n"
        reply = self.check(source, "zero", ("List",))
        self.assertEqual(reply["status"], "refused", reply)
        message = reply["diagnostic"]["message"]
        self.assertIn("cannot infer the type argument T of Lists.length (line 13)", message)
        self.assertIn("write Lists.length::<T>(...) naming T", message)

    def test_a_partly_inferred_call_shows_what_was_inferred(self):
        # kept<T, U>(found: Maybe<U>, rest: List<U>) never mentions T (List.kept itself
        # lost that phantom parameter, so the fixture declares its own).
        source = LISTS_HEAD + ("def kept<T, U>(found: Lists.Maybe<U>, rest: Lists.List<U>) -> Lists.List<U>:\n  rest\n"
                               "def pick(state: State) -> Lists.List<Rain>:\n  kept(Lists.Maybe.none({}), state.rains)\n")
        reply = self.check(source, "pick", ("List",))
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("cannot infer the type argument T of kept", reply["diagnostic"]["message"])
        self.assertIn("write kept::<T, Rain>(...) naming T", reply["diagnostic"]["message"])
    # 3. The statement form for one expected response.
    def test_let_response_is_its_match(self):
        self.same(BUMP_EXPLICIT, BUMP_SUGARED, "bump")
        self.same(TWICE_EXPLICIT, TWICE_SUGARED, "twice")

    def test_the_named_response_continues_the_block(self):
        artifact = self.compile(BUMP_SUGARED, "bump")
        started = self.h.start(artifact, [nat(4)])
        self.assertEqual(started["status"], "yielded", started)
        done = self.h.resume(artifact, started["checkpoint"], variant("written"))
        self.assertEqual(done["status"], "finished", done)
        self.assertEqual(done["value"], nat(5))

    def test_any_other_response_refuses_the_turn_by_name(self):
        artifact = self.compile(BUMP_SUGARED, "bump")
        for label, payload in (("refused", {"tag": "record", "fields": [
                {"name": "clause", "value": {"tag": "label", "value": "owner"}}]}), ("later", None)):
            with self.subTest(response=label):
                started = self.h.start(artifact, [nat(4)])
                self.assertEqual(started["status"], "yielded", started)
                reply = self.h.resume(artifact, started["checkpoint"], variant(label, payload))
                self.assertEqual(reply, {"status": "error", "message": "turn refused: unexpected response " + label})

    def test_the_second_statement_refuses_after_the_first_continues(self):
        artifact = self.compile(TWICE_SUGARED, "twice")
        started = self.h.start(artifact, [nat(1)])
        second = self.h.resume(artifact, started["checkpoint"], variant("written"))
        self.assertEqual(second["status"], "yielded", second)
        reply = self.h.resume(artifact, second["checkpoint"], variant("written"))
        self.assertEqual(reply["message"], "turn refused: unexpected response written")

    def test_let_response_takes_a_world_call(self):
        source = TURN_HEAD + ("def pick(reply: World.Reply) -> Activity<Nat>:\n"
                              "  let written(_) = reply\n  1n\n")
        reply = self.check(source, "pick")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (let-response)", reply["diagnostic"]["message"])

    def test_refuse_stands_only_where_an_activity_finishes(self):
        pure = TURN_HEAD + "def f(n: Nat) -> Nat:\n  refuse(\"no\")\n"
        reply = self.check(pure, "f")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (refuse-outside-activity)", reply["diagnostic"]["message"])
        nested = TURN_HEAD + ("def g(n: Nat) -> Activity<Nat>:\n"
                              "  if refuse(\"no\") then n else 0n\n")
        reply = self.check(nested, "g")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (refuse-outside-tail)", reply["diagnostic"]["message"])
        # In both branches of a tail `if`, it is where the activity finishes.
        branches = TURN_HEAD + ("def h(n: Nat) -> Activity<Nat>:\n"
                                "  if n == 0n then refuse(\"zero\") else n\n")
        artifact = self.compile(branches, "h")
        self.assertEqual(self.h.start(artifact, [nat(0)])["message"], "turn refused: zero")
        self.assertEqual(self.h.start(artifact, [nat(3)])["value"], nat(3))

    def test_halt_suggests_the_statement(self):
        reply = self.check(HEAD + "def stop(n: Nat) -> Nat:\n  halt(\"no\")\n", "stop")
        self.assertIn("let written(_) = world.write(...)", reply["diagnostic"]["hint"])


SCENE = HEAD + """record State:
  title: String
  count: Nat
"""
# (name, explicit, sugared, entry)
TEXT_PAIRS = [
    ("two pieces", SCENE + "def f(s: State) -> String:\n  textConcat(\"SCENE \", s.title)\n",
     SCENE + "def f(s: State) -> String:\n  \"SCENE {s.title}\"\n", "f"),
    ("four pieces, right-nested",
     SCENE + "def f(s: State) -> String:\n  textConcat(\"SCENE \", textConcat(s.title, textConcat(\": \", natText(s.count))))\n",
     SCENE + "def f(s: State) -> String:\n  \"SCENE {s.title}: {natText(s.count)}\"\n", "f"),
    ("five pieces, joined",
     SCENE + "def f(s: State) -> String:\n  textJoin(TextPieces.cons({head: \"SCENE \", tail: TextPieces.cons({head: s.title, tail: "
     "TextPieces.cons({head: \" (\", tail: TextPieces.cons({head: natText(s.count), tail: TextPieces.cons({head: \" here)\", "
     "tail: TextPieces.nil({})})})})})}), \"\")\n",
     SCENE + "def f(s: State) -> String:\n  \"SCENE {s.title} ({natText(s.count)} here)\"\n", "f"),
    ("doubled braces and an escaped literal inside",
     SCENE + "def f(s: State) -> String:\n  textConcat(\"{{\", textConcat(textConcat(s.title, \"!\"), \"}}\"))\n",
     SCENE + "def f(s: State) -> String:\n  \"{{{textConcat(s.title, \\\"!\\\")}}}\"\n", "f"),
]


FORM_HEAD = HEAD + "import ./List.obend as Lists\nimport ./Form.obend as F\n"
FORM_EXPLICIT = FORM_HEAD + """def planting() -> F.Form:
  {card: "", action: "plant", fields: F.Fields.cons({head: {name: "colour", kind: F.Kind.choice({options: F.Names.cons({head: "amber", tail: F.Names.cons({head: "violet", tail: F.Names.cons({head: "silver", tail: F.Names.nil({})})})})})}, tail: F.Fields.cons({head: {name: "seed", kind: F.Kind.text({min: 1n, max: 80n})}, tail: F.Fields.cons({head: {name: "count", kind: F.Kind.natural({min: 1n, max: 1000n})}, tail: F.Fields.nil({})})})})}
def forms() -> Lists.List<F.Form>:
  Lists.List.cons({head: planting(), tail: Lists.List.nil({})})
"""
FORM_SUGARED = FORM_HEAD + """form plant as planting:
  colour: amber | violet | silver
  seed: text 1..80
  count: natural 1..1000n
"""


GARDEN = HEAD + """import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as P
import ./World.obend as World
record State:
  planted: Nat
  children: Lists.List<P.Reference>
  note: String
def plant(state: State, input: {child: P.Reference, note: String}, context: Abi.Context) -> Activity<Nat>:
"""
WRITE_EXPLICIT = GARDEN + """  let written(_) = world.write(extend(keep(), {planted: P.Edit::<Nat, Nat>.add({delta: 1n}), children: P.Entries::<P.Reference, P.Reference>.append({item: input.child}), note: P.Edit::<String, {}>.set({value: input.note})}))
  state.planted + 1n
"""
WRITE_SUGARED = GARDEN + """  let written(_) = write {planted: add 1n, children: append input.child, note: set input.note}
  state.planted + 1n
"""


COUNTER = HEAD + """import ./Abi.obend as Abi
import ./Plan.obend as Plans
import ./World.obend as World
record State:
  count: Nat
law small "a counter stays at most a hundred": new.count <= 100
def initial() -> State:
  {count: 0n}
def bump(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = world.write::<Edits>({count: Plans.Edit.add({delta: input.n})})
  input.n
"""


class Interpolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def test_interpolation_is_its_explicit_spelling(self):
        for name, explicit, sugared, entry in TEXT_PAIRS:
            with self.subTest(form=name):
                a = self.h.compile(explicit, entry)
                b = self.h.compile(sugared, entry)
                self.assertEqual(core(a), core(b))

    def test_interpolation_runs(self):
        artifact = self.h.compile(TEXT_PAIRS[2][2], "f")
        state = {"tag": "record", "fields": [{"name": "title", "value": {"tag": "label", "value": "Moth"}},
                                             {"name": "count", "value": nat(3)}]}
        reply = self.h.send({"op": "run", "artifact": artifact, "arguments": [state]})
        self.assertEqual(reply["value"], {"tag": "label", "value": "SCENE Moth (3 here)"}, reply)

    def test_malformed_interpolations_are_refused_by_name(self):
        for text, message in (("\"a {s.title\"", "is not closed"), ("\"a } b\"", "written }}"),
                              ("\"a {s.title s.title}\"", "holds one expression")):
            with self.subTest(text=text):
                reply = self.h.send({"op": "check-package", "entry": "f", "modules": [
                    {"name": "Package", "source": SCENE + "def f(s: State) -> String:\n  " + text + "\n"}]})
                self.assertEqual(reply["status"], "refused", reply)
                self.assertIn(message, reply["diagnostic"]["message"])

    def test_template_habits_suggest_interpolation(self):
        reply = self.h.send({"op": "check-package", "entry": "f", "modules": [
            {"name": "Package", "source": SCENE + "def f(s: State) -> String:\n  `SCENE ${s.title}`\n"}]})
        self.assertIn("text interpolation is", reply["diagnostic"].get("hint", ""), reply)


class Forms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def check(self, source, entry):
        return self.h.send({"op": "check-package", "entry": entry,
                            "modules": library_modules("List", "Form") + [{"name": "Package", "source": source}]})

    def test_a_form_block_is_its_form_record(self):
        a = self.h.compile(FORM_EXPLICIT, "planting", ("List", "Form"))
        b = self.h.compile(FORM_SUGARED, "planting", ("List", "Form"))
        self.assertEqual(core(a), core(b))

    def test_the_default_name_is_the_action_and_form(self):
        source = FORM_HEAD + "form plant:\n  seed: text 1..80\n"
        self.assertEqual(self.check(source, "plantForm")["status"], "checked")

    def test_a_source_field_is_the_source_kind(self):
        # Form.obend's `source: {}` case is the objects lane's: one library with it, one without.
        modules, lacking = library_modules("List", "Form"), library_modules("List", "Form")
        for with_case, ms in ((True, modules), (False, lacking)):
            for m in ms:
                if m["name"] == "Form":
                    bare = m["source"].replace("  source: {}\n", "")
                    m["source"] = bare.replace("sum Kind:\n", "sum Kind:\n  source: {}\n") if with_case else bare
        explicit = FORM_HEAD + ("def workshopForm() -> F.Form:\n  {card: \"\", action: \"compile\", fields: "
                                "F.Fields.cons({head: {name: \"program\", kind: F.Kind.source({})}, tail: "
                                "F.Fields.cons({head: {name: \"note\", kind: F.Kind.text({min: 1n, max: 80n})}, "
                                "tail: F.Fields.nil({})})})}\n"
                                "def forms() -> Lists.List<F.Form>:\n  Lists.List.cons({head: workshopForm(), tail: Lists.List.nil({})})\n")
        sugared = FORM_HEAD + "form compile as workshopForm:\n  program: source\n  note: text 1..80\n"
        replies = [self.h.send({"op": "compile", "entry": "workshopForm",
                                "modules": modules + [{"name": "Package", "source": text}]}) for text in (explicit, sugared)]
        self.assertEqual(core(replies[0]["artifact"]), core(replies[1]["artifact"]), replies)
        self.assertIn('"source"', json.dumps(replies[1]["artifact"]["packet"]))
        # Against a Form library without the case, the lowering is refused by the elaborator.
        reply = self.h.send({"op": "check-package", "entry": "workshopForm",
                             "modules": lacking + [{"name": "Package", "source": sugared}]})
        self.assertEqual(reply["status"], "refused", reply)

    def test_a_form_block_needs_the_form_library_and_known_kinds(self):
        reply = self.check(HEAD + "form plant:\n  seed: text 1..80\n", "plantForm")
        self.assertIn("a form block needs the Form library", reply["diagnostic"]["message"])
        reply = self.check(FORM_HEAD + "form plant:\n  seed: words 1..80\n", "plantForm")
        self.assertIn("a form field is `name: text MIN..MAX`", reply["diagnostic"]["message"])
        self.assertIn("`name: source`", reply["diagnostic"]["message"])


# KERNEL-HANDOFF §16 item 8c: a form block declares its method's input record and, without a
# hand-written forms(), forms() of the blocks in source order.
FORM_STATE = FORM_HEAD + """sum Colour:
  amber: {}
  violet: {}
  silver: {}
record State:
  planted: Nat
def plant(state: State, input: PlantInput) -> Nat:
  state.planted + input.count
def water(state: State, input: WaterInput) -> Nat:
  textLength(input.note)
"""
FORM_BLOCKS = """form plant as planting:
  colour: amber | violet | silver
  seed: text 1..80
  count: natural 1..1000
form water:
  note: text 0..40
  shade: Colour
"""
FORM_BLOCKS_EXPLICIT = """def planting() -> F.Form:
  {card: "", action: "plant", fields: F.Fields.cons({head: {name: "colour", kind: F.Kind.choice({options: F.Names.cons({head: "amber", tail: F.Names.cons({head: "violet", tail: F.Names.cons({head: "silver", tail: F.Names.nil({})})})})})}, tail: F.Fields.cons({head: {name: "seed", kind: F.Kind.text({min: 1n, max: 80n})}, tail: F.Fields.cons({head: {name: "count", kind: F.Kind.natural({min: 1n, max: 1000n})}, tail: F.Fields.nil({})})})})}
def waterForm() -> F.Form:
  {card: "", action: "water", fields: F.Fields.cons({head: {name: "note", kind: F.Kind.text({min: 0n, max: 40n})}, tail: F.Fields.cons({head: {name: "shade", kind: F.Kind.choice({options: F.Names.cons({head: "amber", tail: F.Names.cons({head: "violet", tail: F.Names.cons({head: "silver", tail: F.Names.nil({})})})})})}, tail: F.Fields.nil({})})})}
"""
FORM_INPUTS_EXPLICIT = """sum PlantColour:
  amber: {}
  violet: {}
  silver: {}
record PlantInput:
  colour: PlantColour
  seed: String
  count: Nat
record WaterInput:
  note: String
  shade: Colour
def forms() -> Lists.List<F.Form>:
  Lists.List.cons({head: planting(), tail: Lists.List.cons({head: waterForm(), tail: Lists.List.nil({})})})
"""


def kind(label, payload):
    return {"tag": "variant", "label": label, "payload": {"tag": "record", "fields": payload}}


def nat_field(name, n):
    return {"name": name, "value": {"tag": "natural", "value": str(n)}}


def choice(*options):
    return kind("choice", [{"name": "options", "value": {"tag": "list", "items": [{"tag": "label", "value": o} for o in options]}}])


class FormInputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def send(self, op, source, entry):
        return self.h.send({"op": op, "entry": entry,
                            "modules": library_modules("List", "Form") + [{"name": "Package", "source": source}]})

    def compiled(self, source, entry):
        reply = self.send("compile", source, entry)
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def test_form_blocks_are_their_values_inputs_and_forms(self):
        sugared = FORM_STATE + FORM_BLOCKS
        explicit = FORM_STATE + FORM_BLOCKS_EXPLICIT + FORM_INPUTS_EXPLICIT
        for entry in ("plant", "water", "planting", "waterForm", "forms"):
            with self.subTest(entry=entry):
                self.assertEqual(core(self.compiled(sugared, entry)), core(self.compiled(explicit, entry)))

    def test_a_method_row_carries_its_form(self):
        rows = {row["name"]: row for row in self.compiled(FORM_STATE + FORM_BLOCKS, "plant")["methods"]}
        self.assertEqual(rows["plant"]["form"], [
            {"name": "colour", "kind": choice("amber", "violet", "silver")},
            {"name": "seed", "kind": kind("text", [nat_field("min", 1), nat_field("max", 80)])},
            {"name": "count", "kind": kind("natural", [nat_field("min", 1), nat_field("max", 1000)])}])
        # A field naming a closed sum is offered as the choice of its labels.
        self.assertEqual(rows["water"]["form"][1], {"name": "shade", "kind": choice("amber", "violet", "silver")})
        # A module without form blocks has rows without `form`.
        plain = self.compiled(FORM_STATE.replace("PlantInput", "{count: Nat}").replace("WaterInput", "{note: String}"), "plant")
        self.assertTrue(all("form" not in row for row in plain["methods"]), plain["methods"])

    def test_a_hand_written_forms_is_kept(self):
        # The derived forms() lists both blocks in source order (the first test); a module's own wins.
        own = "def forms() -> Lists.List<F.Form>:\n  Lists.List.cons({head: waterForm(), tail: Lists.List.nil({})})\n"
        inputs = FORM_INPUTS_EXPLICIT[:FORM_INPUTS_EXPLICIT.index("def forms()")]
        self.assertEqual(core(self.compiled(FORM_STATE + FORM_BLOCKS + own, "forms")),
                         core(self.compiled(FORM_STATE + FORM_BLOCKS_EXPLICIT + inputs + own, "forms")))

    def test_a_named_kind_must_be_a_closed_sum_of_empty_cases(self):
        source = FORM_STATE.replace("record State:", "sum Mixed:\n  one: {}\n  two: {n: Nat}\nrecord State:") + \
            FORM_BLOCKS.replace("shade: Colour", "shade: Mixed")
        reply = self.send("check-package", source, "plant")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (form-kind): form water offers shade: Mixed, which is not a closed sum of empty cases",
                      reply["diagnostic"]["message"])

    def test_a_method_takes_its_form_blocks_input(self):
        reply = self.send("check-package", FORM_STATE.replace("input: PlantInput", "input: {count: Nat}") + FORM_BLOCKS, "plant")
        self.assertEqual(reply["status"], "refused", reply)
        d = reply["diagnostic"]
        self.assertIn("refused (form-input): plant has a form block, so its input is PlantInput", d["message"])
        self.assertEqual((d["definition"], d["expected"], d["found"]), ("Package.plant", "PlantInput", "{count: Nat}"))
        # A block without fields: the method takes no input, or `{}`; one with fields needs its input.
        ring = FORM_STATE + FORM_BLOCKS + "form ring:\ndef ring(state: State) -> Nat:\n  0n\n"
        self.assertEqual(self.send("check-package", ring, "ring")["status"], "checked")
        self.assertEqual(self.send("check-package", ring.replace("ring(state: State)", "ring(state: State, input: {})"), "ring")["status"], "checked")
        none = FORM_STATE.replace("def water(state: State, input: WaterInput)", "def water(state: State)").replace("textLength(input.note)", "0n")
        self.assertIn("so its input is WaterInput", self.send("check-package", none + FORM_BLOCKS, "water")["diagnostic"]["message"])

    def test_a_declared_input_beside_its_form_block_is_refused_by_name(self):
        source = FORM_STATE + FORM_BLOCKS + "record PlantInput:\n  count: Nat\n"
        reply = self.send("check-package", source, "plant")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (form-input): form plant declares PlantInput, its method's input, and so does the module", reply["diagnostic"]["message"])


class Writes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def test_write_is_its_plan(self):
        a = self.h.compile(WRITE_EXPLICIT, "plant", ("Abi", "List", "World"))
        b = self.h.compile(WRITE_SUGARED, "plant", ("Abi", "List", "World"))
        self.assertEqual(core(a), core(b))

    def test_write_names_its_operations(self):
        source = WRITE_SUGARED.replace("add 1n", "bump 1n")
        reply = self.h.send({"op": "check-package", "entry": "plant",
                             "modules": library_modules("Abi", "List", "World") + [{"name": "Package", "source": source}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("takes add, set, append, remove, amend, removeItem, insert, upsert or retract, not bump", reply["diagnostic"]["message"])


    def test_relation_edits_are_their_plans(self):
        # RELATIONAL section 3: insert/upsert/retract, against world/lib/Plan.obend, which has them.
        modules = library_modules("Abi", "List", "World")
        for op, ctor, payload, value in [("insert", "insert", "row", "input.child"),
                                         ("upsert", "upsert", "row", "input.child"),
                                         ("retract", "retract", "key", "{object: input.note}")]:
            with self.subTest(op=op):
                sugared = GARDEN + "  let written(_) = write {children: %s %s}\n  state.planted\n" % (op, value)
                explicit = GARDEN + ("  let written(_) = world.write(extend(keep(), "
                                     "{children: P.Entries::<P.Reference, P.Reference>.%s({%s: %s})}))\n  state.planted\n" % (ctor, payload, value))
                packets = []
                for source in (sugared, explicit):
                    reply = self.h.send({"op": "compile", "entry": "plant",
                                         "modules": modules + [{"name": "Package", "source": source}]})
                    self.assertEqual(reply["status"], "compiled", reply)
                    packets.append(core(reply["artifact"]))
                self.assertEqual(packets[0], packets[1])


    def compiled_core(self, source, library=("Abi", "List", "World")):
        reply = self.h.send({"op": "compile", "entry": "plant",
                             "modules": library_modules(*library) + [{"name": "Package", "source": source}]})
        self.assertEqual(reply["status"], "compiled", reply)
        return core(reply["artifact"])

    def test_remove_and_amend_name_items(self):
        # Plan.obend lost the index forms: `remove ITEM` is removeItem, `amend ITEM with CHANGE` amendItem.
        for sugared, explicit in [("children: remove input.child", "children: P.Entries::<P.Reference, P.Reference>.removeItem({item: input.child})"),
                                  ("children: amend input.child with input.child", "children: P.Entries::<P.Reference, P.Reference>.amendItem({item: input.child, change: input.child})")]:
            with self.subTest(edit=sugared):
                self.assertEqual(self.compiled_core(GARDEN + "  let written(_) = write {%s}\n  state.planted\n" % sugared),
                                 self.compiled_core(GARDEN + "  let written(_) = world.write(extend(keep(), {%s}))\n  state.planted\n" % explicit))

    def test_remove_on_a_relation_is_a_retract_by_key(self):
        sugared = ROWS + "  let written(_) = write {rows: remove {at: input.at}}\n  0n\n"
        explicit = ROWS + "  let written(_) = world.write(extend(keep(), {rows: P.Entries::<Row, Row>.retract({key: {at: input.at}})}))\n  0n\n"
        library = ("Abi", "List", "World", "Relation")
        self.assertEqual(self.compiled_core(sugared, library), self.compiled_core(explicit, library))

    def test_an_index_is_refused_by_name(self):
        source = GARDEN + "  let written(_) = write {children: remove {index: 0n}}\n  state.planted\n"
        reply = self.h.send({"op": "check-package", "entry": "plant",
                             "modules": library_modules("Abi", "List", "World") + [{"name": "Package", "source": source}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("names a position, and edits name items", reply["diagnostic"]["message"])
        self.assertIn("children: remove ITEM", reply["diagnostic"]["message"])


ROWS = HEAD + """import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as P
import ./Relation.obend as Relations
import ./World.obend as World
record Row:
  at: Nat
  text: String
record State:
  rows: Relations.Relation<Row>
def plant(state: State, input: {at: Nat}, context: Abi.Context) -> Activity<Nat>:
"""

RELATIONS = HEAD + """import ./List.obend as Lists
record Decl:
  field: String
  key: Lists.List<String>
record State:
  rains: Lists.List<{author: String, at: Nat, text: String}>
def relations() -> Lists.List<Decl>:
  Lists.List.cons({head: {field: "rains", key: Lists.List.cons({head: "author", tail: Lists.List.cons({head: "at", tail: Lists.List.nil({})})})}, tail: Lists.List.nil({})})
def initial() -> State:
  {rains: Lists.List.nil({})}
"""


class Relations(unittest.TestCase):
    """RELATIONAL section 2: a package's `relations()` is listed in its artifacts, so the host
    reads the keys without compiling a definition per object."""

    def test_relations_are_listed_in_every_entry_artifact(self):
        h = Host()
        self.addCleanup(h.close)
        art = h.compile(RELATIONS, "initial", ("List",))
        self.assertEqual(art["relations"], [{"field": "rains", "key": ["author", "at"], "limit": 0}])
        plain = h.compile(RELATIONS.replace("def relations()", "def declared()"), "initial", ("List",))
        self.assertNotIn("relations", plain)

    def test_a_declaration_carries_its_limit_and_retention(self):
        # RELATIONAL section 11: a limit (0 is the host's default) and the retention past it.
        h = Host()
        self.addCleanup(h.close)
        bounded = (RELATIONS.replace("  key: Lists.List<String>\n", "  key: Lists.List<String>\n  limit: Nat\n  retain: String\n")
                   .replace("tail: Lists.List.nil({})})})}, tail", "tail: Lists.List.nil({})})}), limit: 64n, retain: \"dropOldest\"}, tail"))
        art = h.compile(bounded, "initial", ("List",))
        self.assertEqual(art["relations"], [{"field": "rains", "key": ["author", "at"], "limit": 64, "retain": "dropOldest"}])
        bad = h.send({"op": "compile", "entry": "initial", "modules": library_modules("List") + [
            {"name": "Package", "source": bounded.replace("  limit: Nat\n", "  limit: String\n").replace("limit: 64n", "limit: \"many\"")}]})
        self.assertEqual(bad["status"], "error", bad)
        self.assertIn("relations(): a limit is a Nat", bad["message"])


class LawReading(TurnWorld):
    """A law's reading is carried beside it; the law enforces exactly as without one, and
    the statement form runs on the real host (a staged write is answered `written`)."""

    def test_a_law_with_a_reading_enforces_as_before(self):
        self.create("c", library_modules("Abi", "World") + [{"name": "Package", "source": declared(COUNTER)}], 0)
        ok = self.turn("c", "bump", record(n=nat(5)))
        self.assertEqual(ok["status"], "admitted", ok)
        refused = self.turn("c", "bump", record(n=nat(150)))
        self.assertEqual(refused["status"], "refused", refused)
        self.assertEqual(refused["receipt"]["outcome"].get("clause"), "small", refused)

    def test_write_runs_on_the_host(self):
        source = WRITE_SUGARED + "def initial() -> State:\n  {planted: 0n, children: Lists.List.nil({}), note: \"\"}\n"
        r = self.host.send(op="world-create", principal="ember", identity="create-g", object="g",
                           modules=library_modules("Abi", "List", "World") + [{"name": "Package", "source": declared(source)}],
                           entry="initial", seed=record())
        self.assertEqual(r["status"], "created", r)
        child = record(world=label(""), object=label("bell-1"))
        done = self.turn("g", "plant", record(child=child, note=label("hello")))
        self.assertEqual(done["status"], "admitted", done)
        state = self.host.send(op="world-view", principal="ember", object="g")["state"]
        fields = {f["name"]: f["value"] for f in state["fields"]}
        self.assertEqual(fields["planted"], nat(1))
        self.assertEqual(fields["note"], label("hello"))
        self.assertEqual(fields["children"], {"tag": "list", "items": [child]})

    def test_a_reading_is_a_string_literal(self):
        h = Host()
        self.addCleanup(h.close)
        bad = COUNTER.replace('"a counter stays at most a hundred"', "at most a hundred")
        reply = h.send({"op": "check-package", "entry": "initial",
                        "modules": library_modules("Abi", "World") + [{"name": "Package", "source": bad}]})
        self.assertEqual(reply["status"], "refused", reply)


if __name__ == "__main__":
    unittest.main()


# KERNEL-HANDOFF §16 item 8a: a module with a State and the Plan library and neither `Edits` nor
# `keep` gets both, at the end of the module: lists and relations `Entries<X, X>`, a Nat `Edit<Nat, Nat>`,
# anything else `Edit<T, {}>`; `keep()` keeps every field.
DERIVED_HEAD = HEAD + """import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as P
import ./Relation.obend as Relations
import ./World.obend as World
record Row:
  at: Nat
  text: String
type Names = Lists.List<String>
record State:
  planted: Nat
  children: Lists.List<P.Reference>
  names: Names
  rows: Relations.Relation<Row>
  note: String
  open: Bool
  owner: P.Reference
"""
DERIVED_PAIR = """record Edits:
  planted: P.Edit<Nat, Nat>
  children: P.Entries<P.Reference, P.Reference>
  names: P.Entries<String, String>
  rows: P.Entries<Row, Row>
  note: P.Edit<String, {}>
  open: P.Edit<Bool, {}>
  owner: P.Edit<P.Reference, {}>
def keep() -> Edits:
  {planted: P.Edit.keep({}), children: P.Entries.keep({}), names: P.Entries.keep({}), rows: P.Entries.keep({}), note: P.Edit.keep({}), open: P.Edit.keep({}), owner: P.Edit.keep({})}
"""
DERIVED_REST = """def initial() -> State:
  {planted: 0n, children: Lists.List.nil({}), names: Lists.List.nil({}), rows: Relations.empty(), note: "", open: false, owner: P.nobody()}
def plant(state: State, input: {child: P.Reference, at: Nat, name: String}, context: Abi.Context) -> Activity<Nat>:
  let written(_) = write {planted: add 1n, children: append input.child, names: amend input.name with "{input.name}!", rows: upsert {at: input.at, text: input.name}, open: set true}
  state.planted + 1n
"""
DERIVED_LIBRARY = ("Abi", "List", "World", "Relation")


def without_state(source):
    """The module with its State renamed (and nothing fixed), so a hand-written Edits and keep()
    are its own: the explicit spelling a derived pair is compared against."""
    return re.sub(r"(?<![.\w])State\b", "Shape", source).replace(": fixed ", ": ")


class DerivedEdits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def send(self, op, source, entry, extra=()):
        return self.h.send({"op": op, "entry": entry, "modules": library_modules(*DERIVED_LIBRARY) + list(extra) +
                            [{"name": "Package", "source": source}]})

    def compiled(self, source, entry, extra=()):
        reply = self.send("compile", source, entry, extra)
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def test_derived_edits_are_the_pair_written_at_the_end(self):
        derived = DERIVED_HEAD + DERIVED_REST
        written = without_state(DERIVED_HEAD + DERIVED_REST + DERIVED_PAIR)
        for entry in ("plant", "keep", "initial"):
            with self.subTest(entry=entry):
                self.assertEqual(core(self.compiled(derived, entry)), core(self.compiled(written, entry)))

    def test_keep_keeps_every_field_in_state_order(self):
        artifact = self.compiled(DERIVED_HEAD + DERIVED_REST, "keep")
        reply = self.h.send({"op": "run", "artifact": artifact, "arguments": []})
        self.assertEqual(reply["status"], "finished", reply)
        fields = reply["value"]["fields"]
        self.assertEqual([f["name"] for f in fields], ["planted", "children", "names", "rows", "note", "open", "owner"])
        self.assertTrue(all(f["value"] == {"tag": "variant", "label": "keep", "payload": {"tag": "record", "fields": []}}
                            for f in fields), fields)

    def test_a_hand_written_pair_beside_state_is_refused_by_name(self):
        bump = "def bump(state: State, context: Abi.Context) -> Activity<Nat>:\n  let written(_) = write {planted: add 1n}\n  0n\n"
        for declared, name in (("record Edits:\n  planted: P.Edit<Nat, Nat>\n", "Edits is"),
                               ("def keep() -> Edits:\n  {planted: P.Edit.keep({})}\n", "keep() is")):
            with self.subTest(declared=name):
                reply = self.send("check-package", DERIVED_HEAD + declared + bump, "bump")
                self.assertEqual(reply["status"], "refused", reply)
                self.assertIn("refused (derived-edits): " + name + " derived from State; delete this declaration",
                              reply["diagnostic"]["message"])

    def test_a_state_named_from_another_module_derives_in_its_own_terms(self):
        # `type State = Lib.State`: the items of Lib's fields are spelled through the import of Lib.
        lib = HEAD + "import ./List.obend as Lists\nimport ./Plan.obend as P\nrecord Exit:\n  label: String\n" \
            "record State:\n  exits: Lists.List<Exit>\n  count: Nat\n  name: String\n"
        package = HEAD + "import ./Abi.obend as Abi\nimport ./List.obend as Lists\nimport ./Plan.obend as P\n" \
            "import ./World.obend as World\nimport ./Lib.obend as Lib\ntype State = Lib.State\n" \
            "def go(state: State, input: {label: String}, context: Abi.Context) -> Activity<Nat>:\n" \
            "  let written(_) = write {exits: append {label: input.label}, count: add 1n, name: set input.label}\n  0n\n"
        written = without_state(package) + ("record Edits:\n  exits: P.Entries<Lib.Exit, Lib.Exit>\n  count: P.Edit<Nat, Nat>\n"
                             "  name: P.Edit<String, {}>\ndef keep() -> Edits:\n"
                             "  {exits: P.Entries.keep({}), count: P.Edit.keep({}), name: P.Edit.keep({})}\n")
        extra = [{"name": "Lib", "source": lib}]
        self.assertEqual(core(self.compiled(package, "go", extra)), core(self.compiled(written, "go", extra)))

    def test_an_item_type_the_module_cannot_name_is_refused_by_name(self):
        inner = HEAD + "record Item:\n  n: Nat\n"
        outer = HEAD + "import ./List.obend as Lists\nimport ./Inner.obend as Inner\ntype Items = Lists.List<Inner.Item>\n"
        package = HEAD + "import ./List.obend as Lists\nimport ./Plan.obend as P\nimport ./Outer.obend as Outer\n" \
            "record State:\n  items: Outer.Items\n"
        reply = self.send("check-package", package, "keep", [{"name": "Inner", "source": inner}, {"name": "Outer", "source": outer}])
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (derived-edits): State.items holds items of a type from a module Package does not import",
                      reply["diagnostic"]["message"])

    def test_write_without_the_plan_library_is_refused_by_name(self):
        source = HEAD + "import ./Abi.obend as Abi\nrecord State:\n  count: Nat\n" \
            "def bump(state: State, context: Abi.Context) -> Activity<Nat>:\n  let written(_) = write {count: add 1n}\n  0n\n"
        reply = self.h.send({"op": "check-package", "entry": "bump",
                             "modules": library_modules("Abi") + [{"name": "Package", "source": source}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (derived-edits): write {...} and keep() derive Edits from State through the Plan library",
                      reply["diagnostic"]["message"])


# A `fixed` State field is set by initial() or a seed only: the derived Edits omits it, the
# artifact lists it, and no write names it.
FIXED_HEAD = DERIVED_HEAD.replace("  note: String\n", "  note: fixed String\n").replace("  owner: P.Reference\n", "  owner: fixed P.Reference\n")
FIXED_PAIR = """record Edits:
  planted: P.Edit<Nat, Nat>
  children: P.Entries<P.Reference, P.Reference>
  names: P.Entries<String, String>
  rows: P.Entries<Row, Row>
  open: P.Edit<Bool, {}>
def keep() -> Edits:
  {planted: P.Edit.keep({}), children: P.Entries.keep({}), names: P.Entries.keep({}), rows: P.Entries.keep({}), open: P.Edit.keep({})}
"""


class FixedFields(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    send = DerivedEdits.send
    compiled = DerivedEdits.compiled

    def test_fixed_fields_are_the_pair_that_omits_them(self):
        for entry in ("plant", "keep", "initial"):
            with self.subTest(entry=entry):
                derived = self.compiled(FIXED_HEAD + DERIVED_REST, entry)
                written = self.compiled(without_state(FIXED_HEAD + DERIVED_REST + FIXED_PAIR), entry)
                self.assertEqual(core(derived), core(written))
                self.assertEqual(derived["fixed"], ["note", "owner"])
        self.assertNotIn("fixed", self.compiled(DERIVED_HEAD + DERIVED_REST, "plant"))

    def test_a_write_naming_a_fixed_field_is_refused_by_name(self):
        for source in (FIXED_HEAD + DERIVED_REST.replace("open: set true}", "open: set true, note: set input.name}"),
                       FIXED_HEAD + DERIVED_REST.replace("let written(_) = write {", "let written(_) = world.write({note: P.Edit.set({value: \"\"})})\n  let again(_) = write {")):
            reply = self.send("check-package", source, "plant")
            self.assertEqual(reply["status"], "refused", reply)
            self.assertIn("refused (fixed): note is fixed; no edit names it", reply["diagnostic"]["message"])

    def test_fixed_fields_follow_layers_and_alias_chains(self):
        # Refuted by an artifact without `fixed` whose effective State has fixed fields: a layer
        # with no State of its own, or a State aliasing an alias of one (review kernel 2).
        base = [{"name": "Base", "source": FIXED_HEAD + DERIVED_REST}]
        layer = ("layer over ./Base.obend\n" + HEAD + "import ./Abi.obend as Abi\n"
                 "def louder(state: Super.State, context: Abi.Context) -> Nat:\n  state.planted + 2n\n")
        for entry in ("plant", "louder"):
            with self.subTest(layer=entry):
                self.assertEqual(self.compiled(layer, entry, base).get("fixed"), ["note", "owner"])
        lib = [{"name": "Lib", "source": FIXED_HEAD + DERIVED_REST + "type Shared = State\n"}]
        aliased = (HEAD + "import ./Lib.obend as Lib\ntype Again = Lib.Shared\ntype State = Again\n"
                   "def initial() -> State:\n  Lib.initial()\n")
        self.assertEqual(self.compiled(aliased, "initial", lib).get("fixed"), ["note", "owner"])

    def test_a_layer_write_naming_an_inherited_fixed_field_is_refused(self):
        base = [{"name": "Base", "source": FIXED_HEAD + DERIVED_REST}]
        layer = ("layer over ./Base.obend\n" + HEAD + "import ./Abi.obend as Abi\nimport ./Plan.obend as P\n"
                 "import ./World.obend as World\n"
                 "def retitle(state: Super.State, input: {}, context: Abi.Context) -> Activity<Nat>:\n"
                 "  let written(_) = world.write::<Super.Edits>({note: P.Edit.set({value: \"\"})})\n  state.planted\n")
        reply = self.send("check-package", layer, "retitle", base)
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (fixed): note is fixed; no edit names it", reply["diagnostic"]["message"])

    def test_only_a_state_field_is_fixed(self):
        source = DERIVED_HEAD.replace("  text: String\n", "  text: fixed String\n") + DERIVED_REST
        reply = self.send("check-package", source, "plant")
        self.assertIn("refused (fixed): only a State field is fixed; text is a field of Row", reply["diagnostic"]["message"])


class Declares(unittest.TestCase):
    """The artifact names the entry module's conventional declarations, derived ones included."""

    def test_declares_lists_derived_and_written_conventions(self):
        h = Host()
        self.addCleanup(h.close)
        derived = h.compile(FORM_STATE + FORM_BLOCKS + "def initial() -> State:\n  {planted: 0n}\n", "plant", ("List", "Form"))
        self.assertEqual(derived["declares"], ["forms", "initial"])
        plain = h.compile(FORM_STATE.replace("PlantInput", "{count: Nat}").replace("WaterInput", "{note: String}"),
                          "plant", ("List", "Form"))
        self.assertEqual(plain["declares"], [])

    def test_a_layer_declares_what_its_stack_declares(self):
        # Refuted by a layer that writes no forms() or initial() declaring neither, though both
        # are inherited from the module below (review kernel 5): the host reads `declares`.
        h = Host()
        self.addCleanup(h.close)
        base = FORM_STATE + FORM_BLOCKS + "def initial() -> State:\n  {planted: 0n}\ndef methods() -> Nat:\n  0n\n"
        layer = "layer over ./Base.obend\n" + HEAD + "def extra(n: Nat) -> Nat:\n  n\n"
        for entry in ("extra", "plant"):
            with self.subTest(entry=entry):
                reply = h.send({"op": "compile", "entry": entry, "modules": library_modules("List", "Form") +
                                [{"name": "Base", "source": base}, {"name": "Package", "source": layer}]})
                self.assertEqual(reply["status"], "compiled", reply)
                self.assertEqual(reply["artifact"]["declares"], ["forms", "methods", "initial"])
