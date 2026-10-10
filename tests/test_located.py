"""Located refusals: every refusal of an elaborated package names the definition, the span
in the source, the expected and found types in surface syntax, and a hint when one applies,
on `check-package` and on `compile` alike.

    python3 -m unittest tests.test_located -v
"""
import json
import unittest

from tests.test_turn import Host, library_modules

HEAD = "edition ObjectiveBend 1\n"

# The objects lane's case: a Reference where text was expected, found by bisecting.
REFERENCE_AS_TEXT = HEAD + """import ./Plan.obend as Plans
record Ctx:
  object: Plans.Reference
  name: String
def label(c: Ctx) -> String:
  textConcat(c.object, "!")
"""
TOO_FEW = HEAD + "def add(a: Nat, b: Nat) -> Nat:\n  a + b\ndef use(n: Nat) -> Nat:\n  add(n)\n"
TOO_MANY = HEAD + "def add(a: Nat, b: Nat) -> Nat:\n  a + b\ndef use(n: Nat) -> Nat:\n  add(n, n, n)\n"
LIGHT = HEAD + "sum Light:\n  on: {}\n  off: {}\n"
UNKNOWN_ARM = LIGHT + "def flip(l: Light) -> Nat:\n  match l:\n    case on(_): 1n\n    case off(_): 0n\n    case dim(_): 2n\n"
UNKNOWN_CASE = LIGHT + "def make(n: Nat) -> Light:\n  Light.dim({})\n"


def text_at(source, span):
    return source.encode()[span["start"]:span["end"]].decode()


class Located(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def refusals(self, source, entry, library=()):
        """The diagnostic of check-package and of compile, which must agree."""
        modules = library_modules(*library) + [{"name": "Package", "source": source}]
        checked = self.h.send({"op": "check-package", "entry": entry, "modules": modules})
        self.assertEqual(checked["status"], "refused", checked)
        compiled = self.h.send({"op": "compile", "entry": entry, "modules": modules})
        self.assertEqual(compiled["status"], "error", compiled)
        self.assertEqual(json.loads(compiled["message"]), checked["diagnostic"])
        return checked["diagnostic"]

    def test_a_reference_passed_as_text_names_the_operand_its_type_and_the_field(self):
        d = self.refusals(REFERENCE_AS_TEXT, "label", ["Plan"])
        self.assertEqual(d["stage"], "objective-typed-check")
        self.assertEqual((d["module"], d["definition"], d["span"]["line"]), ("Package", "Package.label", 7))
        self.assertEqual(text_at(REFERENCE_AS_TEXT, d["span"]), "c.object")
        self.assertEqual((d["expected"], d["found"]), ("String", "Plans.Reference"))
        self.assertIn("textConcat", d["message"])
        self.assertIn("`object`", d["hint"])

    def test_wrong_arity_names_the_call(self):
        few = self.refusals(TOO_FEW, "use")
        self.assertEqual((few["definition"], few["span"]["line"]), ("Package.use", 5))
        self.assertEqual(text_at(TOO_FEW, few["span"]), "add(n)")
        self.assertEqual((few["expected"], few["found"]), ("Nat", "(Nat) -> Nat"))
        self.assertIn("waiting for 1 more argument", few["hint"])
        many = self.refusals(TOO_MANY, "use")
        self.assertEqual(text_at(TOO_MANY, many["span"]), "add(n, n, n)")
        self.assertEqual(many["found"], "Nat")
        self.assertIn("more arguments than its function takes", many["hint"])

    def test_an_arm_or_case_that_does_not_exist_is_named_where_it_is_written(self):
        arm = self.refusals(UNKNOWN_ARM, "flip")
        self.assertEqual((arm["definition"], arm["span"]["line"]), ("Package.flip", 9))
        self.assertEqual((arm["expected"], arm["found"]), ("(on | off)", "dim"))
        self.assertIn("on, off", arm["hint"])
        case = self.refusals(UNKNOWN_CASE, "make")
        self.assertEqual((case["definition"], case["span"]["line"]), ("Package.make", 6))
        self.assertEqual(text_at(UNKNOWN_CASE, case["span"]), "Light.dim({})")
        self.assertEqual((case["expected"], case["found"]), ("Light (on | off)", "dim"))
        self.assertIn("on, off", case["hint"])


if __name__ == "__main__":
    unittest.main()
