"""Surface sugar without new semantics: each sugared form compiles to the packet of
its explicit spelling. A packet names its modules' source hashes (`sourceModules`),
so two spellings are compared on the packet without that one field; everything else
(term, annotations, types, bounds, entry) must be byte-identical.

    python3 -m unittest tests.test_sugar -v
"""
import hashlib
import json
import unittest

from tests.test_turn import BINDING, Host, library_modules, nat, variant
from tests.test_turn_world import TurnWorld, label, record

HEAD = "edition ObjectiveBend 1\n"


def core(artifact):
    """The packet's digest without its source hashes."""
    packet = dict(artifact["packet"])
    packet.pop("sourceModules")
    return hashlib.sha256(json.dumps(packet, sort_keys=True).encode()).hexdigest()


# A generic declaration in every package, so both spellings run the generics pass (an
# explicit `Data.of::<T>` is a specialization, and the pass adds its generated module
# to the package's metadata).
DATA_PLANS = HEAD + """sum Box<T>:
  box: {value: T}
record Reference:
  world: String
  object: String
sum Plan:
  send: {object: Reference, method: String, argument: Data}
sum Response:
  delivery: {id: String}
  refused: {clause: String}
record Note:
  text: String
  count: Nat
"""

# (name, explicit, sugared, entry): each pair must compile to the same packet.
DATA_PAIRS = [
    ("sum payload field",
     DATA_PLANS + "def tell(text: String) -> Activity<Plan, Response, Nat>:\n"
     "  match perform(Plan.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: Data.of::<{text: String}>({text: text})})):\n"
     "    case _: 1n\n",
     DATA_PLANS + "def tell(text: String) -> Activity<Plan, Response, Nat>:\n"
     "  match perform(Plan.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: {text: text}})):\n"
     "    case _: 1n\n",
     "tell"),
    ("named record value",
     DATA_PLANS + "def tell(note: Note) -> Activity<Plan, Response, Nat>:\n"
     "  match perform(Plan.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: Data.of::<Note>(note)})):\n"
     "    case _: note.count\n",
     DATA_PLANS + "def tell(note: Note) -> Activity<Plan, Response, Nat>:\n"
     "  match perform(Plan.send({object: {world: \"\", object: \"bell\"}, method: \"note\", argument: note})):\n"
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
record Rain:
  author: String
  text: String
record State:
  rains: Lists.List<Rain>
  count: Nat
sum Plan:
  write: {count: Nat}
sum Response:
  written: {}
  refused: {clause: String}
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
     LISTS_HEAD + "def wrote<T>(state: State, then: Nat -> T) -> Activity<Plan, Response, T>:\n"
     "  match perform(Plan.write({count: state.count + 1n})):\n    case _: then(state.count)\n"
     "def bump(state: State, n: Nat) -> Activity<Plan, Response, Nat>:\n"
     "  wrote::<Nat>(state, fn(c: Nat) -> Nat: c + n)\n",
     LISTS_HEAD + "def wrote<T>(state: State, then: Nat -> T) -> Activity<Plan, Response, T>:\n"
     "  match perform(Plan.write({count: state.count + 1n})):\n    case _: then(state.count)\n"
     "def bump(state: State, n: Nat) -> Activity<Plan, Response, Nat>:\n"
     "  wrote(state, fn(c: Nat) -> Nat: c + n)\n",
     "bump"),
    ("inside a generic body",
     LISTS_HEAD + "def twice<T>(items: Lists.List<T>) -> Nat:\n  Lists.length::<T>(items) + Lists.length::<T>(items)\n"
     "def f(state: State) -> Nat:\n  twice::<Rain>(state.rains)\n",
     LISTS_HEAD + "def twice<T>(items: Lists.List<T>) -> Nat:\n  Lists.length(items) + Lists.length(items)\n"
     "def f(state: State) -> Nat:\n  twice(state.rains)\n",
     "f"),
]


TURN_HEAD = HEAD + """record Edit:
  field: Nat
  after: Nat
sum Plan:
  write: Edit
sum Reply:
  written: {}
  refused: {clause: String}
  later: {}
"""

BUMP_SUGARED = TURN_HEAD + """def bump(count: Nat) -> Activity<Plan, Reply, Nat>:
  let written(_) = perform(Plan.write({field: 0n, after: count + 1n}))
  let next = count + 1n
  next
"""
# The match the statement lowers to: one refusal arm per label it does not name.
BUMP_EXPLICIT = TURN_HEAD + """def bump(count: Nat) -> Activity<Plan, Reply, Nat>:
  match perform(Plan.write({field: 0n, after: count + 1n})):
    case written(_):
      let next = count + 1n
      next
    case refused(_): refuse("unexpected response refused")
    case later(_): refuse("unexpected response later")
"""

# Two statements in a row, the second binding its payload.
TWICE_SUGARED = TURN_HEAD + """def twice(count: Nat) -> Activity<Plan, Reply, String>:
  let written(_) = perform(Plan.write({field: 0n, after: count}))
  let refused(r) = perform(Plan.write({field: 1n, after: count}))
  r.clause
"""
TWICE_EXPLICIT = TURN_HEAD + """def twice(count: Nat) -> Activity<Plan, Reply, String>:
  match perform(Plan.write({field: 0n, after: count})):
    case written(_):
      match perform(Plan.write({field: 1n, after: count})):
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
        return self.h.compile(source, entry, library)

    def check(self, source, entry, library=()):
        return self.h.send({"op": "check-package", "entry": entry,
                            "modules": library_modules(*library) + [{"name": "Package", "source": source}]})

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
        source = DATA_PLANS + ("def go(n: Nat) -> Activity<Plan, Response, Nat>:\n"
                               "  match perform(Plan.send({object: {world: \"\", object: \"b\"}, method: \"m\", argument: {}})):\n"
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
        self.assertIn("cannot infer the type argument T of Lists.length (line 17)", message)
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

    def test_let_response_takes_a_perform(self):
        source = TURN_HEAD + ("def pick(reply: Reply) -> Activity<Plan, Reply, Nat>:\n"
                              "  let written(_) = reply\n  1n\n")
        reply = self.check(source, "pick")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (let-response)", reply["diagnostic"]["message"])

    def test_refuse_stands_only_where_an_activity_finishes(self):
        pure = TURN_HEAD + "def f(n: Nat) -> Nat:\n  refuse(\"no\")\n"
        reply = self.check(pure, "f")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (refuse-outside-activity)", reply["diagnostic"]["message"])
        nested = TURN_HEAD + ("def g(n: Nat) -> Activity<Plan, Reply, Nat>:\n"
                              "  if refuse(\"no\") then n else 0n\n")
        reply = self.check(nested, "g")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("refused (refuse-outside-tail)", reply["diagnostic"]["message"])
        # In both branches of a tail `if`, it is where the activity finishes.
        branches = TURN_HEAD + ("def h(n: Nat) -> Activity<Plan, Reply, Nat>:\n"
                                "  if n == 0n then refuse(\"zero\") else n\n")
        artifact = self.compile(branches, "h")
        self.assertEqual(self.h.start(artifact, [nat(0)])["message"], "turn refused: zero")
        self.assertEqual(self.h.start(artifact, [nat(3)])["value"], nat(3))

    def test_halt_suggests_the_statement(self):
        reply = self.check(HEAD + "def stop(n: Nat) -> Nat:\n  halt(\"no\")\n", "stop")
        self.assertIn("let written(_) = perform(Plan.write({...}))", reply["diagnostic"]["hint"])


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
"""
FORM_SUGARED = FORM_HEAD + """form plant as planting:
  colour: amber | violet | silver
  seed: text 1..80
  count: natural 1..1000n
"""


GARDEN = HEAD + """import ./Abi.obend as Abi
import ./List.obend as Lists
import ./Plan.obend as P
record State:
  planted: Nat
  children: Lists.List<P.Reference>
  note: String
record Edits:
  planted: P.Edit<Nat, Nat>
  children: P.Entries<P.Reference, {}>
  note: P.Edit<String, {}>
type Plan = P.Plan<Edits>
type Response = P.Response<State, {}>
def keep() -> Edits:
  {planted: P.Edit::<Nat, Nat>.keep({}), children: P.Entries::<P.Reference, {}>.keep({}), note: P.Edit::<String, {}>.keep({})}
def plant(state: State, input: {child: P.Reference, note: String}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
"""
WRITE_EXPLICIT = GARDEN + """  let written(_) = perform(Plan.write({object: P.self(context), edits: extend(keep(), {planted: P.Edit::<Nat, Nat>.add({delta: 1n}), children: P.Entries::<P.Reference, {}>.append({item: input.child}), note: P.Edit::<String, {}>.set({value: input.note})})}))
  state.planted + 1n
"""
WRITE_SUGARED = GARDEN + """  let written(_) = perform(write {planted: add 1n, children: append input.child, note: set input.note})
  state.planted + 1n
"""


COUNTER = HEAD + """import ./Abi.obend as Abi
import ./Plan.obend as Plans
record State:
  count: Nat
record Edits:
  count: Plans.Edit<Nat, Nat>
type Plan = Plans.Plan<Edits>
type Response = Plans.Response<State, {}>
law small "a counter stays at most a hundred": new.count <= 100
def initial() -> State:
  {count: 0n}
def bump(state: State, input: {n: Nat}, context: Abi.Context) -> Activity<Plan, Response, Nat>:
  let written(_) = perform(Plan.write({object: Plans.self(context), edits: {count: Plans.Edit.add({delta: input.n})}}))
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

    def test_a_form_block_needs_the_form_library_and_known_kinds(self):
        reply = self.check(HEAD + "form plant:\n  seed: text 1..80\n", "plantForm")
        self.assertIn("a form block needs the Form library", reply["diagnostic"]["message"])
        reply = self.check(FORM_HEAD + "form plant:\n  seed: words 1..80\n", "plantForm")
        self.assertIn("a form field is `name: text MIN..MAX`", reply["diagnostic"]["message"])


class Writes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def test_write_is_its_plan(self):
        a = self.h.compile(WRITE_EXPLICIT, "plant", ("Abi", "List", "Plan"))
        b = self.h.compile(WRITE_SUGARED, "plant", ("Abi", "List", "Plan"))
        self.assertEqual(core(a), core(b))

    def test_write_names_its_operations(self):
        source = WRITE_SUGARED.replace("add 1n", "bump 1n")
        reply = self.h.send({"op": "check-package", "entry": "plant",
                             "modules": library_modules("Abi", "List", "Plan") + [{"name": "Package", "source": source}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("takes add, set, append, remove, removeItem, insert, upsert or retract, not bump", reply["diagnostic"]["message"])


    def test_relation_edits_are_their_plans(self):
        # RELATIONAL section 3: insert/upsert/retract, against a Plan library that has them.
        plan = [m for m in library_modules("Abi", "List", "Plan") if m["name"] == "Plan"][0]["source"]
        plan = plan.replace("  removeItem: {item: D}\n",
                            "  removeItem: {item: D}\n  insert: {row: D}\n  upsert: {row: D}\n  retract: {key: Data}\n")
        modules = [m if m["name"] != "Plan" else {"name": "Plan", "source": plan}
                   for m in library_modules("Abi", "List", "Plan")]
        for op, ctor, payload, value in [("insert", "insert", "row", "input.child"),
                                         ("upsert", "upsert", "row", "input.child"),
                                         ("retract", "retract", "key", "{object: input.note}")]:
            with self.subTest(op=op):
                sugared = GARDEN + "  let written(_) = perform(write {children: %s %s})\n  state.planted\n" % (op, value)
                explicit = GARDEN + ("  let written(_) = perform(Plan.write({object: P.self(context), edits: extend(keep(), "
                                     "{children: P.Entries::<P.Reference, {}>.%s({%s: %s})})}))\n  state.planted\n" % (ctor, payload, value))
                packets = []
                for source in (sugared, explicit):
                    reply = self.h.send({"op": "compile", "entry": "plant",
                                         "modules": modules + [{"name": "Package", "source": source}]})
                    self.assertEqual(reply["status"], "compiled", reply)
                    packets.append(core(reply["artifact"]))
                self.assertEqual(packets[0], packets[1])


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
        self.assertEqual(art["relations"], [{"field": "rains", "key": ["author", "at"]}])
        plain = h.compile(RELATIONS.replace("def relations()", "def declared()"), "initial", ("List",))
        self.assertNotIn("relations", plain)


class LawReading(TurnWorld):
    """A law's reading is carried beside it; the law enforces exactly as without one, and
    the statement form runs on the real host (a staged write is answered `written`)."""

    def test_a_law_with_a_reading_enforces_as_before(self):
        self.create("c", library_modules("Abi", "Plan") + [{"name": "Package", "source": COUNTER}], 0)
        ok = self.turn("c", "bump", record(n=nat(5)))
        self.assertEqual(ok["status"], "admitted", ok)
        refused = self.turn("c", "bump", record(n=nat(150)))
        self.assertEqual(refused["status"], "refused", refused)
        self.assertEqual(refused["receipt"]["outcome"].get("clause"), "small", refused)

    def test_write_runs_on_the_host(self):
        source = WRITE_SUGARED + "def initial() -> State:\n  {planted: 0n, children: Lists.List.nil({}), note: \"\"}\n"
        r = self.host.send(op="world-create", principal="ember", identity="create-g", object="g",
                           modules=library_modules("Abi", "List", "Plan") + [{"name": "Package", "source": source}],
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
                        "modules": library_modules("Abi", "Plan") + [{"name": "Package", "source": bad}]})
        self.assertEqual(reply["status"], "refused", reply)


if __name__ == "__main__":
    unittest.main()
