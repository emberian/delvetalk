"""The tariff charges what a workload costs before it allocates or spins: big naturals, results and
Plans by their canonical bytes, text equality by the bytes compared, a failed prefix scan by its scan.

Evidence for FOUNDATION §2 Limits (layer: kernel).

    python3 -m unittest tests.test_tariff -v

Conformance compares values, never costs: these are the charges a workload cannot dodge (review
kernel 7-10): a natural past a machine word, a result's canonical size, text equality, a failed
prefix scan. Workloads over world library code are bounded where that code is tested, never here.
"""
import unittest

from tests.test_turn import Host, nat
from tests.test_objects import run_pure

BIG = {"ticks": "1000000"}


SQUARES = """edition ObjectiveBend 1
def squared(n: Nat, k: Nat) -> Nat:
  match k:
    case 0: n
    case 1+p: squared(n * n, p)
def big(k: Nat) -> Bool:
  5n < squared(2n, k)
def sum(k: Nat) -> Bool:
  5n < squared(2n, k) + squared(3n, k)
"""


class NaturalArithmetic(unittest.TestCase):
    """A natural past a machine word is charged by its operands' bytes before the result is
    built: ticks linear in the operands (word products for multiply, divide and modulo) and
    the result's bytes reserved against the byte budget."""

    def test_repeated_squaring_is_refused_before_it_allocates(self):
        # Thirty squarings of 2 is 2^(2^30), a 128 MiB natural; forty would be 128 GiB.
        # Each squaring once cost one tick and reserved nothing.
        for k in (30, 40):
            ran = run_pure("Document", "big", nat(k), probe=SQUARES, limits=BIG)
            self.assertEqual(ran["status"], "refused", ran)
            self.assertLessEqual(ran["ticksUsed"], 1000000)


VALUES = """edition ObjectiveBend 1
import ./List.obend as Lists
import ./World.obend as World
def yes(n: Nat) -> Bool:
  0n < n
def word(n: Nat) -> String:
  textTake("abcdefghijklmnopqrstuvwxyz", n)
def big(n: Nat) -> Nat:
  n * 18446744073709551616n
def items(n: Nat) -> Lists.List<Nat>:
  match n:
    case 0: Lists.List::<Nat>.nil({})
    case 1+p: Lists.List::<Nat>.cons({head: n, tail: items(p)})
def pair(n: Nat) -> {left: Nat, right: String}:
  {left: n, right: word(n)}
def shout(n: Nat) -> Activity<Nat>:
  match world.note({text: word(n), count: n, items: items(n)}):
    case ok(_): n
"""

NOTE_WORLD = """edition ObjectiveBend 1
import ./List.obend as Lists
record Reference:
  world: String
  object: String
record Message:
  object: Reference
  method: String
  argument: Data
record Note:
  text: String
  count: Nat
  items: Lists.List<Nat>
sum Reply:
  ok: {}
protocol world:
  note(Note) -> Reply
"""


class CanonicalBytes(unittest.TestCase):
    """The byte budget is the canonical DAG-CBOR size of the result or Plan: a value runs
    under exactly its encoded size and is refused a byte short (review kernel 8: `true`, one
    byte, was refused under `bytes: 1`; sizes were decimal-length legacy accounting)."""

    def test_each_result_and_plan_runs_under_exactly_its_canonical_size(self):
        h = Host()
        self.addCleanup(h.close)
        for entry, argument in (("yes", 3), ("word", 2), ("word", 26), ("big", 7), ("pair", 5)):
            with self.subTest(entry=entry, argument=argument):
                art = h.compile(VALUES, entry, library=("List",), world=NOTE_WORLD)
                free = h.send({"op": "run", "artifact": art, "arguments": [nat(argument)], "limits": BIG})
                self.assertEqual(free["status"], "finished", free)
                size = h.send({"op": "canonical-encode", "data": free["value"]})["bytes"]
                ran = h.send({"op": "run", "artifact": art, "arguments": [nat(argument)],
                              "limits": {"ticks": "1000000", "bytes": str(size)}})
                self.assertEqual((ran["status"], ran.get("value")), ("finished", free["value"]), (size, ran))
                short = h.send({"op": "run", "artifact": art, "arguments": [nat(argument)],
                                "limits": {"ticks": "1000000", "bytes": str(size - 1)}})
                self.assertEqual(short["status"], "refused", (size, short))
        art = h.compile(VALUES, "shout", library=("List",), world=NOTE_WORLD)
        for n in (0, 4, 30):  # the items list crosses as an array: one head, no cons cells
            with self.subTest(n=n):
                free = h.start(art, [nat(n)])
                self.assertEqual(free["status"], "yielded", free)
                size = h.send({"op": "canonical-encode", "data": free["plan"]})["bytes"]
                fits = h.start(art, [nat(n)], bytes=str(size))
                self.assertEqual((fits["status"], fits.get("plan")), ("yielded", free["plan"]), (size, fits))
                short = h.start(art, [nat(n)], bytes=str(size - 1))
                self.assertEqual((short["status"], short.get("resource")), ("exhausted", "bytes"), (size, short))


EQUAL = """edition ObjectiveBend 1
def same(a: String, b: String) -> Bool:
  a == b
"""


class LabelEqual(unittest.TestCase):
    def test_text_equality_is_charged_by_the_bytes_it_compares(self):
        # Refuted by a one-tick comparison of two 100,000-byte texts differing in their last
        # byte (review kernel 9): equality scans the common prefix.
        from tests.test_objects import compile_job, check
        art = compile_job([{"name": "Package", "source": EQUAL}], "same")["artifact"]
        def ran(a, b):
            r = check({"op": "run", "artifact": art, "arguments": [{"tag": "label", "value": a},
                       {"tag": "label", "value": b}], "limits": BIG})
            self.assertEqual(r["status"], "finished", r)
            return r["value"]["value"], r["ticksUsed"]
        long_a, long_b = "x" * 99999 + "a", "x" * 99999 + "b"
        short = ran("a", "b")
        far = ran(long_a, long_b)
        self.assertEqual((short[0], far[0]), (False, False))
        self.assertGreaterEqual(far[1] - short[1], 99999)
        self.assertEqual(ran(long_a, long_a)[0], True)


PREFIX = """edition ObjectiveBend 1
def taken(s: String) -> String:
  textTake(s, 100n)
def dropped(s: String) -> String:
  textDrop(s, 100n)
def spanned(s: String) -> Nat:
  textSpan(s, "x")
"""


class FailedPreflight(unittest.TestCase):
    def test_a_failed_prefix_preflight_spends_the_allowance_it_scanned(self):
        # Refuted when a take or drop whose prefix scan cannot be paid reports less than its
        # whole allowance as used (review kernel 10): the scan ran, as span's does.
        from tests.test_objects import compile_job, check
        text = {"tag": "label", "value": "x" * 1000}
        for entry in ("taken", "dropped", "spanned"):
            with self.subTest(entry=entry):
                art = compile_job([{"name": "Package", "source": PREFIX}], entry)["artifact"]
                whole = check({"op": "run", "artifact": art, "arguments": [text], "limits": BIG})
                self.assertEqual(whole["status"], "finished", whole)
                budget = whole["ticksUsed"] - 150
                short = check({"op": "run", "artifact": art, "arguments": [text],
                               "limits": {"ticks": str(budget)}})
                self.assertEqual(short["status"], "refused", short)
                self.assertEqual(short["ticksUsed"], budget, short)


if __name__ == "__main__":
    unittest.main()
