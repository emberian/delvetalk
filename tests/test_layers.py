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

# Review 2026-10-12 kernel 5 and 8: a stack elsewhere in the closure is not an entry's own, and a
# layer keeps the clauses of the package it extends.
STATE_BASE = """edition ObjectiveBend 1
record State:
  n: Nat
law grows "n never falls": new.n >= old.n
def initial() -> State:
  {n: 0n}
def poke(state: State, input: {}) -> Nat:
  state.n
def render(state: State) -> String:
  "base"
"""
STATE_LAYER = """layer over ./Base.obend
edition ObjectiveBend 1
type State = Super.State
law small "n stays small": new.n <= 9
def render(state: State) -> String:
  "layer"
"""
COUNTER = """edition ObjectiveBend 1
import ./Layer.obend as L
record State:
  count: Nat
def initial() -> State:
  {count: 0n}
def bump(state: State, input: {}) -> Nat:
  state.count + 1n
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
        self.assertIn("write def render(state: State, context: Abi.Context) -> Document.Document", d["hint"])  # as Bell writes it
        late = "edition ObjectiveBend 1\nlayer over ./Base.obend\ndef greet(n: Nat) -> String:\n  \"x\"\n"
        reply = self.h.send({"op": "check-package", "entry": "greet",
                             "modules": [{"name": "Base", "source": BASE}, {"name": "Top", "source": late}]})
        self.assertEqual(reply["status"], "refused", reply)
        self.assertIn("first line", reply["diagnostic"]["message"])

    def test_an_entry_beside_a_stack_takes_its_own_methods_and_entries(self):
        # Refuted if Counter's artifact lists Base's poke and loses its own bump, or a definition
        # Counter lacks is taken from the stack it merely imports.
        lawless = lambda text: "".join(l + "\n" for l in text.splitlines() if not l.startswith("law "))
        modules = [{"name": "Base", "source": lawless(STATE_BASE)}, {"name": "Layer", "source": lawless(STATE_LAYER)},
                   {"name": "Counter", "source": COUNTER}]
        art = self.compile(modules, "initial")
        self.assertEqual([m["name"] for m in art["methods"]], ["bump"])
        self.assertEqual(art["declares"], ["initial"])
        self.assertNotIn("laws", art)
        reply = self.h.send({"op": "compile", "entry": "poke", "modules": modules})
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("missing selected entry", reply["message"])
        # A clause of a module the entry only imports is still refused.
        modules[0] = {"name": "Base", "source": STATE_BASE}
        reply = self.h.send({"op": "compile", "entry": "initial", "modules": modules})
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("Base is imported and declares 1 clause(s)", reply["message"])

    def test_a_layer_keeps_the_clauses_of_the_package_below_it(self):
        # Refuted if layering over a package with top-level clauses is refused, or its clauses dropped.
        ruled = STATE_BASE.replace('law grows "n never falls": new.n >= old.n',
                                   "rule ring: new.n >= 1 then delvetalk me note / text: rung")
        plain = "".join(l + "\n" for l in STATE_LAYER.splitlines() if not l.startswith("law "))
        art = self.compile([{"name": "Base", "source": ruled}, {"name": "Layer", "source": plain}], "render")
        self.assertEqual([m["name"] for m in art["methods"]], ["render", "poke"])
        # The base's law comes along: the pure profile then refuses the package for having laws at all.
        reply = self.h.send({"op": "compile", "entry": "render",
                             "modules": [{"name": "Base", "source": STATE_BASE}, {"name": "Layer", "source": plain}]})
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("package laws require a host law adapter", reply["message"])
        # A layer adds clauses; one of a name below it is refused, never an override.
        clash = plain + "rule ring: new.n >= 2 then delvetalk me note / text: again\n"
        reply = self.h.send({"op": "compile", "entry": "render",
                             "modules": [{"name": "Base", "source": ruled}, {"name": "Layer", "source": clash}]})
        self.assertEqual(reply["status"], "error", reply)
        self.assertIn("`ring` twice", reply["message"])

if __name__ == "__main__":
    unittest.main()
