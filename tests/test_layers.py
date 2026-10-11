"""A layer module overrides the definitions below it for every caller in the package, Super reaches
the version below, and an override keeps its type.

Evidence for FOUNDATION §8 extend (layer: kernel).

Layer stacks (KERNEL-HANDOFF section 13): a module whose first line is
`layer over ./X.obend` overrides X's definitions for every caller in the object, its own
`Super.f` reaching the version below; an override keeps its type; the method table lists
the whole stack; an unlayered package compiles exactly as before
(`tests.test_artifact_pins` keeps its fixture).

    python3 -m unittest tests.test_layers -v
"""
import unittest

from tests.test_turn import Host
from tests.wire import label
from tests.bend import closure, pure

LOUDER = """layer over ./Bell.obend
edition ObjectiveBend 1
import ./Abi.obend as Abi
import ./Document.obend as Document
type State = Super.State
def render(state: State, context: Abi.Context) -> Document.Document:
  Document.concat(Document.text("LOUDER\\n"), Super.render(state, context))
def loud(context: Abi.Context) -> String:
  Document.plain(render(Super.initial(), context))
"""

RETYPED = """layer over ./Bell.obend
edition ObjectiveBend 1
import ./Abi.obend as Abi
type State = Super.State
def render(state: State, context: Abi.Context) -> String:
  "quiet"
"""

BASE = """edition ObjectiveBend 1
def greet(n: Nat) -> String:
  "hi"
def hello(n: Nat) -> String:
  textConcat(greet(n), "!")
"""
TOP = """layer over ./Base.obend
edition ObjectiveBend 1
def greet(n: Nat) -> String:
  textConcat("HI ", Super.greet(n))
"""
TOPMOST = """layer over ./Top.obend
edition ObjectiveBend 1
def greet(n: Nat) -> String:
  textConcat("<", textConcat(Super.greet(n), ">"))
"""


def message(plan):
    """A world call's fields (World.Message: object, method, argument)."""
    return {f["name"]: f["value"] for f in plan["fields"]}


class Layers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.h = Host()

    @classmethod
    def tearDownClass(cls):
        cls.h.close()

    def compile(self, modules, entry):
        reply = self.h.send({"op": "compile", "entry": entry, "modules": modules})
        self.assertEqual(reply["status"], "compiled", reply)
        return reply["artifact"]

    def run_(self, modules, entry, arguments):
        reply = self.h.send({"op": "run", "artifact": self.compile(modules, entry), "arguments": arguments})
        self.assertEqual(reply["status"], "finished", reply)
        return reply["value"]

    def test_a_base_call_sees_the_override_and_super_the_version_below(self):
        # Refuted if `hello` (in Base) still calls Base's own `greet`, or `Super.greet` loops.
        stack = [{"name": "Base", "source": BASE}, {"name": "Top", "source": TOP}]
        self.assertEqual(self.run_(stack, "hello", [{"tag": "natural", "value": "1"}]), label("HI hi!"))
        three = stack + [{"name": "Topmost", "source": TOPMOST}]
        self.assertEqual(self.run_(three, "hello", [{"tag": "natural", "value": "1"}]), label("<HI hi>!"))
        # Without a layer line the same modules are only imports: Base keeps its own greet.
        plain = [{"name": "Base", "source": BASE},
                 {"name": "Top", "source": TOP.replace("layer over ./Base.obend\n", "") +
                  "import ./Base.obend as Super\ndef relay(n: Nat) -> String:\n  Super.hello(n)\n"}]
        self.assertEqual(self.run_(plain, "relay", [{"tag": "natural", "value": "1"}]), label("hi!"))


    def test_a_retyping_override_and_a_late_layer_line_are_refused_by_name(self):
        modules = pure(closure("Bell")) + [{"name": "Retyped", "source": RETYPED}]
        reply = self.h.send({"op": "check-package", "entry": "render", "modules": modules})
        self.assertEqual(reply["status"], "refused", reply)
        d = reply["diagnostic"]
        self.assertIn("refused (layer-override): Retyped.render", d["message"])
        self.assertEqual((d["module"], d["span"]["line"]), ("Retyped", 6))
        self.assertTrue(d["found"].endswith("-> String"), d)
        self.assertIn("signature of Bell.render", d["hint"])
        late = "edition ObjectiveBend 1\nlayer over ./Base.obend\ndef greet(n: Nat) -> String:\n  \"x\"\n"
        reply = self.h.send({"op": "check-package", "entry": "greet",
                             "modules": [{"name": "Base", "source": BASE}, {"name": "Top", "source": late}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("first line", reply["diagnostic"]["message"])


if __name__ == "__main__":
    unittest.main()
