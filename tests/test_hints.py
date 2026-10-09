"""Dialect hints: a refused package names the pseudo-Bend habit behind the
refusal and states the real form, beside stage/message/module/span. A hint
never changes what is accepted.

    python3 -m unittest tests.test_hints -v
"""
import json
import unittest

from tests.test_objects import closure
from tests.test_turn import Host

HEAD = "edition ObjectiveBend 1\n"
PAIR = "record Item:\n  id: Nat\n"

CASES = [
    ("untyped closure", HEAD + PAIR + "def keep(id: Nat) -> Bool:\n  fn(t) t.id != id\n", "keep",
     "closures are `fn(x: T) -> U: body`"),
    ("Maybe builtin", HEAD + "def find(n: Nat) -> Maybe<Nat>:\n  n\n", "find",
     "there is no Maybe builtin"),
    ("halt", HEAD + "def stop(n: Nat) -> Nat:\n  halt(\"no\")\n", "stop",
     "there is no halt"),
    ("Some/None", HEAD + "def wrap(n: Nat) -> Nat:\n  Some(n)\n", "wrap",
     "there is no Some/None"),
    ("arrow arms", HEAD + "sum Light:\n  on: {}\n  off: {}\ndef flip(l: Light) -> Nat:\n  match l:\n    on(_) -> 1n\n    off(_) -> 0n\n",
     "flip", "match arms are `case label(x): body`"),
    ("record with bars", HEAD + "record Shape: Circle {r: Nat} | Square {s: Nat}\ndef one(n: Nat) -> Nat:\n  n\n",
     "one", "a sum is declared with `sum Name:`"),
    ("law match", HEAD + "law owner: match request.action:\ndef one(n: Nat) -> Nat:\n  n\n", "one",
     "laws are one line over request facts, not a match"),
    ("list literal", HEAD + "def one(n: Nat) -> Nat:\n  [n]\n", "one",
     "there are no list literals"),
    ("untyped def", HEAD + "def one(n):\n  n\n", "one",
     "definitions are `def name(x: T) -> U:`"),
    ("slash comment", HEAD + "// the counter\ndef one(n: Nat) -> Nat:\n  n\n", "one",
     "comments start with `#`"),
]

CORRECT = HEAD + """sum Light:
  on: {}
  off: {}
# a correct program
def flip(l: Light) -> Nat:
  match l:
    case on(_): 1n
    case off(_): 0n
"""


# A module that uses the library's declared `Lists.Maybe<T>` beside an unrelated mistake.
QUALIFIED_MAYBE = HEAD + """import ./List.obend as Lists
def pick(n: Nat) -> Lists.Maybe<Nat>:
  Lists.Maybe::<Nat>.none({})
"""
UNRELATED = {
    "typed-packet refusal": QUALIFIED_MAYBE + "def bad(n: Nat) -> Bool:\n  n + 1n\n",
    "multi-line if": QUALIFIED_MAYBE + "def bad(n: Nat) -> Nat:\n  if n == 0n\n    then 1n else 2n\n",
    "unbalanced parenthesis": QUALIFIED_MAYBE + "def bad(n: Nat) -> Nat:\n  (n + 1n\n",
}


class HintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def check(self, source, entry):
        return self.h.send({"op": "check-package", "entry": entry,
                            "modules": [{"name": "Package", "source": source}]})

    def test_each_dialect_habit_yields_its_hint(self):
        for name, source, entry, hint in CASES:
            with self.subTest(habit=name):
                reply = self.check(source, entry)
                self.assertEqual(reply["status"], "refused", reply)
                self.assertIn("hint", reply["diagnostic"], reply)
                self.assertIn(hint, reply["diagnostic"]["hint"])

    def test_compile_carries_the_hint_in_its_diagnostic(self):
        name, source, entry, hint = CASES[4]
        reply = self.h.send({"op": "compile", "entry": entry, "modules": [{"name": "Package", "source": source}]})
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn(hint, json.loads(reply["message"])["hint"])

    def test_a_correct_program_has_no_hint(self):
        reply = self.check(CORRECT, "flip")
        self.assertEqual(reply["status"], "checked", reply)
        self.assertNotIn("hint", json.dumps(reply))

    def test_a_plain_type_error_has_no_hint(self):
        reply = self.check(HEAD + "def one(n: Nat) -> Bool:\n  n\n", "one")
        self.assertEqual(reply["status"], "refused", reply)
        self.assertNotIn("hint", reply["diagnostic"])

    def test_a_hint_fires_only_where_its_trigger_is(self):
        for name, source in UNRELATED.items():
            with self.subTest(refusal=name):
                reply = self.h.send({"op": "check-package", "entry": "bad",
                                     "modules": closure("List") + [{"name": "Probe", "source": source}]})
                self.assertEqual(reply["status"], "refused", reply)
                self.assertNotIn("hint", reply["diagnostic"], reply)
                if name == "unbalanced parenthesis":
                    self.assertEqual(reply["diagnostic"]["stage"], "objective-source-parse", reply)
        reply = self.h.send({"op": "check-package", "entry": "bad",
                             "modules": closure("List") + [{"name": "Probe", "source": UNRELATED["typed-packet refusal"]}]})
        self.assertEqual(reply["diagnostic"]["stage"], "objective-typed-check", reply)


if __name__ == "__main__":
    unittest.main()
