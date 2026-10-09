"""Surface sugar without new semantics: each sugared form compiles to the packet of
its explicit spelling. A packet names its modules' source hashes (`sourceModules`),
so two spellings are compared on the packet without that one field; everything else
(term, annotations, types, bounds, entry) must be byte-identical.

    python3 -m unittest tests.test_sugar -v
"""
import hashlib
import json
import unittest

from tests.test_turn import Host, library_modules

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
        # kept<T, U>(found: Maybe<U>, rest: List<U>) never mentions T.
        source = LISTS_HEAD + "def pick(state: State) -> Lists.List<Rain>:\n  Lists.kept(Lists.Maybe.none({}), state.rains)\n"
        reply = self.check(source, "pick", ("List",))
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("cannot infer the type argument T of Lists.kept", reply["diagnostic"]["message"])
        self.assertIn("write Lists.kept::<T, Rain>(...) naming T", reply["diagnostic"]["message"])

if __name__ == "__main__":
    unittest.main()
