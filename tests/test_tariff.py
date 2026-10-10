"""The tariff, pinned: exact tick counts of workloads whose code lives in the test, so only a change
to the machine's charges moves them.

Evidence for FOUNDATION §2 Limits (layer: kernel).

The tariff, pinned: exact tick counts of workloads whose code is fixed in this file, so
only a change to the machine's charges can move them.

    python3 -m unittest tests.test_tariff -v

Conformance compares values, never costs, so these counts are the regression guard for
the tariff: a change to the machine or to `textStepCost` that moves one of them must
update the number here and say why. Workloads over world library code (a Bell card, a
spell parse) are bounded where that code is tested, never pinned here: their counts move
with every edit of the library.

| workload                                   | before  | after   |
| ------------------------------------------ | ------- | ------- |
| one `bump` turn (start 73 + resume 10)     | 66      | 83      |
| `Document.plain`, 1,025 leaves (with build)| 336,659 | 129,272 |
| the same document's `Document.size` walk   | 120,037 | 120,037 |

Before: `Document.plain` joined adjacent pairs in rounds (every byte copied about
log2(leaves) times); `textTake`/`textDrop` were charged 2 x min(B, 4n) bytes.
The `bump` row moved from 66 to 83 when the turn became a world call: the start now builds a
`Message` record (object reference, method label) and injects the edit record as `Data`,
where the old form injected one sum variant; the resume (10) is unchanged.
After: `plain` is one `textJoin` (charged by the bytes it appends), and take/drop
are charged by the exact bytes of the prefix they traverse.
"""
import unittest

from tests.test_turn import Host, PLANS, PLANS_WORLD, BINDING, nat, variant
from tests.test_objects import run_pure

BIG = {"ticks": "1000000"}

DOCUMENT = """edition ObjectiveBend 1
import ./Document.obend as Document
def leaves(n: Nat) -> Document.Documents:
  match n:
    case 0: Document.Documents.nil()
    case 1+p: Document.Documents.cons({head: Document.text("abcdefgh"), tail: leaves(p)})
def flat(n: Nat) -> Nat:
  textLength(Document.plain(Document.Document.sequence({items: leaves(n)})))
def sized(n: Nat) -> Nat:
  Document.size(Document.Document.sequence({items: leaves(n)}))
"""

STRINGS = """edition ObjectiveBend 1
import ./List.obend as Lists
def strings(n: Nat, word: String) -> Lists.List<String>:
  match n:
    case 0: Lists.List::<String>.nil()
    case 1+p: Lists.List::<String>.cons({head: word, tail: strings(p, word)})
def joined(n: Nat) -> String:
  textJoin(strings(n, "ab"), ", ")
def size(n: Nat) -> Nat:
  textLength(textJoin(strings(n, "x"), ""))
"""


class TariffTests(unittest.TestCase):
    def test_a_bump_turn_costs_73_ticks_to_start_and_10_to_resume(self):
        h = Host()
        self.addCleanup(h.close)
        art = h.compile(PLANS, "bump", world=PLANS_WORLD)
        started = h.start(art, [nat(41)])
        resumed = h.resume(art, started["checkpoint"], variant("written"))
        print("\n  bump: start %d + resume %d ticks" % (started["ticksUsed"], resumed["ticksUsed"]))
        self.assertEqual((started["ticksUsed"], resumed["ticksUsed"]), (73, 10))

    def test_document_plain_over_1025_leaves_costs_its_pinned_ticks(self):
        flat = run_pure("Document", "flat", nat(1025), probe=DOCUMENT, limits=BIG)
        sized = run_pure("Document", "sized", nat(1025), probe=DOCUMENT, limits=BIG)
        print("\n  plain, 1,025 leaves: %d ticks (was 336,659); size walk %d; plain's own work %d"
              % (flat["ticksUsed"], sized["ticksUsed"], flat["ticksUsed"] - sized["ticksUsed"]))
        self.assertEqual(flat["value"]["value"], "8200")
        self.assertEqual(flat["ticksUsed"], 129272)
        self.assertEqual(sized["ticksUsed"], 120037)
        self.assertLess(flat["ticksUsed"] - sized["ticksUsed"], 50000)

    def test_text_join_is_linear_in_its_output(self):
        # Refuted if a join re-reads its accumulator: doubling the elements would
        # then roughly quadruple the ticks.
        costs = [run_pure("Document", "size", nat(n), probe=STRINGS, limits=BIG)["ticksUsed"] for n in (2000, 4000, 8000)]
        print("\n  textJoin of 2,000 / 4,000 / 8,000 elements: %s ticks" % costs)
        self.assertLess(costs[2], 2.1 * costs[1])
        self.assertLess(costs[1], 2.1 * costs[0])

    def test_text_join_separates_and_refuses_a_non_list(self):
        joined = run_pure("Document", "joined", nat(3), probe=STRINGS)
        self.assertEqual(joined["value"]["value"], "ab, ab, ab")
        self.assertEqual(run_pure("Document", "joined", nat(0), probe=STRINGS)["value"]["value"], "")
        from tests.test_objects import compile_job
        refused = compile_job([{"name": "Package", "source":
            "edition ObjectiveBend 1\ndef f(n: Nat) -> String:\n  textJoin(n, \"\")\n"}], "f")
        self.assertNotEqual(refused["status"], "compiled", refused)


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

    def test_small_naturals_cost_one_tick_and_bignums_are_charged(self):
        small = run_pure("Document", "big", nat(5), probe=SQUARES, limits=BIG)
        self.assertEqual(small["value"], {"tag": "boolean", "value": True})
        larger = run_pure("Document", "big", nat(9), probe=SQUARES, limits=BIG)
        self.assertEqual(larger["value"], {"tag": "boolean", "value": True})
        # 2^(2^9) needs three more squarings past a word, each charged by its operand bytes.
        self.assertGreater(larger["ticksUsed"] - small["ticksUsed"], 4 * 50)
        summed = run_pure("Document", "sum", nat(12), probe=SQUARES, limits=BIG)
        self.assertEqual(summed["value"], {"tag": "boolean", "value": True})


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

    def test_each_result_runs_under_exactly_its_canonical_size(self):
        from tests.test_objects import check
        from tests.test_turn import library_modules
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

    def test_a_plan_yields_under_exactly_its_canonical_size(self):
        h = Host()
        self.addCleanup(h.close)
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
