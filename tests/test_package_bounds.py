"""A package at the program bound compiles, and every bound a package meets refuses by name
(KERNEL-HANDOFF §4; lane/kernel13). `Bounds.maxPackageBytes` (128 KiB) is the source of one
module offered as a program; a module of that size must meet no other kernel bound (generic
instances, expansion nodes, row width) on its way to a packet. `Generics.maxInstances` (1,024)
is the generic instances one package specializes; past it the refusal names the count, the
bound and the module and declaration that asked for the next one.

    python3 -W ignore -m tests.run tests.test_package_bounds
"""
import json
import unittest

from tests import host
from tests.test_objects import closure

MAX_PACKAGE_BYTES = 131072  # Delvetalk.Bounds.maxPackageBytes
MAX_MODULE_BYTES = 524288  # Delvetalk.Bounds.maxModuleBytes
MAX_INSTANCES = 1024  # Delvetalk.Generics.maxInstances


def program(size):
    """One entry module of about `size` bytes over List.obend: distinct records and functions,
    each over a shared list type, and `main` reaching every tenth."""
    lines = ["edition ObjectiveBend 1", "import ./List.obend as Lists"]
    i = 0
    while len("\n".join(lines).encode()) + 8 * i < size - 400:
        lines += [f"record P{i}:", "  n: Nat", "  s: String",
                  f"def f{i}(p: P{i}, xs: Lists.List<String>) -> String:",
                  f"  if p.n == 0n then p.s else \"{{p.s}} and {{natText(Lists.length(xs) + {i}n)}}\""]
        i += 1
    reach = " + ".join(f"textLength(f{j}({{n: {j}n, s: \"x\"}}, Lists.List.nil({{}})))" for j in range(0, i, 10))
    lines += ["def main() -> Nat:", "  " + reach]
    text = "\n".join(lines) + "\n"
    return text + "#" + "." * (size - len(text.encode()) - 2) + "\n"


def instances(rows):
    """About eleven generic instances per row type: Relation insert, count, retract and rows."""
    src = ["edition ObjectiveBend 1", "import ./List.obend as Lists", "import ./Relation.obend as Relations"]
    for i in range(rows):
        src += [f"record R{i}:", "  a: Nat", "  b: String", f"def use{i}() -> Nat:",
                f"  Relations.count::<R{i}>(Relations.insert::<R{i}, Nat>(Relations.empty::<R{i}>(), "
                f"{{a: {i}n, b: \"x\"}}, fn(x: R{i}) -> Nat: x.a)) + Lists.length::<R{i}>(Relations.rows::<R{i}>("
                f"Relations.retract::<R{i}, Nat>(Relations.empty::<R{i}>(), 1n, fn(x: R{i}) -> Nat: x.a)))"]

    def tree(lo, hi):
        return f"use{lo}()" if hi - lo == 1 else f"({tree(lo, (lo + hi) // 2)} + {tree((lo + hi) // 2, hi)})"
    src += ["def all() -> Nat:", "  " + tree(0, rows)]
    return closure("Relation") + [{"name": "Many", "source": "\n".join(src) + "\n"}]


class PackageBound(unittest.TestCase):
    def test_a_module_at_the_program_bound_compiles(self):
        source = program(MAX_PACKAGE_BYTES)
        self.assertEqual(len(source.encode()), MAX_PACKAGE_BYTES)
        modules = closure("List") + [{"name": "Big", "source": source}]
        checked = host.check({"op": "check-package", "modules": modules, "entry": "main"})
        self.assertEqual(checked["status"], "checked", json.dumps(checked)[:400])
        run = host.check({"op": "run", "artifact": host.check({"op": "compile", "modules": modules, "entry": "main"})["artifact"],
                          "arguments": [], "limits": {"ticks": 1000000}})
        self.assertEqual(run["status"], "finished", json.dumps(run)[:400])

    def test_a_module_past_the_module_bound_is_refused_by_name(self):
        reply = host.check({"op": "check-package", "entry": "main",
                            "modules": [{"name": "Huge", "source": "# " + "x" * MAX_MODULE_BYTES + "\n"}]})
        self.assertEqual(reply["status"], "refused")
        self.assertIn(f"module Huge exceeds maxModuleBytes ({MAX_MODULE_BYTES} bytes)", reply["diagnostic"]["message"])

    def test_an_import_scan_past_the_package_bound_is_refused_by_name(self):
        modules = [{"name": f"M{i}", "source": "# " + "x" * (MAX_MODULE_BYTES - 16) + "\n"} for i in range(3)]
        reply = host.check({"op": "source-imports-v1", "modules": modules})
        self.assertEqual(reply["status"], "error")
        self.assertIn("exceeds maxPackageSourceBytes (1048576 bytes)", reply["message"])


class InstanceBound(unittest.TestCase):
    def test_a_closure_of_a_thousand_instances_compiles(self):
        modules = instances(92)
        checked = host.check({"op": "check-package", "modules": modules, "entry": "all"})
        self.assertEqual(checked["status"], "checked", json.dumps(checked)[:400])
        count = len(checked["artifact"]["genericInstances"])
        self.assertGreater(count, 1000)
        self.assertLessEqual(count, MAX_INSTANCES)

    def test_past_the_bound_the_refusal_names_count_bound_and_module(self):
        reply = host.check({"op": "check-package", "modules": instances(100), "entry": "all"})
        self.assertEqual(reply["status"], "refused")
        d = reply["diagnostic"]
        self.assertEqual(d["stage"], "source-specialization")
        self.assertIn(f"refused (generic-instances): the package needs more than {MAX_INSTANCES} generic instances",
                      d["message"])
        self.assertIn("Many.use", d["message"])
        self.assertEqual(d.get("module"), "Many")
        self.assertIn("line", d.get("span", {}))


if __name__ == "__main__":
    unittest.main()
